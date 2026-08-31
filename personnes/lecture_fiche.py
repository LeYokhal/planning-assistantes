"""Lecture d'un export JSON de la fiche personnel Notion.

Cinq colonnes, pas une de plus. La fiche Notion porte aussi le numéro de
sécurité sociale, la date de naissance, le téléphone, l'IBAN : ces colonnes
n'ont rien à faire dans l'application, et un export fait au `SELECT *` doit
être refusé en bloc plutôt que trié en silence. C'est le sens de la garde
« colonnes inattendues » — et la raison pour laquelle son message ne cite que
des NOMS de colonnes, jamais une valeur.

Une ligne hors convention n'invalide pas le fichier : elle est ignorée avec son
motif, et le rapport d'import les liste. Seule la forme du fichier lui-même
(JSON illisible, colonnes) provoque un refus total.
"""

import json
from dataclasses import dataclass, field

from comptes.models import Personne
from comptes.noms import decouper_nom_prenom, jour_canonique, normaliser

COLONNES = (
    "Name",
    "Department",
    "Planning",
    "Heures hebdomadaire",
    "Jours de travail",
)

DEPARTEMENTS = {
    "assistante": Personne.RoleMetier.ASSISTANTE,
    "praticien": Personne.RoleMetier.PRATICIEN,
    "secretariat": Personne.RoleMetier.SECRETAIRE,
}

# Notion exporte ses cases à cocher sous ces libellés.
VRAI = ("__YES__", True)
FAUX = ("__NO__", False, None)

MOTIF_DEPARTEMENT = "département inconnu"
MOTIF_CONVENTION = "hors convention NOM Prénom"
MOTIF_PLANNING = "planning illisible"
MOTIF_HEURES = "heures illisibles"
MOTIF_JOURS = "jours de travail invalides"


class FicheInvalide(Exception):
    """Le fichier lui-même est refusé : rien n'en sera importé."""


@dataclass(frozen=True)
class LigneFiche:
    """Une ligne exploitable de la fiche."""

    numero: int
    nom: str
    prenom: str
    role_metier: str
    planifiee: bool
    heures: int | None
    jours: tuple


@dataclass
class LectureFiche:
    """Résultat d'une lecture : ce qui est exploitable, et ce qui a été écarté.

    `ignorees` porte `(numero, libelle_court, motif)`. Le libellé est le nom
    complet tel que lu — il sert à l'écran, pour que le cabinet retrouve la
    ligne dans Notion, et n'entre jamais dans le journal d'audit.
    """

    lignes: list = field(default_factory=list)
    ignorees: list = field(default_factory=list)


def _resultats(brut):
    """Accepte `{"results": [...]}` (copié de Notion) ou une liste directe."""
    if isinstance(brut, dict):
        resultats = brut.get("results")
        if not isinstance(resultats, list):
            raise FicheInvalide("forme inconnue")
        return resultats
    if isinstance(brut, list):
        return brut
    raise FicheInvalide("forme inconnue")


def _controler_colonnes(lignes):
    """Refuse le fichier entier si les colonnes ne sont pas exactement les cinq.

    Ne cite QUE des noms de colonnes : le message peut finir dans un log ou une
    capture d'écran.
    """
    attendues = set(COLONNES)
    for ligne in lignes:
        if not isinstance(ligne, dict):
            raise FicheInvalide("forme inconnue")
        recues = set(ligne)
        inattendues = recues - attendues
        if inattendues:
            raise FicheInvalide(
                "colonnes inattendues : " + ", ".join(sorted(inattendues))
            )
        manquantes = attendues - recues
        if manquantes:
            raise FicheInvalide(
                "colonnes manquantes : " + ", ".join(sorted(manquantes))
            )


def _planifiee(valeur):
    """Case « Planning » de Notion. `None` si la valeur n'est pas interprétable."""
    if valeur in VRAI:
        return True
    if valeur in FAUX:
        return False
    return None


def _heures(valeur):
    """Heures hebdomadaires : entier ou rien. `False` (booléen) n'est pas 0."""
    if valeur is None:
        return True, None
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return False, None
    return True, valeur


def _jours(valeur):
    """Jours de travail : liste canonique, ou `(False, ())` si illisible."""
    if valeur is None or valeur == "":
        return True, ()
    if isinstance(valeur, str):
        try:
            valeur = json.loads(valeur)
        except ValueError:
            return False, ()
    if not isinstance(valeur, list):
        return False, ()

    jours = []
    for brut in valeur:
        if not isinstance(brut, str):
            return False, ()
        canonique = jour_canonique(brut)
        if canonique is None:
            return False, ()
        jours.append(canonique)
    return True, tuple(jours)


def lire(contenu):
    """Lit les octets d'un export et renvoie une `LectureFiche`.

    Lève `FicheInvalide` si le fichier n'est pas exploitable du tout.
    """
    try:
        brut = json.loads(contenu.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise FicheInvalide("JSON illisible") from None

    resultats = _resultats(brut)
    _controler_colonnes(resultats)

    lecture = LectureFiche()
    for numero, entree in enumerate(resultats, start=1):
        libelle = str(entree.get("Name") or "").strip()

        role = DEPARTEMENTS.get(normaliser(entree.get("Department")))
        if role is None:
            lecture.ignorees.append((numero, libelle, MOTIF_DEPARTEMENT))
            continue

        decoupe = decouper_nom_prenom(libelle)
        if decoupe is None:
            lecture.ignorees.append((numero, libelle, MOTIF_CONVENTION))
            continue
        nom, prenom = decoupe

        planifiee = _planifiee(entree.get("Planning"))
        if planifiee is None:
            lecture.ignorees.append((numero, libelle, MOTIF_PLANNING))
            continue

        heures_ok, heures = _heures(entree.get("Heures hebdomadaire"))
        if not heures_ok:
            lecture.ignorees.append((numero, libelle, MOTIF_HEURES))
            continue

        jours_ok, jours = _jours(entree.get("Jours de travail"))
        if not jours_ok:
            lecture.ignorees.append((numero, libelle, MOTIF_JOURS))
            continue

        lecture.lignes.append(
            LigneFiche(
                numero=numero,
                nom=nom,
                prenom=prenom,
                role_metier=role,
                planifiee=planifiee,
                heures=heures,
                jours=jours,
            )
        )

    return lecture
