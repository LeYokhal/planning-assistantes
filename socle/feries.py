"""Jours fériés français.

Port de `paques()` et `feries_fr()` du skill v1
(`reference/skill-v1/scripts/build_planning.py:32-50`), qui reste non exécuté par
l'application. Le calcul de Pâques est l'algorithme de Meeus/Jones/Butcher,
recopié tel quel : il est exact de 1583 à 4099, et il n'a aucune raison de
changer.

Module volontairement PUR : aucun accès à la base, aucun réglage, aucune
dépendance Django. Les jours comptés (brique 3) et le planning (brique 4) en ont
besoin autant l'un que l'autre, d'où sa place dans `socle`.

Les onze fériés retenus sont ceux du régime général métropolitain. Le cabinet
n'est pas en Alsace-Moselle : ni Vendredi saint ni Saint-Étienne.
"""

import datetime
import functools

NOMS = {
    "jour_de_l_an": "Jour de l'an",
    "lundi_de_paques": "Lundi de Pâques",
    "fete_du_travail": "Fête du Travail",
    "victoire_1945": "Victoire 1945",
    "ascension": "Ascension",
    "lundi_de_pentecote": "Lundi de Pentecôte",
    "fete_nationale": "Fête nationale",
    "assomption": "Assomption",
    "toussaint": "Toussaint",
    "armistice": "Armistice",
    "noel": "Noël",
}


def paques(annee):
    """Dimanche de Pâques de l'année, par l'algorithme de Meeus/Jones/Butcher."""
    a = annee % 19
    b = annee // 100
    c = annee % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mois = (h + m - 7 * n + 114) // 31
    jour = ((h + m - 7 * n + 114) % 31) + 1
    return datetime.date(annee, mois, jour)


@functools.lru_cache(maxsize=32)
def feries_annee(annee):
    """Dictionnaire `date -> libellé` des onze fériés d'une année.

    Mis en cache : le calcul est pur, et le calcul des jours comptés interroge
    la même année des dizaines de fois d'affilée.
    """
    dimanche = paques(annee)
    return {
        datetime.date(annee, 1, 1): NOMS["jour_de_l_an"],
        dimanche + datetime.timedelta(days=1): NOMS["lundi_de_paques"],
        datetime.date(annee, 5, 1): NOMS["fete_du_travail"],
        datetime.date(annee, 5, 8): NOMS["victoire_1945"],
        dimanche + datetime.timedelta(days=39): NOMS["ascension"],
        dimanche + datetime.timedelta(days=50): NOMS["lundi_de_pentecote"],
        datetime.date(annee, 7, 14): NOMS["fete_nationale"],
        datetime.date(annee, 8, 15): NOMS["assomption"],
        datetime.date(annee, 11, 1): NOMS["toussaint"],
        datetime.date(annee, 11, 11): NOMS["armistice"],
        datetime.date(annee, 12, 25): NOMS["noel"],
    }


def est_ferie(jour):
    """Vrai si cette date est un jour férié."""
    return jour in feries_annee(jour.year)


def nom_ferie(jour):
    """Libellé du férié, ou chaîne vide si le jour n'en est pas un."""
    return feries_annee(jour.year).get(jour, "")


def feries_entre(debut, fin):
    """Dictionnaire `date -> libellé` des fériés de la plage, bornes comprises.

    La plage peut chevaucher deux années : les deux sont interrogées.
    """
    trouves = {}
    for annee in range(debut.year, fin.year + 1):
        for jour, nom in feries_annee(annee).items():
            if debut <= jour <= fin:
                trouves[jour] = nom
    return trouves
