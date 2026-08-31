"""Normalisation des noms et des jours, partagée par la brique 2.

Port du skill v1 (`reference/skill-v1/scripts/build_planning.py`), qui reste
non exécuté par l'application. Deux fonctions y coexistaient sous le même nom :
celle de `build_planning.py` retire les segments entre parenthèses (suffixe
« (Villecresnes) » des agendas Doctolib), celle de `prepare_inputs.py` non.
C'est la PREMIÈRE qui est portée ici — sans elle, un agenda suffixé ne
s'apparie jamais.

Ajout par rapport au skill : les titres (« Dr », « Docteur ») sont retirés. Les
agendas Doctolib en portent, la fiche personnel non.
"""

import re
import unicodedata

JOURS_FR = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")

TITRES = frozenset({"dr", "docteur"})

# Un nom de famille de la fiche : majuscules (accentuées comprises), traits
# d'union, apostrophes. « DA VEIGA MONTEIRO » en est trois, « Dilsa » aucun.
_MOT_NOM = re.compile(r"^[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]*$")

_JOURS_PAR_CLE = None


def normaliser(texte):
    """Réduit un nom à sa forme comparable : « Dr Amelie DUPONT (Villecresnes) » → « amelie dupont ».

    Accents retirés (NFKD puis suppression des combinants, donc formes composée
    et décomposée donnent le même résultat), segments entre parenthèses
    supprimés, tout ce qui n'est ni lettre ni espace remplacé par un espace,
    casse repliée, espaces réduits, titres retirés.
    """
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\(.*?\)", " ", s)          # suffixes « (Villecresnes) »
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    mots = [mot for mot in s.casefold().split() if mot not in TITRES]
    return " ".join(mots)


def code_pour(prenom, nom):
    """Identifiant stable et sans espace : prénom + « _ » + 3 lettres du nom.

    Port de `ident()` du skill. Deux personnes de même prénom dont les noms
    partagent leurs trois premières lettres obtiennent le même code : l'unicité
    de `Personne.code` fait foi, l'appelant traite la collision (voir
    `Personne.save`).
    """
    debut = re.sub(r"[^a-z]", "", normaliser(prenom))
    fin = re.sub(r"[^a-z]", "", normaliser(nom))[:3]
    if not debut or not fin:
        return ""
    return f"{debut}_{fin}"


def decouper_nom_prenom(nom_complet):
    """Découpe « NOM Prénom » en `(nom, prénom)`, ou renvoie None.

    Convention de la colonne `Name` de la fiche personnel : le nom de famille
    est en majuscules et peut compter plusieurs mots, le prénom est le dernier
    mot. Une ligne hors convention (« New team member », « Dupont ») n'est pas
    devinée : elle est renvoyée à l'appelant qui l'ignorera en le disant.
    """
    mots = (nom_complet or "").split()
    if len(mots) < 2:
        return None
    if not all(_MOT_NOM.match(mot) for mot in mots[:-1]):
        return None
    return " ".join(mots[:-1]), mots[-1]


def jour_canonique(texte):
    """« mardi », « MARDI », « Mardi  » → « Mardi ». Jour inconnu → None."""
    global _JOURS_PAR_CLE
    if _JOURS_PAR_CLE is None:
        _JOURS_PAR_CLE = {normaliser(jour): jour for jour in JOURS_FR}
    return _JOURS_PAR_CLE.get(normaliser(texte))
