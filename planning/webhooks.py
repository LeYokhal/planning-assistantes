"""Webhook n8n de l'événement `planning.publie` (brique 4b).

Un seul événement : une version du planning vient d'être publiée. Le corps ne
porte que le mois, le numéro de version, un comptage, l'identifiant du compte
qui a publié et un lien : ni nom, ni type d'absence, ni `state`.

Calque d'`absences/webhooks.py` : client `socle.client_n8n`, fail-closed sans
URL ni secret. Ce module n'importe pas `services` (c'est `services` qui
l'importe) : le nombre de briques lui est passé par l'appelant.
"""

import logging

from django.conf import settings
from django.utils import timezone

from socle import client_n8n

logger = logging.getLogger(__name__)

EN_TETE_SECRET = "X-Webhook-Secret"

EVENEMENT_PUBLIE = "planning.publie"


def _lien(mois):
    """URL de la page du mois, pour le mail d'alerte n8n."""
    base = getattr(settings, "APP_URL", "").rstrip("/")
    return f"{base}/planning/{mois}/"


def corps(version, nb_briques):
    """Corps JSON de l'événement. Ni nom, ni type d'absence, ni `state`."""
    return {
        "evenement": EVENEMENT_PUBLIE,
        "mois": version.mois,
        "numero": version.numero,
        "nb_briques": nb_briques,
        "publie_par_id": version.publie_par_id,
        "lien": _lien(version.mois),
        "horodatage": timezone.now().isoformat(),
    }


def notifier_publication(version, nb_briques):
    """Prévient n8n. Renvoie True si n8n l'a accepté.

    Ne lève jamais : un webhook muet ne doit pas empêcher une publication. La
    variable `N8N_PLANNING_WEBHOOK_URL` n'est pas posée avant la brique 5 :
    l'avertissement « non configure » est attendu d'ici là.
    """
    resultat = client_n8n.poster(
        getattr(settings, "N8N_PLANNING_WEBHOOK_URL", ""),
        EN_TETE_SECRET,
        getattr(settings, "N8N_WEBHOOK_SECRET", ""),
        corps(version, nb_briques),
    )

    if resultat.motif == client_n8n.MOTIF_NON_CONFIGURE:
        logger.warning("webhook planning non configure : aucune notification")
        return False

    if resultat.motif == client_n8n.MOTIF_RESEAU:
        logger.warning("webhook planning impossible (%s)", resultat.erreur)
        return False

    if resultat.motif == client_n8n.MOTIF_STATUT:
        logger.warning("webhook planning refuse (statut %s)", resultat.statut)
        return False

    logger.info("webhook planning transmis (statut %s)", resultat.statut)
    return True
