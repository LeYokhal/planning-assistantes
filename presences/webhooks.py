"""Webhook n8n des événements d'import (`import.termine` / `import.echec`).

Client sœur de `comptes/mails.py`, volontairement indépendant : les deux
partagent le patron (fail-closed, délai court, seul le statut journalisé) mais
pas le code, et surtout pas l'en-tête — `X-Mail-Secret` sur un webhook d'import
serait trompeur. La factorisation d'un client n8n commun attendra qu'il y ait
trois appelants (brique 5).

Un webhook par LOT, envoyé à la fin du lot. Le corps ne contient ni nom
d'agenda, ni donnée patient : uniquement des identifiants, des fenêtres et des
comptages.
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

from .fenetres import mois_de_fenetre
from .models import ImportPresences

logger = logging.getLogger(__name__)

DELAI_SECONDES = 10
EN_TETE_SECRET = "X-Webhook-Secret"

EVENEMENT_TERMINE = "import.termine"
EVENEMENT_ECHEC = "import.echec"


def _lien(imports):
    """URL de l'écran concerné par le lot, pour le mail d'alerte n8n."""
    base = getattr(settings, "APP_URL", "").rstrip("/")
    for import_ in imports:
        if import_.mois:
            return f"{base}/presences/{import_.mois}/"
    for import_ in imports:
        if import_.debut and import_.fin:
            return f"{base}/presences/{mois_de_fenetre(import_.debut, import_.fin)}/"
    return f"{base}/admin/presences/importpresences/"


def corps_lot(imports):
    """Construit le corps JSON transmis à n8n pour un lot."""
    premier = imports[0]
    toutes_reussies = all(
        import_.statut == ImportPresences.Statut.REUSSI for import_ in imports
    )
    return {
        "evenement": EVENEMENT_TERMINE if toutes_reussies else EVENEMENT_ECHEC,
        "lot": str(premier.lot),
        "mois": premier.mois or None,
        "source": premier.source,
        "fenetres": [
            {
                "import_id": import_.pk,
                "debut": import_.debut.isoformat() if import_.debut else None,
                "fin": import_.fin.isoformat() if import_.fin else None,
                "statut": import_.statut,
                "invariant_ok": import_.invariant_ok,
                "nb_lignes": import_.nb_lignes,
                "erreur": import_.erreur,
            }
            for import_ in imports
        ],
        "lien": _lien(imports),
        "horodatage": timezone.now().isoformat(),
    }


def notifier_lot(imports):
    """Prévient n8n de la fin d'un lot. Renvoie True si n8n l'a accepté.

    Comportement fail-closed : sans URL ni secret, rien n'est tenté.
    """
    imports = list(imports)
    if not imports:
        return False

    url = getattr(settings, "N8N_IMPORT_WEBHOOK_URL", "")
    secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    if not url or not secret:
        logger.warning("webhook import non configure : aucune notification")
        return False

    corps = corps_lot(imports)

    try:
        reponse = requests.post(
            url,
            json=corps,
            headers={
                EN_TETE_SECRET: secret,
                "Content-Type": "application/json",
            },
            timeout=DELAI_SECONDES,
        )
    except requests.RequestException as erreur:
        logger.warning("webhook import impossible (%s)", type(erreur).__name__)
        return False

    if reponse.status_code >= 400:
        logger.warning(
            "webhook import refuse (statut %s)", reponse.status_code
        )
        return False

    logger.info("webhook import transmis (statut %s)", reponse.status_code)
    for import_ in imports:
        import_.webhook_envoye = True
        if import_.pk:
            import_.save(update_fields=["webhook_envoye"])
    return True
