"""Import d'un planning historique (brique 7a, C7.1).

Reprise **exceptionnelle** des plannings de janvier à août 2026, produits hors
de l'application au format de l'export JSON de la page (`moteur.exporter`), pour
lesquels aucune présence Doctolib n'a jamais été importée. Un fichier = un mois =
**une** `PlanningVersion` publiée et marquée « historique ».

Ce module est un chemin d'écriture **entièrement distinct** de `services.publier` :

* **aucune revérification des règles.** `verifier(DATA, state)` est inapplicable
  ici : sans import de présences, `DATA.jours` est vide et *toutes* les briques
  deviendraient `praticien_absent` / `sans_donnees`. La règle n'est pas
  contournée, elle est sans objet — le rapport d'analyse le dit à l'écran ;
* **aucun webhook.** `services.publier` appelle `webhooks.notifier_publication` ;
  un import historique ne doit pas déclencher le mail « planning publié » de mars
  2026 quand la brique 5 existera (C7.6). Cela s'obtient en ne passant pas par
  `publier`, pas en le modifiant ;
* **aucun filtre d'activité** à la résolution des codes (C7.4) : les fiches
  praticien fermées, sans agenda Doctolib, gardent leur colonne.

`analyser` ne fait que lire : ni base, ni audit, ni log. `executer` écrit une
ligne et un événement, en tout ou rien.

⚠️ **Décision D2-a** (arbitrée le 08/09/2026, grep préalable) : `verifications`
ne porte **pas** `verifie_le` — rien n'a été vérifié, et l'écrire serait un
mensonge. Le grep de `verifie_le` sur tout le dépôt ne trouve qu'un écrivain
(`services.publier`), un commentaire (`models.py`) et l'assertion du chemin
normal (`test_publication.py`) : aucun lecteur ne casse.

⚠️ Le journal et les logs ne portent que le mois, un numéro et des comptages :
jamais un nom, jamais un type d'absence. Les **codes** de personnes (`lea_deh`)
apparaissent dans le rapport à l'écran — ils sont nécessaires pour corriger un
fichier, et ce ne sont pas des données personnelles au sens du cadrage.
"""

import datetime
import hashlib
import json
import logging
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser
from comptes.models import Personne
from presences.fenetres import plage_mois
from socle.feries import feries_entre

from . import services
from .models import PlanningVersion
from .verification import BRIQUES, MISC, nettoyer

logger = logging.getLogger(__name__)

# ~40 jours de briques tiennent en quelques dizaines de Ko : 1 Mo laisse la même
# marge large que la 3-quater (`absences/forms.py`).
TAILLE_MAX_IMPORT = 1024 * 1024

CLES_RACINE = ("mois", "affectations", "feries", "feries_off", "notes")
# `numero` et `exporte`, présents dans l'export de la page, sont acceptés et
# ignorés : le numéro est décidé par le serveur.
CHAMPS_BRIQUE = ("a", "s", "t", "x")

VERDICT_CREER = "creer"
VERDICT_DEJA_PRESENTE = "deja_presente"
VERDICT_REFUSE = "refuse"

LIBELLES_VERDICTS = {
    VERDICT_CREER: "à importer",
    VERDICT_DEJA_PRESENTE: "déjà présente",
    VERDICT_REFUSE: "refusé",
}


class ActionImpossible(Exception):
    """L'écriture est refusée (décision D5). Le message est montré tel quel."""


@dataclass
class Analyse:
    """Rapport d'analyse d'un fichier. Aucune écriture ne l'a produit.

    `state` est l'état nettoyé prêt à écrire ; `empreinte` est le SHA-256 du
    couple `(mois, state)` sérialisé canoniquement — stable d'un ré-export à
    l'autre, contrairement à celui des octets reçus, puisque `exporte` change à
    chaque export de la page.
    """

    mois: str = ""
    verdict: str = VERDICT_REFUSE
    state: dict = field(default_factory=dict)
    empreinte: str = ""
    debut: str = ""
    fin: str = ""
    nb_jours: int = 0
    nb_briques: int = 0
    numero_courant: int = 0
    colonnes: list = field(default_factory=list)
    personnes: list = field(default_factory=list)
    erreurs: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)

    @property
    def verdict_libelle(self):
        return LIBELLES_VERDICTS[self.verdict]

    @property
    def peut_confirmer(self):
        return self.verdict == VERDICT_CREER


def empreinte_de(mois, state):
    """SHA-256 du couple `(mois, state)` sérialisé canoniquement.

    `sort_keys` neutralise l'ordre des clés (le passage par la base le change) ;
    l'ordre des briques d'une journée, lui, est significatif et conservé.
    """
    canonique = json.dumps(
        {"mois": mois, "state": state},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def _date_iso(valeur):
    """Vrai si la valeur est une date « AAAA-MM-JJ » lisible."""
    if not isinstance(valeur, str) or len(valeur) != 10:
        return False
    try:
        return datetime.date.fromisoformat(valeur).isoformat() == valeur
    except ValueError:
        return False


def _structure(fichier):
    """Contrôle la forme du fichier et rend `(mois, plage, erreurs)`.

    Les messages ne citent que des dates, des noms de champ et des rangs : jamais
    une valeur. `plage` est `None` dès que le mois est illisible.
    """
    erreurs = []
    if not isinstance(fichier, dict):
        return None, None, ["Le fichier doit être un objet JSON."]

    manquantes = [cle for cle in CLES_RACINE if cle not in fichier]
    if manquantes:
        erreurs.append(
            "Clés absentes de la racine : " + ", ".join(f"« {c} »" for c in manquantes)
        )

    mois = fichier.get("mois")
    plage = None
    if not isinstance(mois, str):
        erreurs.append("Champ « mois » absent ou illisible (attendu « AAAA-MM »).")
        mois = None
    else:
        try:
            plage = plage_mois(mois)
        except ValueError:
            erreurs.append(f"Mois « {mois} » illisible (attendu « AAAA-MM »).")
            mois = None

    affectations = fichier.get("affectations")
    if not isinstance(affectations, dict):
        erreurs.append("Champ « affectations » absent ou illisible (objet attendu).")
        return mois, plage, erreurs

    for iso in sorted(affectations):
        if not _date_iso(iso):
            erreurs.append(f"Clé « {iso} » d'affectations : date illisible.")
            continue
        slots = affectations[iso]
        if not isinstance(slots, dict):
            erreurs.append(f"{iso} : la journée doit être un objet de colonnes.")
            continue
        for slot in sorted(slots):
            briques = slots[slot]
            if not isinstance(briques, list):
                erreurs.append(f"{iso} / « {slot} » : liste de briques attendue.")
                continue
            for rang, brique in enumerate(briques, start=1):
                erreurs.extend(_erreurs_brique(iso, slot, rang, brique))

    for cle, attendu in (("feries", dict), ("feries_off", list), ("notes", dict)):
        if cle in fichier and not isinstance(fichier[cle], attendu):
            erreurs.append(f"Champ « {cle} » illisible.")

    return mois, plage, erreurs


def _erreurs_brique(iso, slot, rang, brique):
    """Forme d'une brique : `{a, s, t, x}`, `t` dans J | C. Aucune valeur citée."""
    prefixe = f"{iso} / « {slot} » / brique {rang}"
    if not isinstance(brique, dict):
        return [f"{prefixe} : objet attendu."]
    erreurs = []
    manquants = [champ for champ in CHAMPS_BRIQUE if champ not in brique]
    if manquants:
        erreurs.append(
            f"{prefixe} : champ(s) " + ", ".join(f"« {c} »" for c in manquants) + " absent(s)."
        )
    if not isinstance(brique.get("s"), str) or not brique.get("s").strip():
        erreurs.append(f"{prefixe} : champ « s » vide ou illisible.")
    if brique.get("t") not in BRIQUES:
        erreurs.append(f"{prefixe} : champ « t » hors {' | '.join(BRIQUES)}.")
    for champ in ("x", "a"):
        if champ in brique and not isinstance(brique[champ], bool):
            erreurs.append(f"{prefixe} : champ « {champ} » non booléen.")
    return erreurs


def _resoudre(state, plage):
    """Résout colonnes et codes de briques, et rend `(colonnes, personnes, erreurs, avertissements)`.

    ⚠️ Aucun filtre `actif` ni `planifiee` (C7.4) : une fiche praticien fermée,
    sans agenda Doctolib, garde sa colonne — c'est tout l'objet de la décision.
    """
    connues = {p.code: p for p in Personne.objects.exclude(code=None).exclude(code="")}
    erreurs, avertissements = [], []

    par_slot = {}
    par_code = {}
    inconnus_slots, inconnus_codes = set(), set()
    feries = {jour.isoformat() for jour in feries_entre(plage.debut, plage.fin)}
    fermes = set(state["feries"]) | feries
    fermes -= set(state["feries_off"])

    for iso in sorted(state["affectations"]):
        if not (plage.debut.isoformat() <= iso <= plage.fin.isoformat()):
            erreurs.append(
                f"{iso} : jour hors de la plage du mois "
                f"({plage.debut.isoformat()} au {plage.fin.isoformat()})."
            )
            continue
        vus_du_jour = {}
        porte_une_brique = False
        for slot, briques in sorted(state["affectations"][iso].items()):
            if not briques:
                continue
            porte_une_brique = True
            entree = par_slot.setdefault(
                slot,
                {
                    "slot": slot,
                    "libelle": services.LIBELLES_MISC.get(slot) or "",
                    "genre": "misc" if slot in MISC else "praticien",
                    "nb_briques": 0,
                    "codes": set(),
                    "inactive": False,
                    "non_planifiee": False,
                    "sans_agenda": False,
                },
            )
            if slot not in MISC:
                personne = connues.get(slot)
                if personne is None:
                    entree["genre"] = "inconnu"
                    inconnus_slots.add(slot)
                else:
                    entree["libelle"] = str(personne)
                    entree["inactive"] = not personne.actif
                    entree["non_planifiee"] = not personne.planifiee
                    entree["sans_agenda"] = not (personne.agenda_doctolib or "").strip()
            entree["nb_briques"] += len(briques)

            for brique in briques:
                code = brique["s"]
                entree["codes"].add(code)
                personne = connues.get(code)
                if personne is None:
                    inconnus_codes.add(code)
                fiche = par_code.setdefault(
                    code,
                    {
                        "code": code,
                        "libelle": str(personne) if personne else "",
                        "nb_briques": 0,
                        "jours": set(),
                        "inactive": bool(personne) and not personne.actif,
                        "non_planifiee": bool(personne) and not personne.planifiee,
                        "connue": personne is not None,
                    },
                )
                fiche["nb_briques"] += 1
                fiche["jours"].add(iso)
                vus_du_jour.setdefault(code, []).append(slot)

        if porte_une_brique and iso in fermes:
            avertissements.append(
                f"{iso} : jour fermé ou férié, mais il porte des briques."
            )
        for code, slots in sorted(vus_du_jour.items()):
            if len(slots) > 1:
                erreurs.append(
                    f"{iso} : « {code} » posé {len(slots)} fois "
                    f"({', '.join(slots)}) — un seul poste par jour."
                )

    for code in sorted(inconnus_slots):
        erreurs.append(f"Colonne « {code} » : aucune fiche ne porte ce code.")
    for code in sorted(inconnus_codes):
        erreurs.append(f"Brique « {code} » : aucune fiche ne porte ce code.")

    colonnes = sorted(
        par_slot.values(), key=lambda c: (c["genre"] != "praticien", c["libelle"], c["slot"])
    )
    for colonne in colonnes:
        colonne["codes"] = sorted(colonne["codes"])
        colonne["libelle"] = colonne["libelle"] or colonne["slot"]
        if colonne["inactive"] or colonne["non_planifiee"]:
            avertissements.append(
                f"Colonne « {colonne['slot']} » : fiche "
                + ("close" if colonne["inactive"] else "non planifiée")
                + " — colonne conservée (C7.4)."
            )

    personnes = sorted(par_code.values(), key=lambda p: (not p["connue"], p["code"]))
    for fiche in personnes:
        fiche["nb_jours"] = len(fiche.pop("jours"))
        fiche["libelle"] = fiche["libelle"] or fiche["code"]

    return colonnes, personnes, erreurs, avertissements


def analyser(fichier):
    """Rapport d'analyse d'un fichier de planning historique. **N'écrit rien.**

    `fichier` est l'objet JSON décodé par `forms.FormulaireImportHistorique`.
    Rend une `Analyse` dont le `verdict` vaut :

    * `refuse` — forme invalide, code inconnu (colonne ou brique), jour hors de
      la plage des semaines du mois, même personne deux fois le même jour, ou
      mois déjà couvert par une version **non historique** (décision D1-1) ;
    * `deja_presente` — le mois n'a que des versions historiques et la dernière
      porte exactement cet état (décision D1-2) : rien à écrire ;
    * `creer` — sinon. Un mois déjà historique mais différent reçoit une version
      **suivante**, voie de correction puisque `PlanningVersion` est en lecture
      seule (décision D1-3).

    Un jour fermé ou férié porteur de briques est un **avertissement**, pas un
    refus : le cabinet a pu ouvrir exceptionnellement.
    """
    mois, plage, erreurs = _structure(fichier)
    if plage is None or erreurs:
        return Analyse(mois=mois or "", verdict=VERDICT_REFUSE, erreurs=erreurs)

    state = nettoyer(fichier)
    colonnes, personnes, erreurs, avertissements = _resoudre(state, plage)
    nb_jours = sum(
        1 for slots in state["affectations"].values() if any(slots.values())
    )
    analyse = Analyse(
        mois=mois,
        state=state,
        empreinte=empreinte_de(mois, state),
        debut=plage.debut.isoformat(),
        fin=plage.fin.isoformat(),
        nb_jours=nb_jours,
        nb_briques=services.nb_briques(state),
        colonnes=colonnes,
        personnes=personnes,
        erreurs=erreurs,
        avertissements=avertissements,
    )

    versions = list(PlanningVersion.objects.filter(mois=mois).order_by("-numero"))
    analyse.numero_courant = versions[0].numero if versions else 0
    vivantes = [v for v in versions if not services.est_historique(v)]
    if vivantes:
        analyse.erreurs.append(
            f"Ce mois porte déjà une version enregistrée dans l'application "
            f"(v{vivantes[0].numero}) : l'import historique est refusé."
        )
    elif versions and empreinte_de(mois, nettoyer(versions[0].state)) == analyse.empreinte:
        analyse.verdict = VERDICT_DEJA_PRESENTE
        return analyse

    if analyse.erreurs:
        analyse.verdict = VERDICT_REFUSE
    elif not analyse.nb_briques:
        analyse.erreurs.append("Le fichier ne porte aucune brique.")
        analyse.verdict = VERDICT_REFUSE
    else:
        analyse.verdict = VERDICT_CREER
    return analyse


def executer(analyse, qui):
    """Écrit la version historique décrite par `analyse` et la renvoie.

    Rend `None` sans rien écrire si l'analyse conclut « déjà présente » (D1-2) :
    la garde n'est pas seulement dans le gabarit. Lève `ActionImpossible` sur un
    rapport refusé, ou si une version du mois est apparue entre l'analyse rejouée
    et l'insertion (contrainte unique `(mois, numero)`, patron de
    `services.enregistrer` : l'`IntegrityError` est attrapée **hors** du bloc).

    ⚠️ Ni `verifier`, ni webhook : voir la docstring du module.

    `qui` est le compte cabinet ; il ne figure dans l'audit que par la clé
    étrangère de l'événement.
    """
    if analyse.verdict == VERDICT_REFUSE:
        raise ActionImpossible(
            f"{len(analyse.erreurs)} refus dans le rapport : rien n'est importé "
            "tant que le fichier n'est pas corrigé."
        )
    if analyse.verdict == VERDICT_DEJA_PRESENTE:
        return None

    auteur = qui if getattr(qui, "is_authenticated", False) else None
    maintenant = timezone.now()
    try:
        with transaction.atomic():
            version = PlanningVersion.objects.create(
                mois=analyse.mois,
                numero=analyse.numero_courant + 1,
                state=analyse.state,
                version_de_base=analyse.numero_courant,
                auteur=auteur,
                publiee=True,
                publie_le=maintenant,
                publie_par=auteur,
                verifications={
                    "historique": True,
                    "importe_le": maintenant.isoformat(),
                    "empreinte": analyse.empreinte,
                    # Aucune présence Doctolib : C6.9 n'a aucun marqueur
                    # d'effectif à calculer pour ce mois.
                    "imports": [],
                    "nb_briques": analyse.nb_briques,
                    "nb_jours": analyse.nb_jours,
                },
            )
            journaliser(
                Action.PLANNING_HISTORIQUE_IMPORTE,
                qui=qui,
                objet=version,
                mois=analyse.mois,
                numero=version.numero,
                nb_briques=analyse.nb_briques,
                nb_jours=analyse.nb_jours,
                empreinte=analyse.empreinte,
            )
    except IntegrityError:
        raise ActionImpossible(
            "Une version de ce mois a été enregistrée entre-temps : "
            "téléversez le fichier à nouveau."
        ) from None

    logger.info(
        "planning historique %s : version %s importee (%s briques, %s jours)",
        analyse.mois,
        version.numero,
        analyse.nb_briques,
        analyse.nb_jours,
    )
    return version
