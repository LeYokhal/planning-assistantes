"""Services d'import et de lecture des présences.

Une ligne `ImportPresences` est écrite une fois, terminée une fois, et plus
jamais retouchée. L'écran du mois ne recalcule rien de durable : il relit les
payloads bruts des imports réussis les plus récents.
"""

import datetime
import hashlib
import logging
from dataclasses import dataclass

from django.utils import timezone

from audit.models import Action
from audit.services import journaliser

from . import lecture as lecture_s7
from . import webhooks
from .models import ImportPresences
from .verrou import peremption

logger = logging.getLogger(__name__)

MOTIF_ECART = "écart enveloppe"
ERREUR_INTERROMPU = "interrompu (délai dépassé)"

CLASSE_PRESENT = "present"
CLASSE_PRESENT_ATYPIQUE = "present-atypique"
CLASSE_ATYPIQUE = "atypique"
CLASSE_FERME = "ferme"
CLASSE_NONPLAN = "nonplan"
CLASSE_AUTRE = "autre"
CLASSE_INCONNU = "inconnu"


# --- Structures de lecture pour l'écran -------------------------------------


@dataclass(frozen=True)
class Cellule:
    """Une case du tableau : un agenda, un jour."""

    agenda: str
    presence: bool
    verdict: str
    libelle: str
    classe: str
    effectifs: tuple = ()
    nb_rdv: int = 0
    journee_courte: bool = False


@dataclass(frozen=True)
class Jour:
    """Un jour de la plage, couvert par un import ou non."""

    date: datetime.date
    couvert: bool = False
    import_id: int = None
    nb_ouverts: int = 0
    nb_presents: int = 0
    cellules: tuple = ()

    @property
    def week_end(self):
        return self.date.weekday() >= 5


@dataclass(frozen=True)
class Ligne:
    """Une ligne du tableau d'une semaine : un agenda, ses sept cases.

    `cases` contient une `Cellule` par jour couvert et None pour un jour non
    importé. Les gabarits Django ne savent pas indexer une liste par variable :
    le croisement agenda × jour est donc fait ici, pas dans le gabarit.
    """

    agenda: str
    cases: tuple


@dataclass(frozen=True)
class Semaine:
    """Une semaine complète, lundi → dimanche."""

    lundi: datetime.date
    jours: tuple
    lignes: tuple = ()


@dataclass(frozen=True)
class Couverture:
    """Ce que l'écran du mois a besoin de savoir, et rien de plus."""

    debut: datetime.date
    fin: datetime.date
    semaines: tuple = ()
    agendas: tuple = ()
    sources: tuple = ()
    jours_non_couverts: int = 0


# --- Écriture ---------------------------------------------------------------


def requalifier_interrompus():
    """Passe en échec les lignes « en cours » trop vieilles. Renvoie leur nombre.

    Un redéploiement, un plantage ou un thread tué laissent une ligne « en
    cours » qui ne se terminera jamais. Sans cette requalification, l'écran la
    compterait indéfiniment comme un import en route.
    """
    limite = timezone.now() - peremption()
    perimes = ImportPresences.objects.filter(
        statut=ImportPresences.Statut.EN_COURS, importe_le__lt=limite
    )
    nombre = perimes.update(
        statut=ImportPresences.Statut.ECHEC,
        erreur=ERREUR_INTERROMPU,
        termine_le=timezone.now(),
    )
    if nombre:
        logger.warning("imports interrompus requalifies en echec : %s", nombre)
    return nombre


def _empreinte(contenu):
    """SHA-256 hexadécimal des octets reçus."""
    return hashlib.sha256(contenu).hexdigest()


def _details_audit(import_):
    """Détails journalisables d'un import : jamais de nom, jamais de fichier."""
    return {
        "source": import_.source,
        "mois": import_.mois,
        "lot": str(import_.lot),
        "invariant_ok": import_.invariant_ok,
        "nb_lignes": import_.nb_lignes,
    }


def _appliquer_lecture(import_, resultat):
    """Reporte une lecture réussie sur la ligne d'import (sans sauvegarder)."""
    import_.statut = ImportPresences.Statut.REUSSI
    import_.payload = resultat.payload
    import_.forme = resultat.forme
    import_.debut = resultat.debut
    import_.fin = resultat.fin
    import_.message = resultat.message
    import_.invariant_ok = True
    import_.nb_jours = resultat.nb_jours
    import_.nb_lignes = resultat.nb_lignes
    import_.nb_presents = resultat.nb_presents
    import_.erreur = ""
    import_.termine_le = timezone.now()


def _appliquer_echec(import_, erreur):
    """Reporte un refus de lecture sur la ligne d'import (sans sauvegarder)."""
    message = str(erreur)[: lecture_s7.LONGUEUR_MAX_ERREUR]
    import_.statut = ImportPresences.Statut.ECHEC
    import_.erreur = message
    # L'invariant n'est « faux » que si c'est lui qui a refusé le payload : dans
    # tous les autres cas, il n'a pas pu être évalué.
    import_.invariant_ok = False if message.startswith(MOTIF_ECART) else None
    import_.termine_le = timezone.now()


def importer_fichier(contenu, qui, nom_fichier=""):
    """Importe un payload S7 déposé depuis le navigateur. Toujours synchrone.

    Un import fichier ne prend pas le verrou : il ne touche pas au réseau et dure
    moins d'une seconde. Il ne passe jamais par l'état « en cours ».
    """
    requalifier_interrompus()

    import_ = ImportPresences(
        source=ImportPresences.Source.FICHIER,
        statut=ImportPresences.Statut.EN_COURS,
        empreinte=_empreinte(contenu),
        taille=len(contenu),
        nom_fichier=str(nom_fichier)[:120],
        importe_par=qui if getattr(qui, "is_authenticated", False) else None,
    )

    try:
        _appliquer_lecture(import_, lecture_s7.lire(contenu))
    except lecture_s7.PayloadInvalide as erreur:
        _appliquer_echec(import_, erreur)

    import_.save()

    reussi = import_.statut == ImportPresences.Statut.REUSSI
    journaliser(
        Action.IMPORT_REUSSI if reussi else Action.IMPORT_ECHEC,
        qui=qui,
        objet=import_,
        **_details_audit(import_),
    )
    logger.info(
        "import fichier #%s : %s, fenetre %s->%s, %s lignes",
        import_.pk,
        import_.statut,
        import_.debut,
        import_.fin,
        import_.nb_lignes,
    )

    webhooks.notifier_lot([import_])
    return import_


def doublon_de(import_):
    """Renvoie le plus ancien import réussi de même empreinte, ou None."""
    if not import_.empreinte:
        return None
    return (
        ImportPresences.objects.filter(
            statut=ImportPresences.Statut.REUSSI, empreinte=import_.empreinte
        )
        .exclude(pk=import_.pk)
        .order_by("importe_le", "id")
        .first()
    )


def creer_import_endpoint(mois, lot, debut, fin):
    """Ouvre une ligne « en cours » pour une fenêtre d'un tir endpoint."""
    return ImportPresences.objects.create(
        source=ImportPresences.Source.ENDPOINT,
        statut=ImportPresences.Statut.EN_COURS,
        lot=lot,
        mois=mois,
        debut=debut,
        fin=fin,
    )


def terminer_import(import_, contenu, duree_ms=None, fenetre_attendue=None):
    """Termine une ligne « en cours » avec le contenu reçu de l'endpoint."""
    import_.empreinte = _empreinte(contenu)
    import_.taille = len(contenu)
    import_.duree_ms = duree_ms

    try:
        resultat = lecture_s7.lire(contenu)
        if fenetre_attendue is not None and (
            resultat.debut,
            resultat.fin,
        ) != tuple(fenetre_attendue):
            raise lecture_s7.PayloadInvalide(
                f"fenêtre inattendue : {resultat.debut}→{resultat.fin} "
                f"au lieu de {fenetre_attendue[0]}→{fenetre_attendue[1]}"
            )
        _appliquer_lecture(import_, resultat)
    except lecture_s7.PayloadInvalide as erreur:
        _appliquer_echec(import_, erreur)

    import_.save()

    reussi = import_.statut == ImportPresences.Statut.REUSSI
    journaliser(
        Action.IMPORT_REUSSI if reussi else Action.IMPORT_ECHEC,
        qui=None,
        objet=import_,
        **_details_audit(import_),
    )
    logger.info(
        "import endpoint #%s : %s, fenetre %s->%s, %s lignes, %s ms",
        import_.pk,
        import_.statut,
        import_.debut,
        import_.fin,
        import_.nb_lignes,
        import_.duree_ms,
    )
    return import_


def echouer_import(import_, erreur):
    """Termine une ligne en échec sans qu'aucun payload n'ait pu être lu."""
    _appliquer_echec(import_, erreur)
    import_.save()

    journaliser(
        Action.IMPORT_ECHEC, qui=None, objet=import_, **_details_audit(import_)
    )
    logger.warning(
        "import #%s en echec : %s", import_.pk, import_.erreur
    )
    return import_


# --- Lecture pour l'écran ---------------------------------------------------


def _formater_creneaux(creneaux):
    """« 09:30–13:30 · 14:30–18:30 » à partir des créneaux effectifs."""
    segments = []
    for creneau in creneaux or ():
        if isinstance(creneau, (list, tuple)) and len(creneau) == 2:
            segments.append(f"{creneau[0]}–{creneau[1]}")
        else:
            segments.append(str(creneau))
    return tuple(segments)


def construire_cellule(agenda, ligne):
    """Traduit une ligne praticien du payload en case de tableau.

    Le signal PRIMAIRE est `presence` — jamais `creneaux_effectifs` seuls, qui
    ne disent rien de l'ouverture de l'agenda.
    """
    presence = bool(ligne.get("presence"))
    verdict = str(ligne.get("verdict", ""))
    nb_rdv = ligne.get("nb_rdv") or 0
    courte = bool(ligne.get("journee_courte"))
    effectifs = _formater_creneaux(ligne.get("creneaux_effectifs"))

    if presence and effectifs:
        libelle = "✓ " + " · ".join(effectifs)
        if courte:
            libelle += " · courte"
        classe = CLASSE_PRESENT
    elif presence:
        libelle = f"✓ atypique · {nb_rdv} RDV"
        classe = CLASSE_PRESENT_ATYPIQUE
    elif verdict == lecture_s7.VERDICT_ATYPIQUE:
        libelle = f"atypique · {nb_rdv} RDV"
        classe = CLASSE_ATYPIQUE
    elif verdict == lecture_s7.VERDICT_FERME:
        libelle = "fermé"
        classe = CLASSE_FERME
    elif verdict == lecture_s7.VERDICT_NON_PLANIFIE:
        libelle = "·"
        classe = CLASSE_NONPLAN
    else:
        libelle = verdict
        classe = CLASSE_AUTRE

    return Cellule(
        agenda=agenda,
        presence=presence,
        verdict=verdict,
        libelle=libelle,
        classe=classe,
        effectifs=effectifs,
        nb_rdv=nb_rdv,
        journee_courte=courte,
    )


def _jours_par_date(import_):
    """Index `date ISO -> jour` du payload d'un import réussi."""
    payload = import_.payload or {}
    jours = (payload.get("donnees") or {}).get("jours") or []
    return {
        jour.get("date"): jour
        for jour in jours
        if isinstance(jour, dict) and jour.get("date")
    }


def couverture(debut, fin):
    """Assemble la couverture de la plage `debut`→`fin` pour l'écran du mois.

    Pour chaque jour, c'est le DERNIER import réussi (par date d'import) dont la
    fenêtre couvre ce jour qui fait foi : un import plus récent corrige un
    import plus ancien sans que rien ne soit ni modifié ni supprimé.
    """
    imports = list(
        ImportPresences.objects.filter(
            statut=ImportPresences.Statut.REUSSI,
            debut__lte=fin,
            fin__gte=debut,
        ).order_by("-importe_le", "-id")
    )
    index = {import_.pk: _jours_par_date(import_) for import_ in imports}

    retenus = {}
    jours_bruts = {}
    date_courante = debut
    while date_courante <= fin:
        cle = date_courante.isoformat()
        for import_ in imports:
            if import_.debut <= date_courante <= import_.fin and cle in index[import_.pk]:
                retenus[cle] = import_
                jours_bruts[cle] = index[import_.pk][cle]
                break
        date_courante += datetime.timedelta(days=1)

    agendas = sorted(
        {
            str(ligne.get("praticien", "")).strip()
            for jour in jours_bruts.values()
            for ligne in jour.get("praticiens", [])
            if isinstance(ligne, dict)
        },
        key=str.casefold,
    )

    jours = []
    date_courante = debut
    while date_courante <= fin:
        cle = date_courante.isoformat()
        brut = jours_bruts.get(cle)
        if brut is None:
            jours.append(Jour(date=date_courante))
        else:
            par_agenda = {
                str(ligne.get("praticien", "")).strip(): ligne
                for ligne in brut.get("praticiens", [])
                if isinstance(ligne, dict)
            }
            cellules = tuple(
                construire_cellule(agenda, par_agenda[agenda])
                if agenda in par_agenda
                else Cellule(
                    agenda=agenda,
                    presence=False,
                    verdict="",
                    libelle="?",
                    classe=CLASSE_INCONNU,
                )
                for agenda in agendas
            )
            # Recomptés sur le détail, jamais lus dans le payload.
            jours.append(
                Jour(
                    date=date_courante,
                    couvert=True,
                    import_id=retenus[cle].pk,
                    nb_ouverts=sum(
                        1
                        for cellule in cellules
                        if cellule.verdict
                        in (lecture_s7.VERDICT_OUVERT, lecture_s7.VERDICT_ATYPIQUE)
                    ),
                    nb_presents=sum(1 for cellule in cellules if cellule.presence),
                    cellules=cellules,
                )
            )
        date_courante += datetime.timedelta(days=1)

    semaines = []
    for depart in range(0, len(jours), 7):
        jours_semaine = tuple(jours[depart : depart + 7])
        semaines.append(
            Semaine(
                lundi=jours_semaine[0].date,
                jours=jours_semaine,
                lignes=tuple(
                    Ligne(
                        agenda=agenda,
                        cases=tuple(
                            jour.cellules[rang] if jour.couvert else None
                            for jour in jours_semaine
                        ),
                    )
                    for rang, agenda in enumerate(agendas)
                ),
            )
        )
    semaines = tuple(semaines)
    sources = tuple(sorted(set(retenus.values()), key=lambda import_: import_.pk))

    return Couverture(
        debut=debut,
        fin=fin,
        semaines=semaines,
        agendas=tuple(agendas),
        sources=sources,
        jours_non_couverts=sum(1 for jour in jours if not jour.couvert),
    )
