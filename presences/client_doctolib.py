"""Client de l'endpoint « présences » du serveur MCP Doctolib (brique 0).

⚠️ La brique 0 n'est PAS livrée : `DOCTOLIB_PRESENCES_URL` et
`DOCTOLIB_PRESENCES_SECRET` sont absentes, et ce chemin est donc inactif. Un tir
demandé par n8n aboutit en échec « endpoint inactif », sans le moindre appel
réseau. Le contrat ci-dessous sera réaligné sur celui de la brique 0 le jour où
elle existera.

Ni l'URL ni le secret n'apparaissent jamais dans les logs.
"""

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# (délai de connexion, délai de lecture). L'appel S7 sur 31 jours dure
# largement plus d'une minute : le second délai est volontairement long.
DELAI = (10, 150)

EN_TETE_SECRET = "X-Presences-Secret"
LONGUEUR_MAX_ERREUR = 200


class EndpointInactif(Exception):
    """Aucune URL ou aucun secret : le chemin endpoint n'est pas câblé."""


class EndpointErreur(Exception):
    """L'endpoint a répondu autre chose qu'un 200, ou n'a pas répondu."""


def appeler(debut, fin):
    """Demande une fenêtre de présences et renvoie `(octets, durée en ms)`."""
    url = getattr(settings, "DOCTOLIB_PRESENCES_URL", "")
    secret = getattr(settings, "DOCTOLIB_PRESENCES_SECRET", "")
    if not url or not secret:
        raise EndpointInactif("endpoint inactif (brique 0 non livrée)")

    depart = time.monotonic()
    try:
        reponse = requests.post(
            url,
            json={
                "date": debut.isoformat(),
                "date_fin": fin.isoformat(),
                "praticien": "tous",
            },
            headers={
                EN_TETE_SECRET: secret,
                "Content-Type": "application/json",
            },
            timeout=DELAI,
        )
    except requests.RequestException as erreur:
        # Le message d'une exception `requests` contient l'URL : on ne garde que
        # le type.
        raise EndpointErreur(
            f"endpoint injoignable ({type(erreur).__name__})"
        ) from None

    duree_ms = int((time.monotonic() - depart) * 1000)

    if reponse.status_code != 200:
        raise EndpointErreur(
            f"HTTP {reponse.status_code} : {_message_court(reponse)}"[
                :LONGUEUR_MAX_ERREUR
            ]
        )

    logger.info(
        "endpoint presences %s->%s : HTTP %s, %s ms",
        debut,
        fin,
        reponse.status_code,
        duree_ms,
    )
    return reponse.content, duree_ms


def _message_court(reponse):
    """Le `message` du corps JSON s'il y en a un, sinon rien."""
    try:
        corps = reponse.json()
    except ValueError:
        return ""
    if not isinstance(corps, dict):
        return ""
    return str(corps.get("message", ""))[:150]
