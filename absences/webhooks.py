"""Webhooks n8n des événements d'absence.

Trois événements : `absence.demandee` (création en attente de décision),
`absence.declaree` (création immédiatement effective) et `absence.decidee`
(passage en validée ou refusée). **L'annulation est auditée sans webhook** :
elle ne demande d'action à personne.

⚠️ Le corps ne porte **ni le type d'absence, ni la précision**. Il ne transporte
que des identifiants, des dates, un statut et un lien : n8n envoie un mail
d'alerte, et ce mail n'a pas à révéler qu'une salariée est en arrêt maladie.
C'est la contrainte structurante de la brique, et elle se prouve par les tests
de `absences/tests/test_confidentialite.py`.

Client HTTP : `socle.client_n8n` (décision J). Fail-closed sans URL ni secret,
comme les deux autres appelants.
"""

import logging

from django.conf import settings
from django.utils import timezone

from socle import client_n8n

logger = logging.getLogger(__name__)

EN_TETE_SECRET = "X-Webhook-Secret"

EVENEMENT_DEMANDEE = "absence.demandee"
EVENEMENT_DECLAREE = "absence.declaree"
EVENEMENT_DECIDEE = "absence.decidee"


def _lien(absence):
    """URL de l'écran de décision, pour le mail d'alerte n8n."""
    base = getattr(settings, "APP_URL", "").rstrip("/")
    return f"{base}/absences/"


def corps(evenement, absence):
    """Corps JSON d'un événement. Ni type d'absence, ni précision, ni nom."""
    return {
        "evenement": evenement,
        "absence_id": absence.pk,
        "personne_id": absence.personne_id,
        "debut": absence.date_debut.isoformat(),
        "fin": absence.date_fin.isoformat(),
        "statut": absence.statut,
        "lien": _lien(absence),
        "horodatage": timezone.now().isoformat(),
    }


def notifier(evenement, absence):
    """Prévient n8n. Renvoie True si n8n l'a accepté.

    Ne lève jamais : un webhook muet ne doit pas empêcher une salariée de poser
    son absence.
    """
    resultat = client_n8n.poster(
        getattr(settings, "N8N_ABSENCE_WEBHOOK_URL", ""),
        EN_TETE_SECRET,
        getattr(settings, "N8N_WEBHOOK_SECRET", ""),
        corps(evenement, absence),
    )

    if resultat.motif == client_n8n.MOTIF_NON_CONFIGURE:
        logger.warning("webhook absence non configure : aucune notification")
        return False

    if resultat.motif == client_n8n.MOTIF_RESEAU:
        logger.warning("webhook absence impossible (%s)", resultat.erreur)
        return False

    if resultat.motif == client_n8n.MOTIF_STATUT:
        logger.warning("webhook absence refuse (statut %s)", resultat.statut)
        return False

    logger.info("webhook absence transmis (statut %s)", resultat.statut)
    return True
