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

# ⚠️ NE PAS RETIRER cet import, bien que l'appel réseau soit passé dans
# `socle.client_n8n` (brique 3, décision J). Six tests de `test_webhooks.py`
# patchent `presences.webhooks.requests.post`, et la fixture `Routeur` de
# `test_endpoint.py` s'appuie sur le fait que ce module et
# `presences.client_doctolib` partagent le module `requests`. Retirer l'import
# ferait tomber ces tests en `AttributeError`.
import requests  # noqa: F401
from django.conf import settings
from django.utils import timezone

from socle import client_n8n

from .fenetres import mois_de_fenetre
from .models import ImportPresences

logger = logging.getLogger(__name__)

DELAI_SECONDES = client_n8n.DELAI_SECONDES
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

    resultat = client_n8n.poster(
        getattr(settings, "N8N_IMPORT_WEBHOOK_URL", ""),
        EN_TETE_SECRET,
        getattr(settings, "N8N_WEBHOOK_SECRET", ""),
        corps_lot(imports),
    )

    if resultat.motif == client_n8n.MOTIF_NON_CONFIGURE:
        logger.warning("webhook import non configure : aucune notification")
        return False

    if resultat.motif == client_n8n.MOTIF_RESEAU:
        logger.warning("webhook import impossible (%s)", resultat.erreur)
        return False

    if resultat.motif == client_n8n.MOTIF_STATUT:
        logger.warning(
            "webhook import refuse (statut %s)", resultat.statut
        )
        return False

    logger.info("webhook import transmis (statut %s)", resultat.statut)
    for import_ in imports:
        import_.webhook_envoye = True
        if import_.pk:
            import_.save(update_fields=["webhook_envoye"])
    return True
