"""Déclaration de l'application « absences »."""

from django.apps import AppConfig


class AbsencesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "absences"
    verbose_name = "Absences"
