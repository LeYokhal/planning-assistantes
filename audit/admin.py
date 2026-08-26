"""Administration du journal d'audit : consultation seule."""

from django.contrib import admin

from .models import EvenementAudit


@admin.register(EvenementAudit)
class EvenementAuditAdmin(admin.ModelAdmin):
    """Journal strictement non modifiable depuis l'administration."""

    list_display = ("quand", "action", "qui", "type_objet", "id_objet")
    # Pas de recherche portant sur `details`.
    list_filter = ("action", "quand")
    date_hierarchy = "quand"
    readonly_fields = ("quand", "qui", "action", "type_objet", "id_objet", "details")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
