"""Chargement et validation de `regles.json`.

Le fichier est la copie conforme de `reference/skill-v1/regles.json` : c'est
lui qui porte les binômes, les praticiens exclusifs, les gabarits horaires et
les couleurs. Il se modifie par PR, jamais depuis l'application.

Toute anomalie lève `ImproperlyConfigured` et, comme le chargement a lieu dans
`ReglesConfig.ready()`, empêche le démarrage : mieux vaut une application qui
ne démarre pas qu'une application qui planifie sur des règles fausses.

Les clés commençant par « _ » sont de la documentation dans le fichier : elles
sont ignorées à tous les niveaux.
"""

import datetime
import json
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from comptes.noms import jour_canonique, normaliser

BRIQUES = ("J", "C")

_CACHE = {}


@dataclass(frozen=True)
class Binome:
    assistante: str
    praticien: str
    exclusif: bool


@dataclass(frozen=True)
class CreneauAdministratif:
    salariee: str
    brique: str


@dataclass(frozen=True)
class PraticienAPart:
    nom: str
    etiquette: str


@dataclass(frozen=True)
class Etudiante:
    nom: str
    gabarit_sans_cours: tuple
    mot_cle_notion: str


@dataclass(frozen=True)
class PeriodeOuverture:
    """Jours d'ouverture du cabinet à partir d'une date. `a_partir_du` nul = origine."""

    a_partir_du: datetime.date
    jours: tuple


@dataclass(frozen=True)
class Regles:
    """Les règles du planning, figées et prêtes à lire."""

    gabarits: dict = field(default_factory=dict)
    periodes_ouverture: tuple = ()
    binomes: tuple = ()
    praticiens_exclusifs: tuple = ()
    creneaux_administratifs: tuple = ()
    couleurs: dict = field(default_factory=dict)
    praticiens_a_part: tuple = ()
    heures_par_brique: dict = field(default_factory=dict)
    etudiantes: tuple = ()
    # Tous les noms cités par le fichier, bruts, dédoublonnés, dans l'ordre
    # d'apparition. C'est sur eux que porte `verifier`.
    noms: tuple = ()


@dataclass(frozen=True)
class RapportRegles:
    """Confrontation des noms du fichier aux personnes en base."""

    total: int
    resolus: int
    non_resolus: tuple


def _refus(message):
    return ImproperlyConfigured(f"regles.json : {message}")


def _sans_doc(valeur):
    """Retire les clés de documentation d'un dict. Laisse le reste intact."""
    if isinstance(valeur, dict):
        return {cle: sous for cle, sous in valeur.items() if not str(cle).startswith("_")}
    return valeur


def _dict(brut, cle):
    valeur = _sans_doc(brut.get(cle, {}))
    if not isinstance(valeur, dict):
        raise _refus(f"« {cle} » doit être un objet")
    return valeur


def _liste(brut, cle):
    """Une section « liste » : soit `{"liste": [...]}`, soit une liste directe."""
    valeur = brut.get(cle, [])
    if isinstance(valeur, dict):
        valeur = _sans_doc(valeur).get("liste", [])
    if not isinstance(valeur, list):
        raise _refus(f"« {cle} » doit être une liste")
    return valeur


def _chaine(valeur, ou):
    if not isinstance(valeur, str) or not valeur.strip():
        raise _refus(f"{ou} : chaîne non vide attendue")
    return valeur.strip()


def _gabarits(brut):
    gabarits = {}
    for cle, valeur in _dict(brut, "gabarits").items():
        try:
            heures = int(cle)
        except (TypeError, ValueError):
            raise _refus(f"gabarits : « {cle} » n'est pas un nombre d'heures") from None
        if not isinstance(valeur, list) or not valeur:
            raise _refus(f"gabarits : « {cle} » doit être une liste non vide")
        for brique in valeur:
            if brique not in BRIQUES:
                raise _refus(
                    f"gabarits : « {cle} » contient « {brique} », attendu J ou C"
                )
        gabarits[heures] = tuple(valeur)
    if not gabarits:
        raise _refus("aucun gabarit")
    return gabarits


def _binomes(brut):
    binomes = []
    for rang, entree in enumerate(_liste(brut, "binomes"), start=1):
        if not isinstance(entree, dict):
            raise _refus(f"binomes : entrée {rang} n'est pas un objet")
        exclusif = entree.get("exclusif", False)
        if not isinstance(exclusif, bool):
            raise _refus(f"binomes : entrée {rang}, « exclusif » doit être un booléen")
        binomes.append(
            Binome(
                assistante=_chaine(entree.get("assistante"), f"binomes, entrée {rang}"),
                praticien=_chaine(entree.get("praticien"), f"binomes, entrée {rang}"),
                exclusif=exclusif,
            )
        )
    return tuple(binomes)


def _exclusifs(brut, binomes):
    exclusifs = []
    praticiens_exclusifs = {
        normaliser(binome.praticien) for binome in binomes if binome.exclusif
    }
    for entree in _liste(brut, "praticiens_exclusifs"):
        nom = _chaine(entree, "praticiens_exclusifs")
        if normaliser(nom) not in praticiens_exclusifs:
            raise _refus(
                f"praticiens_exclusifs : « {nom} » n'est le praticien d'aucun "
                "binôme marqué exclusif"
            )
        exclusifs.append(nom)
    return tuple(exclusifs)


def _creneaux(brut):
    creneaux = []
    for rang, entree in enumerate(_liste(brut, "creneau_administratif"), start=1):
        if not isinstance(entree, dict):
            raise _refus(f"creneau_administratif : entrée {rang} n'est pas un objet")
        brique = entree.get("brique")
        if brique not in BRIQUES:
            raise _refus(
                f"creneau_administratif : entrée {rang}, brique « {brique} » "
                "inconnue (J ou C)"
            )
        creneaux.append(
            CreneauAdministratif(
                salariee=_chaine(
                    entree.get("salariee"), f"creneau_administratif, entrée {rang}"
                ),
                brique=brique,
            )
        )
    return tuple(creneaux)


def _couleurs(brut):
    couleurs = {}
    bruts = []
    for nom, couleur in _dict(brut, "couleurs").items():
        nom = _chaine(nom, "couleurs")
        couleurs[normaliser(nom)] = _chaine(couleur, f"couleurs, « {nom} »")
        bruts.append(nom)
    return couleurs, bruts


def _a_part(brut):
    a_part = []
    for rang, entree in enumerate(_liste(brut, "praticiens_a_part"), start=1):
        if not isinstance(entree, dict):
            raise _refus(f"praticiens_a_part : entrée {rang} n'est pas un objet")
        a_part.append(
            PraticienAPart(
                nom=_chaine(entree.get("nom"), f"praticiens_a_part, entrée {rang}"),
                etiquette=_chaine(
                    entree.get("etiquette"), f"praticiens_a_part, entrée {rang}"
                ),
            )
        )
    return tuple(a_part)


def _heures(brut):
    heures = _dict(brut, "heures_par_brique")
    resultat = {}
    for brique in BRIQUES:
        valeur = heures.get(brique)
        if not isinstance(valeur, (int, float)) or isinstance(valeur, bool) or valeur <= 0:
            raise _refus(
                f"heures_par_brique : « {brique} » doit être un nombre strictement positif"
            )
        resultat[brique] = float(valeur)
    return resultat


def _periodes_ouverture(brut):
    """Périodes d'ouverture datées, dans l'ordre chronologique.

    La PREMIÈRE porte `a_partir_du` nul — c'est le régime d'origine, et c'est
    lui qui garantit qu'une date quelconque trouve toujours une période
    applicable. Les suivantes portent une date, strictement croissante.
    """
    entrees = _liste(brut, "periodes_ouverture")
    if not entrees:
        raise _refus("aucune période d'ouverture")

    periodes = []
    precedente = None
    for rang, entree in enumerate(entrees, start=1):
        if not isinstance(entree, dict):
            raise _refus(f"periodes_ouverture : entrée {rang} n'est pas un objet")

        brute = entree.get("a_partir_du")
        if rang == 1:
            if brute is not None:
                raise _refus(
                    "periodes_ouverture : la première période est celle d'origine, "
                    "son « a_partir_du » doit être nul"
                )
            debut = None
        else:
            if not isinstance(brute, str):
                raise _refus(
                    f"periodes_ouverture : entrée {rang}, « a_partir_du » doit être "
                    "une date AAAA-MM-JJ"
                )
            try:
                debut = datetime.date.fromisoformat(brute)
            except ValueError:
                raise _refus(
                    f"periodes_ouverture : entrée {rang}, « {brute} » n'est pas une "
                    "date AAAA-MM-JJ"
                ) from None
            if precedente is not None and debut <= precedente:
                raise _refus(
                    f"periodes_ouverture : entrée {rang}, les dates doivent être "
                    "strictement croissantes"
                )
            precedente = debut

        bruts = entree.get("jours")
        if not isinstance(bruts, list) or not bruts:
            raise _refus(
                f"periodes_ouverture : entrée {rang}, « jours » doit être une liste "
                "non vide"
            )
        jours = []
        for brut_jour in bruts:
            canonique = jour_canonique(brut_jour) if isinstance(brut_jour, str) else None
            if canonique is None:
                raise _refus(
                    f"periodes_ouverture : entrée {rang}, jour « {brut_jour} » inconnu"
                )
            if canonique in jours:
                raise _refus(
                    f"periodes_ouverture : entrée {rang}, jour « {canonique} » en double"
                )
            jours.append(canonique)

        periodes.append(PeriodeOuverture(a_partir_du=debut, jours=tuple(jours)))

    return tuple(periodes)


def _etudiantes(brut):
    etudiantes = []
    for rang, entree in enumerate(_liste(brut, "etudiantes"), start=1):
        if not isinstance(entree, dict):
            raise _refus(f"etudiantes : entrée {rang} n'est pas un objet")
        gabarit = entree.get("gabarit_sans_cours")
        if not isinstance(gabarit, list) or not gabarit:
            raise _refus(
                f"etudiantes : entrée {rang}, « gabarit_sans_cours » doit être "
                "une liste non vide"
            )
        for brique in gabarit:
            if brique not in BRIQUES:
                raise _refus(
                    f"etudiantes : entrée {rang}, « {brique} » inconnu (J ou C)"
                )
        etudiantes.append(
            Etudiante(
                nom=_chaine(entree.get("nom"), f"etudiantes, entrée {rang}"),
                gabarit_sans_cours=tuple(gabarit),
                mot_cle_notion=_chaine(
                    entree.get("mot_cle_notion"), f"etudiantes, entrée {rang}"
                ),
            )
        )
    return tuple(etudiantes)


def _construire(brut):
    """Valide le contenu déjà décodé et fabrique les `Regles`."""
    if not isinstance(brut, dict):
        raise _refus("objet JSON attendu à la racine")

    gabarits = _gabarits(brut)
    binomes = _binomes(brut)
    exclusifs = _exclusifs(brut, binomes)
    creneaux = _creneaux(brut)
    couleurs, couleurs_brutes = _couleurs(brut)
    a_part = _a_part(brut)
    heures = _heures(brut)
    etudiantes = _etudiantes(brut)
    periodes = _periodes_ouverture(brut)

    noms = []
    for nom in (
        [binome.assistante for binome in binomes]
        + [binome.praticien for binome in binomes]
        + list(exclusifs)
        + [creneau.salariee for creneau in creneaux]
        + couleurs_brutes
        + [praticien.nom for praticien in a_part]
        + [etudiante.nom for etudiante in etudiantes]
    ):
        if nom not in noms:
            noms.append(nom)

    return Regles(
        gabarits=gabarits,
        periodes_ouverture=periodes,
        binomes=binomes,
        praticiens_exclusifs=exclusifs,
        creneaux_administratifs=creneaux,
        couleurs=couleurs,
        praticiens_a_part=a_part,
        heures_par_brique=heures,
        etudiantes=etudiantes,
        noms=tuple(noms),
    )


def charger(chemin=None):
    """Charge les règles, une fois par chemin. Lève `ImproperlyConfigured` si invalide."""
    if chemin is None:
        chemin = settings.REGLES_FICHIER
    cle = str(chemin)
    if cle in _CACHE:
        return _CACHE[cle]

    try:
        with open(chemin, encoding="utf-8-sig") as fichier:
            brut = json.load(fichier)
    except FileNotFoundError:
        raise _refus(f"fichier introuvable ({chemin})") from None
    except ValueError:
        raise _refus("JSON illisible") from None

    regles = _construire(brut)
    _CACHE[cle] = regles
    return regles


def couleur_de(nom):
    """Couleur d'une personne d'après les règles. Chaîne vide si elle n'y figure pas."""
    return charger().couleurs.get(normaliser(nom), "")


def jours_ouverture(jour, regles=None):
    """Jours d'ouverture du cabinet applicables à cette date.

    On retient la DERNIÈRE période dont la date de début est déjà passée. La
    période d'origine (`a_partir_du` nul) garantit qu'il y en a toujours une.
    """
    periodes = (regles or charger()).periodes_ouverture
    applicable = periodes[0]
    for periode in periodes[1:]:
        if periode.a_partir_du <= jour:
            applicable = periode
        else:
            break
    return applicable.jours


def verifier(personnes):
    """Confronte les noms du fichier aux personnes fournies.

    Un nom est résolu si une personne porte le même « NOM Prénom » une fois
    normalisé. Les non résolus signalent un fichier de règles en retard sur la
    fiche personnel (départ, mariage, faute de frappe).
    """
    connus = {normaliser(f"{p.nom} {p.prenom}") for p in personnes}
    non_resolus = tuple(nom for nom in charger().noms if normaliser(nom) not in connus)
    total = len(charger().noms)
    return RapportRegles(
        total=total, resolus=total - len(non_resolus), non_resolus=non_resolus
    )
