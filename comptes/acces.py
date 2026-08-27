"""Contrôle d'accès par rôle.

Premier mécanisme de rôle du projet : la brique 1a posait le champ
`Compte.role` sans jamais le lire. Les briques 2 à 5 réutilisent ce décorateur —
il n'y en aura pas d'autre.

`is_superuser` ne contourne PAS le rôle : le compte cabinet porte le rôle
« cabinet » (voir `assurer_compte_cabinet`), et un superutilisateur créé pour
autre chose n'a rien à faire sur ces écrans.
"""

import functools
import logging

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from audit.models import Action
from audit.services import journaliser

logger = logging.getLogger(__name__)


def role_requis(*roles):
    """Vue réservée aux comptes connectés dont le rôle est dans `roles`.

    Anonyme → redirection vers la page de connexion, avec le `next` d'origine.
    Connecté mais mauvais rôle → 403, et un événement `acces_refuse` au journal.
    """

    def decorateur(vue):
        @functools.wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                journaliser(Action.ACCES_REFUSE, qui=request.user, vue=vue.__name__)
                logger.warning("acces refuse a la vue %s", vue.__name__)
                raise PermissionDenied
            return vue(request, *args, **kwargs)

        return enveloppe

    return decorateur
