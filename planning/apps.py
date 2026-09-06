"""Déclaration de l'application « planning » (brique 4a)."""

from django.apps import AppConfig


class PlanningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "planning"
    verbose_name = "Planning"
