"""Signaux d'authentification : journalisation des connexions."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser


@receiver(user_logged_in)
def au_moment_de_la_connexion(sender, request, user, **kwargs):
    journaliser(Action.CONNEXION, qui=user)
    if user.active_le is None:
        user.active_le = timezone.now()
        user.save(update_fields=["active_le"])


@receiver(user_logged_out)
def au_moment_de_la_deconnexion(sender, request, user, **kwargs):
    if user is None:
        return
    journaliser(Action.DECONNEXION, qui=user)
