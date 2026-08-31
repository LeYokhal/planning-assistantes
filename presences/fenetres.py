"""Plage d'un mois et fenêtres d'appel S7.

Port exact de `plage()` du skill v1
(`reference/skill-v1/scripts/build_planning.py`) : le planning se lit en semaines
complètes lundi → dimanche, et l'outil S7 plafonne un appel à 31 jours, d'où une
ou deux fenêtres par mois.

Tout ici est du calendrier pur : aucune requête, aucun accès à la base.
"""

import calendar
import datetime
import re
from dataclasses import dataclass

MOIS_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

MOIS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

FENETRE_MAX_JOURS = 31


@dataclass(frozen=True)
class Plage:
    """Plage affichée d'un mois, et fenêtres d'appel qui la couvrent."""

    mois: str
    debut: datetime.date
    fin: datetime.date
    fenetres: tuple


def _annee_et_numero(mois):
    """Découpe « AAAA-MM » en `(année, numéro)`, ou lève `ValueError`."""
    if not isinstance(mois, str) or not MOIS_RE.match(mois):
        raise ValueError("mois invalide")
    annee, numero = mois.split("-")
    return int(annee), int(numero)


def plage_mois(mois):
    """Renvoie la `Plage` du mois « AAAA-MM ».

    Début = lundi de la semaine du 1er, fin = dimanche de la semaine du dernier
    jour (28, 35 ou 42 jours), fenêtres de 31 jours au plus, contiguës.
    """
    annee, numero = _annee_et_numero(mois)
    premier = datetime.date(annee, numero, 1)
    dernier = datetime.date(annee, numero, calendar.monthrange(annee, numero)[1])
    debut = premier - datetime.timedelta(days=premier.weekday())
    fin = dernier + datetime.timedelta(days=6 - dernier.weekday())

    fenetres = []
    courant = debut
    while courant <= fin:
        arret = min(courant + datetime.timedelta(days=FENETRE_MAX_JOURS - 1), fin)
        fenetres.append((courant, arret))
        courant = arret + datetime.timedelta(days=1)

    return Plage(mois=mois, debut=debut, fin=fin, fenetres=tuple(fenetres))


def mois_precedent(mois):
    """« 2026-01 » → « 2025-12 »."""
    annee, numero = _annee_et_numero(mois)
    if numero == 1:
        return f"{annee - 1}-12"
    return f"{annee}-{numero - 1:02d}"


def mois_suivant(mois):
    """« 2026-12 » → « 2027-01 »."""
    annee, numero = _annee_et_numero(mois)
    if numero == 12:
        return f"{annee + 1}-01"
    return f"{annee}-{numero + 1:02d}"


def libelle_mois(mois):
    """« 2026-10 » → « octobre 2026 »."""
    annee, numero = _annee_et_numero(mois)
    return f"{MOIS_FR[numero - 1]} {annee}"


def _cle_mois(date):
    """« AAAA-MM » d'une date."""
    return f"{date.year}-{date.month:02d}"


def mois_de_fenetre(debut, fin):
    """Renvoie le mois « AAAA-MM » auquel appartient la fenêtre `debut`→`fin`.

    Une fenêtre déborde volontiers sur le mois voisin (semaines complètes) : la
    première fenêtre d'octobre 2026 commence le 28 septembre. On cherche donc
    d'abord le mois dont `plage_mois` produit exactement cette fenêtre — c'est le
    cas de tout fichier issu d'un appel calé sur un mois. À défaut (fenêtre
    quelconque), on retient le mois qui compte le plus de jours dans la fenêtre,
    l'égalité étant tranchée par l'ordre chronologique.
    """
    # Le mois propriétaire peut précéder celui de `debut` : la fenêtre
    # (2027-04-01 → 2027-04-04) est la seconde fenêtre de mars 2027.
    candidats = []
    courant = mois_precedent(_cle_mois(debut))
    dernier = _cle_mois(fin)
    while True:
        candidats.append(courant)
        if courant == dernier:
            break
        courant = mois_suivant(courant)

    for candidat in candidats:
        if (debut, fin) in plage_mois(candidat).fenetres:
            return candidat

    compte = {}
    for decalage in range((fin - debut).days + 1):
        cle = _cle_mois(debut + datetime.timedelta(days=decalage))
        compte[cle] = compte.get(cle, 0) + 1
    # `compte` est construit dans l'ordre chronologique : `max` conserve le
    # premier en cas d'égalité.
    return max(compte, key=compte.get)
