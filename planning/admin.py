"""Administration des versions du planning : consultation seule.

Une version n'est jamais modifiée ni supprimée depuis l'administration — c'est
la trace de ce qui a été enregistré. Le `state` est affiché tel quel : il ne
porte ni congé, ni type d'absence, ni nom, seulement des identifiants.
"""

from django.contrib import admin

from .models import PlanningVersion


@admin.register(PlanningVersion)
class PlanningVersionAdmin(admin.ModelAdmin):
    """Historique des versions, strictement non modifiable."""

    list_display = ("mois", "numero", "version_de_base", "auteur", "cree_le", "publiee")
    list_filter = ("mois", "publiee")
    date_hierarchy = "cree_le"
    fields = (
        "mois",
        "numero",
        "version_de_base",
        "auteur",
        "cree_le",
        "verifications",
        "publiee",
        "publie_le",
        "publie_par",
        "state",
    )
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
