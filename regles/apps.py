from django.apps import AppConfig


class ReglesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "regles"
    verbose_name = "Règles du planning"

    def ready(self):
        """Charge et valide `regles.json` au démarrage.

        Volontairement sans garde : un fichier de règles invalide doit empêcher
        l'application de démarrer plutôt que de la laisser tourner sur des
        règles fausses. L'`ImproperlyConfigured` remonte telle quelle.
        """
        from . import chargeur

        chargeur.charger()
