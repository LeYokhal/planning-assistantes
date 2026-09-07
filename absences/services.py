"""Cycle de vie d'une absence : création, décision, annulation, correction.

Toutes les écritures passent par ici — les vues et l'admin n'écrivent pas de
statut à la main. C'est ce qui garantit qu'un événement d'audit et, le cas
échéant, un webhook accompagnent chaque transition.

⚠️ Aucun appel à `journaliser` de ce module ne passe le type d'absence ni la
précision. Ce qui entre dans `details` : des identifiants, des dates, des
statuts, des comptages. Rien d'autre. Le garde-fou « @ » d'`audit/services.py`
ne reconnaîtrait pas « Maladie » comme une donnée sensible : c'est à la main que
cela se tient.

Brique 4b : quand une absence devient effective (déclaration, validation,
reprise depuis l'administration), `signaler_conflits` regarde si un planning
publié pose déjà une brique de la salariée sur un de ces jours. Le conflit est
signalé (audit, webhook), jamais bloquant, toujours après l'écriture.

Brique 3-quater (C3.9) : `importer`, `analyser_import` et `executer_import`
portent la reprise exceptionnelle de l'existant Notion depuis un fichier, une
fois. Les absences importées naissent effectives, sans webhook ni crochet de
conflit : les conflits sont listés dans le rapport d'analyse, pas signalés.
"""

import datetime
import logging
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser
from comptes.models import Compte, Personne

from . import calcul, webhooks
from .models import AbsenceSalariee, TypeAbsence

logger = logging.getLogger(__name__)

PAS_CORRECTION = 0.5


class ActionImpossible(Exception):
    """Geste refusé par la règle métier. Le message est affichable tel quel."""


def _retention_jours():
    """Durée de rétention en jours, ou None si le réglage est absent.

    Fail-closed (décision F) : absent = aucune purge, `a_effacer_le` laissé nul,
    et la commande de purge rattrapera le jour où le réglage apparaîtra.
    """
    from django.conf import settings

    valeur = getattr(settings, "RETENTION_ABSENCES_JOURS", None)
    try:
        jours = int(valeur)
    except (TypeError, ValueError):
        return None
    return jours if jours > 0 else None


def date_effacement(depuis=None):
    """Date de purge à poser, ou None si la rétention n'est pas réglée."""
    jours = _retention_jours()
    if jours is None:
        return None
    base = depuis or timezone.localdate()
    return base + datetime.timedelta(days=jours)


def _poser_echeance(absence):
    """Pose `a_effacer_le` si la rétention est réglée. Sans effet sinon."""
    if absence.a_effacer_le is None:
        absence.a_effacer_le = date_effacement()


def _appliquer_calcul(absence):
    """Pose les jours comptés et les DATES qui les portent.

    `jours_retenus` est figé ici, en même temps que la valeur calculée : c'est
    lui qui permettra de répartir l'absence entre les mois de paie sans jamais
    rejouer le calcul sur un morceau. Renvoie le signal éventuel.
    """
    resultat = calcul.jours_comptes_de(absence)
    absence.jours_comptes_calcules = resultat.jours
    absence.jours_retenus = resultat.dates_iso
    if not absence.corrigee:
        absence.jours_comptes = resultat.jours
    return resultat.signal


def creer(personne, type_absence, date_debut, date_fin, auteur, precision=""):
    """Crée une absence. Le type décide si elle attend une décision.

    Un type de catégorie « déclaration » est effectif immédiatement : les jours
    comptés sont posés dans la foulée, et l'échéance de purge avec.
    """
    if not calcul.est_salariee(personne):
        raise ActionImpossible(
            "Une absence ne peut porter que sur une assistante ou une secrétaire."
        )
    if date_fin < date_debut:
        raise ActionImpossible("Le dernier jour ne peut pas précéder le premier.")

    declaration = type_absence.categorie == TypeAbsence.Categorie.DECLARE
    absence = AbsenceSalariee(
        personne=personne,
        type=type_absence,
        date_debut=date_debut,
        date_fin=date_fin,
        precision=(precision or "").strip(),
        auteur=auteur if getattr(auteur, "is_authenticated", False) else None,
        statut=(
            AbsenceSalariee.Statut.DECLAREE
            if declaration
            else AbsenceSalariee.Statut.EN_ATTENTE
        ),
    )

    signal = ""
    if declaration:
        signal = _appliquer_calcul(absence)
        _poser_echeance(absence)

    absence.save()

    action = Action.ABSENCE_DECLAREE if declaration else Action.ABSENCE_DEMANDEE
    journaliser(
        action,
        qui=auteur,
        objet=absence,
        personne_id=absence.personne_id,
        debut=absence.date_debut.isoformat(),
        fin=absence.date_fin.isoformat(),
        statut=absence.statut,
    )
    logger.info(
        "absence #%s creee (statut %s, %s jour(s) de plage)",
        absence.pk,
        absence.statut,
        absence.nb_jours_plage,
    )

    webhooks.notifier(
        webhooks.EVENEMENT_DECLAREE if declaration else webhooks.EVENEMENT_DEMANDEE,
        absence,
    )
    if declaration:
        signaler_conflits(absence, auteur)
    return absence, signal


def peut_decider(absence, qui):
    """Règle K : la personne concernée ne décide pas de sa propre absence.

    La règle est assise sur la PERSONNE, pas sur l'auteur de la saisie : un
    compte supprimé laisse `auteur` nul (SET_NULL), et une règle qui s'appuierait
    sur lui deviendrait inévaluable. Seul le rôle `cabinet` tranche alors.
    """
    if qui.role == Compte.Role.CABINET:
        return True
    personne_du_decideur = getattr(qui, "personne_id", None)
    return personne_du_decideur is None or personne_du_decideur != absence.personne_id


def decider(absence, valider, qui):
    """Valide ou refuse une demande en attente."""
    if absence.statut != AbsenceSalariee.Statut.EN_ATTENTE:
        raise ActionImpossible("Cette absence n'est plus en attente de décision.")
    # Décision P, tenue aussi ici : une absence de praticien ne doit pas pouvoir
    # devenir effective, quel que soit le chemin par lequel elle a été créée.
    if not calcul.est_salariee(absence.personne):
        raise ActionImpossible(
            "Une absence ne peut porter que sur une assistante ou une secrétaire."
        )
    if not peut_decider(absence, qui):
        raise ActionImpossible(
            "Vous ne pouvez pas décider de votre propre absence : "
            "seul le cabinet peut la trancher."
        )

    absence.statut = (
        AbsenceSalariee.Statut.VALIDEE if valider else AbsenceSalariee.Statut.REFUSEE
    )
    absence.decide_par = qui
    absence.decide_le = timezone.now()

    signal = ""
    if valider:
        signal = _appliquer_calcul(absence)
        _poser_echeance(absence)

    absence.save(
        update_fields=[
            "statut",
            "decide_par",
            "decide_le",
            "jours_comptes_calcules",
            "jours_comptes",
            "jours_retenus",
            "a_effacer_le",
        ]
    )

    journaliser(
        Action.ABSENCE_DECIDEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
        statut=absence.statut,
        jours_comptes=str(absence.jours_comptes or ""),
    )
    logger.info("absence #%s decidee : %s", absence.pk, absence.statut)

    webhooks.notifier(webhooks.EVENEMENT_DECIDEE, absence)
    if valider:
        signaler_conflits(absence, qui)
    return signal


def signaler_conflits(absence, qui):
    """Signale un conflit avec un planning publié quand l'absence devient effective.

    Décision C : ne bloque jamais, vient après l'écriture, l'audit et le webhook
    de l'absence. Décision I : types bloquants seulement. Le journal et le
    webhook ne portent que des identifiants, des numéros de version et des
    dates : ni type, ni précision, ni nom.
    """
    if not absence.type.bloquant:
        return []
    # Import local : `planning.donnees` importe ce module, le cycle serait
    # direct (patron de `presences/verrou.py`).
    from planning.conflits import conflits

    liste = conflits(absence.personne, absence.date_debut, absence.date_fin)
    for conflit in liste:
        journaliser(
            Action.ABSENCE_CONFLIT_PUBLICATION,
            qui=qui,
            objet=absence,
            personne_id=absence.personne_id,
            mois=conflit["mois"],
            numero=conflit["numero"],
            dates=conflit["dates"],
        )
    if liste:
        logger.info(
            "absence #%s en conflit avec %s planning(s) publie(s)", absence.pk, len(liste)
        )
        webhooks.notifier_conflit(absence, liste)
    return liste


def annuler(absence, qui):
    """Annule une demande encore en attente. Auditée, sans webhook."""
    if absence.statut != AbsenceSalariee.Statut.EN_ATTENTE:
        raise ActionImpossible("Seule une demande en attente peut être annulée.")

    absence.statut = AbsenceSalariee.Statut.ANNULEE
    absence.save(update_fields=["statut"])

    journaliser(
        Action.ABSENCE_ANNULEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
    )
    logger.info("absence #%s annulee", absence.pk)
    return absence


def corriger(absence, valeur, qui):
    """Pose à la main la valeur retenue des jours comptés.

    Seule porte d'entrée des demi-journées (décision O) : le pas est de 0,5, la
    valeur est bornée par la durée de la plage, et la valeur calculée n'est
    jamais touchée — c'est ce qui rend l'écart lisible six mois plus tard.
    """
    from decimal import Decimal, InvalidOperation

    try:
        retenu = Decimal(str(valeur)).quantize(Decimal("0.1"))
    except (InvalidOperation, ValueError, TypeError):
        raise ActionImpossible("Valeur illisible.") from None

    if retenu < 0:
        raise ActionImpossible("Les jours comptés ne peuvent pas être négatifs.")
    if retenu > absence.nb_jours_plage:
        raise ActionImpossible(
            f"Les jours comptés ne peuvent pas dépasser la durée de l'absence "
            f"({absence.nb_jours_plage} jour(s))."
        )
    if (retenu % Decimal(str(PAS_CORRECTION))) != 0:
        raise ActionImpossible("Les jours comptés vont par pas d'une demi-journée.")

    absence.jours_comptes = retenu
    absence.corrige_par = qui
    absence.corrige_le = timezone.now()
    absence.save(update_fields=["jours_comptes", "corrige_par", "corrige_le"])

    journaliser(
        Action.ABSENCE_CORRIGEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
        calcules=str(absence.jours_comptes_calcules or ""),
        retenus=str(retenu),
    )
    logger.info(
        "absence #%s corrigee : %s -> %s",
        absence.pk,
        absence.jours_comptes_calcules,
        retenu,
    )
    return absence


def recalculer(absence):
    """Rejoue le calcul. Ne touche JAMAIS une absence corrigée à la main."""
    if not absence.effective:
        return False
    resultat = calcul.jours_comptes_de(absence)
    champs = ["jours_comptes_calcules", "jours_retenus"]
    absence.jours_comptes_calcules = resultat.jours
    absence.jours_retenus = resultat.dates_iso
    if not absence.corrigee:
        absence.jours_comptes = resultat.jours
        champs.append("jours_comptes")
    absence.save(update_fields=champs)
    return True


def absences_du_mois(debut, fin, pour_la_paie=True):
    """Absences effectives recouvrant la plage, prêtes pour la paie."""
    requete = AbsenceSalariee.objects.filter(
        statut__in=AbsenceSalariee.STATUTS_EFFECTIFS,
        date_debut__lte=fin,
        date_fin__gte=debut,
    ).select_related("personne", "type")
    if pour_la_paie:
        requete = requete.filter(type__paie=True)
    return requete.order_by("personne__nom", "personne__prenom", "date_debut")


# --- Brique 3-quater : reprise exceptionnelle de l'existant Notion (C3.9) -----

VERDICT_CREER = "creer"
VERDICT_DEJA_PRESENTE = "deja_presente"
VERDICT_ERREUR = "erreur"
VERDICTS = (VERDICT_CREER, VERDICT_DEJA_PRESENTE, VERDICT_ERREUR)
LIBELLES_VERDICTS = {
    VERDICT_CREER: "à créer",
    VERDICT_DEJA_PRESENTE: "déjà présente",
    VERDICT_ERREUR: "erreur",
}


def importer(personne, type_absence, date_debut, date_fin, qui, ref=""):
    """Crée une absence effective depuis le fichier de reprise (C3.9).

    Reprise exceptionnelle de l'existant Notion, une fois : l'absence naît
    effective — `validee` si le type est soumis à décision, `qui` tenant lieu
    de décideur, `declaree` sinon. Même calcul et même échéance que `creer`,
    en un seul `save()`. Ni webhook ni crochet de conflit (I3) : les conflits
    avec un planning publié sont listés par `analyser_import`, pas signalés.
    L'audit porte `ref`, identifiants Notion opaques — jamais le type.
    """
    if not calcul.est_salariee(personne):
        raise ActionImpossible(
            "Une absence ne peut porter que sur une assistante ou une secrétaire."
        )
    if date_fin < date_debut:
        raise ActionImpossible("Le dernier jour ne peut pas précéder le premier.")

    declaration = type_absence.categorie == TypeAbsence.Categorie.DECLARE
    absence = AbsenceSalariee(
        personne=personne,
        type=type_absence,
        date_debut=date_debut,
        date_fin=date_fin,
        precision="",
        auteur=qui,
        statut=(
            AbsenceSalariee.Statut.DECLAREE
            if declaration
            else AbsenceSalariee.Statut.VALIDEE
        ),
    )
    if not declaration:
        absence.decide_par = qui
        absence.decide_le = timezone.now()

    signal = _appliquer_calcul(absence)
    _poser_echeance(absence)
    absence.save()

    journaliser(
        Action.ABSENCE_IMPORTEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
        statut=absence.statut,
        jours_comptes=str(absence.jours_comptes or ""),
        ref=ref,
    )
    logger.info(
        "absence #%s importee (statut %s, %s jour(s) de plage)",
        absence.pk,
        absence.statut,
        absence.nb_jours_plage,
    )
    return absence, signal


def _date_iso(valeur):
    """Une date « AAAA-MM-JJ », ou None si la valeur est illisible."""
    try:
        return datetime.date.fromisoformat(str(valeur or "").strip())
    except ValueError:
        return None


def _se_chevauchent(debut_a, fin_a, debut_b, fin_b):
    """Vrai si les deux plages, bornes comprises, ont au moins un jour commun."""
    return debut_a <= fin_b and debut_b <= fin_a


def _statut_prevu(type_absence):
    """Le statut qu'une absence importée de ce type portera (I3)."""
    if type_absence.categorie == TypeAbsence.Categorie.DECLARE:
        return AbsenceSalariee.Statut.DECLAREE
    return AbsenceSalariee.Statut.VALIDEE


def analyser_import(donnees):
    """Rapport d'analyse du fichier de reprise : un verdict par ligne, sans écrire.

    `donnees` est la liste `absences` du fichier (§ 1 du plan), normalisée par
    le formulaire : chaînes `nom`, `prenom`, `type`, `debut`, `fin`, `ref`.
    Chaque ligne rendue porte la personne et le type résolus, les dates, le
    statut prévu, les jours comptés calculés par `calcul.jours_comptes` (sans
    instance), le signal de contrat, le verdict et ses motifs, et les conflits
    avec un planning publié pour les lignes à créer de type bloquant.

    Verdicts (E10) : `creer` ; `deja_presente` si une absence EFFECTIVE de même
    personne, même type et mêmes dates existe déjà (J3) ; `erreur` sinon —
    personne inconnue (`(nom, prenom)` strippés, casse exacte) ou non salariée,
    type vide, inconnu ou inactif, date illisible ou inversée, chevauchement
    d'une absence effective non identique ou d'une demande en attente (E9),
    deux lignes du fichier qui se chevauchent pour une même personne (les deux).
    Les absences refusées et annulées ne comptent pas.

    Lectures seulement : `Personne`, `TypeAbsence`, `AbsenceSalariee` et les
    versions publiées ; aucune écriture, aucun audit, aucun log.
    """
    personnes = {(p.nom, p.prenom): p for p in Personne.objects.all()}
    types = {t.libelle: t for t in TypeAbsence.objects.all()}

    lignes = []
    for indice, brut in enumerate(donnees, start=1):
        motifs = []
        debut = _date_iso(brut.get("debut"))
        fin = _date_iso(brut.get("fin"))
        if debut is None or fin is None:
            motifs.append("date illisible")
        elif fin < debut:
            motifs.append("le dernier jour précède le premier")
        dates_valides = not motifs

        nom = str(brut.get("nom") or "").strip()
        prenom = str(brut.get("prenom") or "").strip()
        personne = personnes.get((nom, prenom))
        if personne is None:
            motifs.append("personne inconnue")
        elif not calcul.est_salariee(personne):
            motifs.append("personne non salariée")
            personne = None

        libelle = str(brut.get("type") or "").strip()
        type_ = types.get(libelle)
        if not libelle:
            motifs.append("type vide")
        elif type_ is None:
            motifs.append("type inconnu")
        elif not type_.actif:
            motifs.append("type inactif")
            type_ = None

        resultat = None
        if personne is not None and dates_valides:
            resultat = calcul.jours_comptes(personne, debut, fin)

        lignes.append(
            {
                "indice": indice,
                "ref": str(brut.get("ref") or "").strip(),
                "nom": nom,
                "prenom": prenom,
                "type_libelle": libelle,
                "personne": personne,
                "type": type_,
                "debut": debut,
                "fin": fin,
                "dates_valides": dates_valides,
                "statut": _statut_prevu(type_) if type_ is not None else "",
                "jours": resultat.jours if resultat else None,
                "signal": resultat.signal if resultat else "",
                "message": resultat.message if resultat else "",
                "motifs": motifs,
                "identique": False,
                "conflits": [],
            }
        )

    # L'existant en base, en une lecture : effectives et en attente des
    # personnes citées. Refusées et annulées sont hors jeu.
    concernees = {l["personne"].pk for l in lignes if l["personne"] is not None}
    existantes = defaultdict(list)
    for absence in AbsenceSalariee.objects.filter(personne_id__in=concernees).exclude(
        statut__in=(AbsenceSalariee.Statut.REFUSEE, AbsenceSalariee.Statut.ANNULEE)
    ):
        existantes[absence.personne_id].append(absence)

    for ligne in lignes:
        if ligne["personne"] is None or not ligne["dates_valides"]:
            continue
        chevauchantes = [
            a
            for a in existantes[ligne["personne"].pk]
            if _se_chevauchent(ligne["debut"], ligne["fin"], a.date_debut, a.date_fin)
        ]
        identiques = [
            a
            for a in chevauchantes
            if a.effective
            and ligne["type"] is not None
            and a.type_id == ligne["type"].pk
            and a.date_debut == ligne["debut"]
            and a.date_fin == ligne["fin"]
        ]
        if identiques:
            ligne["identique"] = True
            continue
        for a in chevauchantes:
            if a.effective:
                ligne["motifs"].append(f"chevauche l'absence effective #{a.pk}")
            else:
                ligne["motifs"].append(f"chevauche la demande en attente #{a.pk}")

    # Deux lignes du fichier qui se chevauchent pour une même personne : les
    # deux en erreur, le fichier est à corriger.
    par_personne = defaultdict(list)
    for ligne in lignes:
        if ligne["personne"] is not None and ligne["dates_valides"]:
            par_personne[ligne["personne"].pk].append(ligne)
    for groupe in par_personne.values():
        for rang, a in enumerate(groupe):
            for b in groupe[rang + 1 :]:
                if _se_chevauchent(a["debut"], a["fin"], b["debut"], b["fin"]):
                    a["motifs"].append(f"chevauche la ligne {b['indice']} du fichier")
                    b["motifs"].append(f"chevauche la ligne {a['indice']} du fichier")

    # Import local : `planning.donnees` importe ce module (patron de
    # `signaler_conflits`). Un seul cache de versions pour tout le rapport (E7).
    from planning.conflits import conflits

    versions = {}
    for ligne in lignes:
        if ligne["motifs"]:
            ligne["verdict"] = VERDICT_ERREUR
        elif ligne["identique"]:
            ligne["verdict"] = VERDICT_DEJA_PRESENTE
        else:
            ligne["verdict"] = VERDICT_CREER
            if ligne["type"].bloquant:
                ligne["conflits"] = conflits(
                    ligne["personne"], ligne["debut"], ligne["fin"], versions
                )
        ligne["motif"] = " ; ".join(ligne["motifs"])
        ligne["verdict_libelle"] = LIBELLES_VERDICTS[ligne["verdict"]]
        ligne["statut_libelle"] = (
            AbsenceSalariee.Statut(ligne["statut"]).label if ligne["statut"] else ""
        )
    return lignes


def compter_verdicts(lignes):
    """Compte par verdict : en-tête du rapport et champs cachés de confirmation."""
    compte = {verdict: 0 for verdict in VERDICTS}
    for ligne in lignes:
        compte[ligne["verdict"]] += 1
    return compte


def executer_import(lignes, qui, empreinte):
    """Écrit les lignes `creer` d'un rapport, tout ou rien (J2, J8).

    Refuse s'il reste une ligne en erreur : pas d'import partiel. Les lignes
    `deja_presente` sont ignorées et comptées (J3). Un seul événement
    `import_absences` par confirmation : compteurs et empreinte SHA-256 du
    fichier, jamais de nom ni de type. Tout est dans une transaction : une
    exception au milieu ne laisse rien, pas même l'audit.
    """
    nb_erreurs = sum(1 for ligne in lignes if ligne["verdict"] == VERDICT_ERREUR)
    if nb_erreurs:
        raise ActionImpossible(
            f"{nb_erreurs} ligne(s) en erreur : rien n'est importé tant que le "
            "fichier n'est pas corrigé."
        )
    a_creer = [ligne for ligne in lignes if ligne["verdict"] == VERDICT_CREER]
    nb_ignorees = sum(
        1 for ligne in lignes if ligne["verdict"] == VERDICT_DEJA_PRESENTE
    )

    with transaction.atomic():
        for ligne in a_creer:
            importer(
                ligne["personne"],
                ligne["type"],
                ligne["debut"],
                ligne["fin"],
                qui,
                ref=ligne["ref"],
            )
        journaliser(
            Action.IMPORT_ABSENCES,
            qui=qui,
            nb_creees=len(a_creer),
            nb_ignorees=nb_ignorees,
            empreinte=empreinte,
        )

    logger.info(
        "import absences : %s creee(s), %s ignoree(s)", len(a_creer), nb_ignorees
    )
    return {"nb_creees": len(a_creer), "nb_ignorees": nb_ignorees}
