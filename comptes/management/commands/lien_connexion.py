"""Génère un lien de connexion de secours, quand n8n est indisponible.

Le lien est affiché sur la sortie standard et n'est jamais journalisé.
L'usage de cette commande sur la production demande un accord explicite.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from audit.models import Action
from audit.services import journaliser
from comptes.views import construire_lien


class Command(BaseCommand):
    help = "Affiche un lien de connexion a usage unique pour une adresse donnee."

    def add_arguments(self, parseur):
        parseur.add_argument("email", help="Adresse e-mail du compte.")

    def handle(self, *args, **options):
        email = options["email"].strip()
        Compte = get_user_model()
        compte = Compte.objects.filter(email__iexact=email, is_active=True).first()
        if compte is None:
            raise CommandError("Aucun compte actif ne correspond a cette adresse.")

        # Evenement d'audit sans adresse ni jeton : l'identite est portee par `qui`.
        journaliser(Action.LIEN_SECOURS, qui=compte, objet=compte)

        # Sortie standard uniquement : le lien ne passe jamais par les logs.
        self.stdout.write(construire_lien(compte))
