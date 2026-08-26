"""Client du webhook n8n chargé de l'envoi des mails.

Aucune adresse, aucun jeton, aucun lien n'apparaît jamais dans les logs :
seuls le fait de l'envoi et le code de statut HTTP sont journalisés.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DELAI_SECONDES = 10

OBJET_LIEN = "Votre lien de connexion — Planning Assistantes"
OBJET_INVITATION = "Votre accès à Planning Assistantes"


def texte_lien(lien):
    """Corps du mail contenant le lien de connexion à usage unique."""
    return (
        "Bonjour, voici votre lien de connexion à Planning Assistantes "
        "(valable 15 minutes, usage unique) :\n"
        f"{lien}\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message."
    )


def texte_invitation():
    """Corps du mail d'invitation. Ne contient AUCUN jeton."""
    return (
        "Un compte vient d'être créé pour vous sur Planning Assistantes "
        "(Espace K Dentaire). Pour vous connecter : "
        f"{settings.APP_URL}/connexion/ — saisissez cette adresse, "
        "vous recevrez un lien."
    )


def envoyer_mail(destinataire, objet, texte):
    """Demande à n8n d'envoyer un mail. Renvoie True si n8n l'a accepté.

    Comportement fail-closed : si l'URL du webhook ou le secret est absent,
    aucun envoi n'est tenté et la fonction renvoie False.
    """
    url = getattr(settings, "N8N_MAIL_WEBHOOK_URL", "")
    secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    if not url or not secret:
        logger.warning("webhook mail non configure : aucun envoi effectue")
        return False

    try:
        reponse = requests.post(
            url,
            json={"destinataire": destinataire, "objet": objet, "texte": texte},
            headers={
                "X-Mail-Secret": secret,
                "Content-Type": "application/json",
            },
            timeout=DELAI_SECONDES,
        )
    except requests.RequestException as erreur:
        # On ne journalise que le type d'erreur : son message peut contenir l'URL.
        logger.warning("envoi de mail impossible (%s)", type(erreur).__name__)
        return False

    if reponse.status_code >= 400:
        logger.warning("envoi de mail refuse par le webhook (statut %s)", reponse.status_code)
        return False

    logger.info("mail transmis au webhook (statut %s)", reponse.status_code)
    return True
