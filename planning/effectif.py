"""Marqueurs d'effectif d'une version publiée (brique 6b, C6.9).

`calculer(data, state)` rend, pour chaque jour couvert de la plage, un compte-rendu
`{"moins", "plus", "ouvert"}` : « − » quand un praticien présent n'a aucune
assistante dans sa colonne (D6b.12), « + » quand la case « sureffectif » porte au
moins une brique hors heures sup (D6b.14), `ouvert` faux un jour férié du
calendrier ou un jour de semaine que le planning n'affiche pas — aucun marqueur
ces jours-là (D6b.13). Un jour sans import de présences (`meta.non_couverts`) n'a
pas d'entrée : « pas d'entrée » signifie exactement « présences non importées ».

Module pur : aucune requête. « Présent » et « jour affiché » sont les définitions
du moteur, par `planning.verification._Lecture` — nom privé réutilisé sciemment,
`verification.py` intouché, aucun cycle (il n'importe que la bibliothèque
standard). Le férié est celui du calendrier seul (`data["feries"]`) : les ponts
ajoutés et les fériés rouverts dans la page sont ignorés, écart au moteur assumé
(revue 4.1 (b)).

Le compte-rendu ne porte que des dates ISO et des booléens : jamais un nom,
jamais un type d'absence. `lire(version)` le relit sans jamais lever.
"""

import datetime

from .verification import _Lecture, nettoyer

SLOT_SUREFFECTIF = "sureffectif"


def _briques(slots, slot):
    """Les briques d'une case ; liste vide si la case manque ou n'est pas une liste."""
    briques = slots.get(slot)
    return briques if isinstance(briques, list) else []


def calculer(data, state):
    """`{"jours": {iso: {"moins": bool, "plus": bool, "ouvert": bool}}}`, dates triées."""
    propre = nettoyer(state)
    lecture = _Lecture(data, propre)
    meta = data["meta"]
    non_couverts = set(meta.get("non_couverts") or [])
    feries = data.get("feries") or {}
    praticiens = data.get("praticiens") or []
    affectations = propre["affectations"]

    jours = {}
    jour = datetime.date.fromisoformat(meta["debut"])
    fin = datetime.date.fromisoformat(meta["fin"])
    while jour <= fin:
        iso = jour.isoformat()
        if iso not in non_couverts:
            ouvert = iso not in feries and jour.weekday() in lecture.shown
            moins = plus = False
            if ouvert:
                slots = affectations.get(iso)
                slots = slots if isinstance(slots, dict) else {}
                moins = any(
                    lecture.present(iso, p) and not _briques(slots, p["id"]) for p in praticiens
                )
                plus = any(
                    isinstance(brique, dict) and not brique.get("x")
                    for brique in _briques(slots, SLOT_SUREFFECTIF)
                )
            jours[iso] = {"moins": moins, "plus": plus, "ouvert": ouvert}
        jour += datetime.timedelta(days=1)
    return {"jours": jours}


def lire(version):
    """Le compte-rendu `jours` d'une version, ou `{}`.

    `{}` pour une version non publiée (`verifications == []`), historique (C7.8)
    ou publiée avant la brique 6b : la grille se rend alors sans marqueur.
    """
    marques = version.verifications if isinstance(version.verifications, dict) else {}
    compte_rendu = marques.get("effectif")
    if not isinstance(compte_rendu, dict):
        return {}
    jours = compte_rendu.get("jours")
    return jours if isinstance(jours, dict) else {}
