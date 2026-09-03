"""Client du webhook n8n chargé de l'envoi des mails.

Aucune adresse, aucun jeton, aucun lien n'apparaît jamais dans les logs :
seuls le fait de l'envoi et le code de statut HTTP sont journalisés.
"""

import logging

# ⚠️ NE PAS RETIRER cet import, bien que l'appel réseau soit passé dans
# `socle.client_n8n` (brique 3, décision J). Six tests de `test_mails.py`
# patchent `comptes.mails.requests.post` : `mock.patch` résout ce chemin par
# `getattr(comptes.mails, "requests")`, et tomberait en `AttributeError` sans
# lui. Le patch reste efficace parce qu'il mute l'attribut `post` du module
# `requests` PARTAGÉ, celui-là même qu'appelle le client factorisé.
import requests  # noqa: F401
from django.conf import settings

from socle import client_n8n

logger = logging.getLogger(__name__)

DELAI_SECONDES = client_n8n.DELAI_SECONDES

EN_TETE_SECRET = "X-Mail-Secret"

OBJET_LIEN = "Votre lien de connexion — Planning Assistantes"
OBJET_INVITATION = "Votre accès à Planning Assistantes"
OBJET_ADRESSE = "Confirmez votre nouvelle adresse — Planning Assistantes"


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


def texte_adresse(lien):
    """Corps du mail de confirmation d'un changement d'adresse.

    Envoyé à la NOUVELLE adresse : c'est le clic qui prouve qu'elle est bien
    relevée par la salariée.
    """
    return (
        "Vous avez demandé à utiliser cette adresse pour vous connecter à "
        "Planning Assistantes. Confirmez en ouvrant ce lien (valable 1 heure) :\n"
        f"{lien}\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
        "rien ne sera changé."
    )


def envoyer_mail(destinataire, objet, texte):
    """Demande à n8n d'envoyer un mail. Renvoie True si n8n l'a accepté.

    Comportement fail-closed : si l'URL du webhook ou le secret est absent,
    aucun envoi n'est tenté et la fonction renvoie False.
    """
    resultat = client_n8n.poster(
        getattr(settings, "N8N_MAIL_WEBHOOK_URL", ""),
        EN_TETE_SECRET,
        getattr(settings, "N8N_WEBHOOK_SECRET", ""),
        {"destinataire": destinataire, "objet": objet, "texte": texte},
    )

    if resultat.motif == client_n8n.MOTIF_NON_CONFIGURE:
        logger.warning("webhook mail non configure : aucun envoi effectue")
        return False

    if resultat.motif == client_n8n.MOTIF_RESEAU:
        # On ne journalise que le type d'erreur : son message peut contenir l'URL.
        logger.warning("envoi de mail impossible (%s)", resultat.erreur)
        return False

    if resultat.motif == client_n8n.MOTIF_STATUT:
        logger.warning("envoi de mail refuse par le webhook (statut %s)", resultat.statut)
        return False

    logger.info("mail transmis au webhook (statut %s)", resultat.statut)
    return True
