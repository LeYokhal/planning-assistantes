"""Contrôle du secret de l'API entrante n8n.

Fail-closed, sur le patron du canari (brief § 2.3) :

* `N8N_API_SECRET` absente → 503, l'API n'existe pas ;
* secret faux OU en-tête absent → 401, avec exactement la même réponse dans les
  deux cas — rien ne doit permettre de distinguer « mauvais secret » de
  « pas de secret » ;
* le secret est vérifié AVANT la méthode : un GET sans secret reçoit 401, pas
  405, et n'apprend donc rien sur l'existence de la route.

Aucun événement d'audit ici : le trafic non authentifié ne doit pas pouvoir
écrire en base. Un simple `logger.warning`, sans jamais la valeur reçue.
"""

import functools
import hmac
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

EN_TETE = "X-Api-Secret"
CLE_META = "HTTP_X_API_SECRET"


def secret_n8n_requis(vue):
    """Exige l'en-tête `X-Api-Secret`, et dispense la vue du contrôle CSRF."""

    @functools.wraps(vue)
    def enveloppe(request, *args, **kwargs):
        attendu = getattr(settings, "N8N_API_SECRET", "")
        if not attendu:
            logger.warning("api n8n desactivee : N8N_API_SECRET absente")
            return JsonResponse({"verdict": "disabled"}, status=503)

        recu = request.META.get(CLE_META, "")
        if not hmac.compare_digest(recu.encode("utf-8"), attendu.encode("utf-8")):
            logger.warning("api n8n : secret refuse")
            return JsonResponse({"verdict": "unauthorized"}, status=401)

        return vue(request, *args, **kwargs)

    # n8n n'a pas de session : le jeton CSRF n'a pas de sens ici, le secret
    # d'en-tête tient ce rôle.
    return csrf_exempt(enveloppe)
