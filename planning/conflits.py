"""Conflit entre une absence devenue effective et un planning publié (brique 4b).

Une absence n'entre dans le planning qu'une fois effective. Si la version
publiée d'un mois pose déjà une brique de la salariée sur un de ces jours, le
planning publié est faux ce jour-là. Le conflit est calculé à la demande
(décision J), jamais stocké : il est signalé (audit, webhook, bandeau de
`/absences/`) et ne bloque rien (décision C).

Cycle d'import : ce module importe `services` et `donnees`, donc
`absences.services`. C'est `absences/` qui importe ce module DANS ses
fonctions, jamais en tête (patron `presences/verrou.py`).
"""

import datetime

from presences.fenetres import mois_precedent, mois_suivant, plage_mois

from . import services
from .donnees import identifiant


def conflits_dans_state(state, sid, dates):
    """Dates ISO de `dates` où `state` pose une brique de `sid`, tout slot. Pur.

    Tout slot compte (praticien, secrétariat, sureffectif, administratif), hors
    quota compris : une brique est une journée due par la salariée.
    """
    affectations = (state or {}).get("affectations") or {}
    touchees = []
    for iso in dates:
        slots = affectations.get(iso)
        if not isinstance(slots, dict):
            continue
        briques = (
            b
            for arr in slots.values()
            if isinstance(arr, list)
            for b in arr
            if isinstance(b, dict)
        )
        if any(b.get("s") == sid for b in briques):
            touchees.append(iso)
    return touchees


def mois_candidats(date_debut, date_fin):
    """Mois « AAAA-MM » dont la plage (semaines complètes) touche [debut, fin]. Pur.

    Une plage déborde d'au plus six jours sur les mois voisins : les candidats
    sont les mois calendaires couverts et leurs voisins immédiats, filtrés par
    `plage_mois`.
    """
    candidats = set()
    jour = date_debut
    while jour <= date_fin:
        cle = jour.strftime("%Y-%m")
        candidats.update((mois_precedent(cle), cle, mois_suivant(cle)))
        jour = (jour.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)

    retenus = []
    for mois in sorted(candidats):
        plage = plage_mois(mois)
        if plage.debut <= date_fin and plage.fin >= date_debut:
            retenus.append(mois)
    return retenus


def conflits(personne, date_debut, date_fin, versions=None):
    """`[{"mois", "numero", "dates"}]` : un élément par mois publié en conflit.

    `versions` est un cache facultatif `{mois: version ou None}`, partagé par
    l'écran de décision pour ne lire chaque version publiée qu'une fois.
    """
    if versions is None:
        versions = {}
    sid = identifiant(personne)
    dates = [
        (date_debut + datetime.timedelta(days=n)).isoformat()
        for n in range((date_fin - date_debut).days + 1)
    ]
    resultat = []
    for mois in mois_candidats(date_debut, date_fin):
        if mois not in versions:
            versions[mois] = services.version_publiee(mois)
        version = versions[mois]
        if version is None:
            continue
        plage = plage_mois(mois)
        debut, fin = plage.debut.isoformat(), plage.fin.isoformat()
        touchees = conflits_dans_state(
            version.state, sid, [iso for iso in dates if debut <= iso <= fin]
        )
        if touchees:
            resultat.append({"mois": mois, "numero": version.numero, "dates": touchees})
    return resultat
