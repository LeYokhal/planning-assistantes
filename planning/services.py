"""Enregistrement des versions du planning (brique 4a).

Toute écriture d'une `PlanningVersion` passe par `enregistrer` : nettoyage du
`state`, contrôle de la version de base, vérification stricte, insertion, audit.
Les vues ne font que traduire les exceptions en codes HTTP.

Concurrence : deux workers gunicorn peuvent recevoir le même « Enregistrer » à
la même seconde. `select_for_update` est proscrit (SQLite en développement,
`CLAUDE.md`) ; c'est la contrainte unique `(mois, numero)` qui sérialise, sur le
patron de `presences/verrou.py` : l'`IntegrityError` est attrapée HORS du bloc
`atomic()`, puis le dernier numéro est relu pour répondre 409.

Le journal d'audit et les logs ne reçoivent que le mois, le numéro et des
comptages : jamais un nom, jamais un type d'absence.
"""

import logging

from django.db import IntegrityError, transaction

from audit.models import Action
from audit.services import journaliser

from . import donnees
from .models import PlanningVersion
from .verification import nettoyer, verifier

logger = logging.getLogger(__name__)


class Conflit(Exception):
    """La version de base n'est plus la dernière : 409, `derniere` = numéro actuel."""

    def __init__(self, derniere):
        super().__init__(f"version {derniere} enregistrée entre-temps")
        self.derniere = derniere


class Invalide(Exception):
    """Des règles strictes sont enfreintes : 422, `violations` = la liste."""

    def __init__(self, violations):
        super().__init__(f"{len(violations)} violation(s)")
        self.violations = violations


def derniere_version(mois):
    """La dernière version enregistrée du mois, ou None."""
    return PlanningVersion.objects.filter(mois=mois).order_by("-numero").first()


def numero_courant(mois):
    """Numéro de la dernière version, 0 s'il n'y en a aucune."""
    derniere = derniere_version(mois)
    return derniere.numero if derniere else 0


def etat_vide():
    """L'état servi quand aucune version n'existe : la page propose alors."""
    return {"affectations": {}, "feries": {}, "feries_off": [], "notes": {}}


def nb_briques(state):
    """Nombre de briques posées, pour l'audit. Aucun nom."""
    total = 0
    for slots in (state.get("affectations") or {}).values():
        if isinstance(slots, dict):
            for arr in slots.values():
                if isinstance(arr, list):
                    total += len(arr)
    return total


def enregistrer(mois, version_de_base, state, qui, data=None):
    """Enregistre une nouvelle version du mois et la renvoie.

    Lève `Conflit` si `version_de_base` n'est plus la dernière (avant comme
    après l'insertion), `Invalide` si une règle stricte est enfreinte. Rien
    n'est écrit dans ces deux cas.
    """
    courant = numero_courant(mois)
    if version_de_base != courant:
        raise Conflit(courant)

    propre = nettoyer(state)
    if data is None:
        data = donnees.construire(mois)
    violations = verifier(data, propre)
    if violations:
        raise Invalide(violations)

    auteur = qui if getattr(qui, "is_authenticated", False) else None
    try:
        with transaction.atomic():
            version = PlanningVersion.objects.create(
                mois=mois,
                numero=courant + 1,
                state=propre,
                version_de_base=version_de_base,
                auteur=auteur,
                verifications=[],
            )
    except IntegrityError:
        # Un autre worker a pris ce numéro entre la lecture et l'écriture.
        raise Conflit(numero_courant(mois)) from None

    total = nb_briques(propre)
    journaliser(
        Action.PLANNING_ENREGISTRE,
        qui=qui,
        objet=version,
        mois=mois,
        numero=version.numero,
        nb_briques=total,
    )
    logger.info(
        "planning %s : version %s enregistree (%s briques)", mois, version.numero, total
    )
    return version
