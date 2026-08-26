from django.apps import AppConfig


class ComptesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptes"
    verbose_name = "Comptes et personnes"

    def ready(self):
        # Branche les signaux de connexion / déconnexion.
        from . import signals  # noqa: F401
