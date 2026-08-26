"""Assure l'existence du compte « cabinet ». Idempotente, exécutée au pré-déploiement.

Cette commande ne doit JAMAIS lever d'exception : elle tourne au pré-déploiement
Railway, où un échec bloquerait tout déploiement ultérieur. Toute erreur est
rapportée sur la sortie d'erreur, et la commande sort quand même en code 0.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from audit.models import Action
from audit.services import journaliser


class Command(BaseCommand):
    help = "Cree le compte cabinet a partir de CABINET_EMAIL s'il n'existe pas encore."

    def handle(self, *args, **options):
        try:
            self._assurer()
        except Exception as erreur:
            # Seul le type d'erreur est rapporte : son message pourrait contenir
            # l'adresse du compte.
            self.stderr.write(
                self.style.ERROR(
                    f"assurer_compte_cabinet : echec ignore ({type(erreur).__name__}). "
                    "Le deploiement continue."
                )
            )

    def _assurer(self):
        email = (
            os.environ.get("CABINET_EMAIL")
            or getattr(settings, "CABINET_EMAIL", "")
            or ""
        ).strip()

        if not email:
            self.stdout.write(
                self.style.WARNING(
                    "CABINET_EMAIL absente ou vide : aucun compte cabinet assure."
                )
            )
            return

        Compte = get_user_model()
        compte = Compte.objects.filter(email__iexact=email).first()
        cree = compte is None

        if cree:
            compte = Compte.objects.create_user(
                email=email,
                role=Compte.Role.CABINET,
                is_staff=True,
                is_superuser=True,
            )
        else:
            champs = []
            for champ, valeur in (("is_active", True), ("is_staff", True), ("is_superuser", True)):
                if getattr(compte, champ) is not valeur:
                    setattr(compte, champ, valeur)
                    champs.append(champ)
            if compte.role != Compte.Role.CABINET:
                compte.role = Compte.Role.CABINET
                champs.append("role")
            if champs:
                compte.save(update_fields=champs)

        journaliser(Action.COMPTE_CABINET_ASSURE, qui=compte, objet=compte, cree=cree)
        self.stdout.write(
            self.style.SUCCESS(
                "compte cabinet cree." if cree else "compte cabinet deja present."
            )
        )
