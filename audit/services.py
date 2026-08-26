"""Service d'écriture du journal d'audit."""

import logging

from .models import EvenementAudit

logger = logging.getLogger(__name__)

# Garde-fou : `details` ne doit jamais transporter d'adresse e-mail, de jeton
# ni de secret. Toute valeur qui ressemble à une adresse est remplacée.
MASQUE = "[masque]"


def _valeur_sure(valeur):
    """Neutralise une valeur qui ressemblerait à une adresse e-mail."""
    if isinstance(valeur, str) and "@" in valeur:
        return MASQUE
    if isinstance(valeur, dict):
        return {cle: _valeur_sure(sous) for cle, sous in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_valeur_sure(sous) for sous in valeur]
    return valeur


def journaliser(action, qui=None, objet=None, **details):
    """Écrit un événement dans le journal d'audit et le renvoie.

    `qui` est un Compte (ou None pour un acteur anonyme), `objet` un modèle
    quelconque dont on note le type et l'identifiant, `details` un dictionnaire
    libre — sans adresse e-mail, sans jeton, sans secret.
    """
    if qui is not None and not getattr(qui, "is_authenticated", False):
        qui = None

    type_objet = ""
    id_objet = ""
    if objet is not None:
        type_objet = type(objet).__name__[:40]
        id_objet = "" if objet.pk is None else str(objet.pk)[:40]

    details_surs = {cle: _valeur_sure(valeur) for cle, valeur in details.items()}
    if details_surs != details:
        logger.warning(
            "audit : une valeur ressemblant a une adresse a ete masquee (action %s)",
            action,
        )

    return EvenementAudit.objects.create(
        action=action,
        qui=qui,
        type_objet=type_objet,
        id_objet=id_objet,
        details=details_surs,
    )
