"""Enchaîne les gestes de pré-déploiement Railway : migrations puis compte cabinet.

Railway n'exécute pas le pré-déploiement dans un shell : `preDeployCommand` ne
peut porter qu'une seule commande, et un `&&` n'y est jamais interprété — seule
la première commande tournerait. Cette commande de gestion est donc le seul
point d'entrée du pré-déploiement, et elle appelle les deux autres elle-même.

Un échec de `migrate` doit faire échouer le déploiement : l'exception remonte.
`assurer_compte_cabinet`, elle, ne lève jamais (voir son propre module).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Pre-deploiement Railway : migrations puis compte cabinet."

    def handle(self, *args, **options):
        # Volontairement sans garde : une migration en echec doit interrompre
        # le deploiement plutot que de laisser demarrer un schema incomplet.
        call_command("migrate", interactive=False, verbosity=1)

        # Idempotente et sans exception : son echec n'a jamais a bloquer.
        call_command("assurer_compte_cabinet")

        self.stdout.write("pre_deploiement termine.")
