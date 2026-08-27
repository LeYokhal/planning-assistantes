"""Déclaration de l'application « API n8n ».

Cette application n'a ni modèle ni migration : elle n'expose que l'API entrante
appelée par n8n. Les briques 2 à 5 y ajouteront leurs routes.
"""

from django.apps import AppConfig


class N8nConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "n8n"
    verbose_name = "API n8n"
