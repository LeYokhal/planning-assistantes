"""Administration des imports : consultation seule.

Une ligne d'import n'est jamais modifiée ni supprimée — c'est la preuve de ce
qui est entré dans l'application. Le payload lui-même n'est jamais affiché :
seules sa taille et son empreinte le sont.
"""

from django.contrib import admin

from .models import ImportPresences, VerrouImport


@admin.register(ImportPresences)
class ImportPresencesAdmin(admin.ModelAdmin):
    """Historique des imports, strictement non modifiable."""

    list_display = (
        "id",
        "source",
        "statut",
        "debut",
        "fin",
        "invariant_ok",
        "nb_lignes",
        "importe_le",
        "importe_par",
        "duree_ms",
        "webhook_envoye",
    )
    list_filter = ("source", "statut", "invariant_ok")
    date_hierarchy = "importe_le"
    # `payload` est volontairement absent : il n'a pas à être affiché.
    fields = (
        "source",
        "statut",
        "lot",
        "mois",
        "debut",
        "fin",
        "forme",
        "empreinte",
        "taille",
        "message",
        "invariant_ok",
        "nb_jours",
        "nb_lignes",
        "nb_presents",
        "erreur",
        "nom_fichier",
        "importe_le",
        "termine_le",
        "importe_par",
        "duree_ms",
        "webhook_envoye",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        # Le payload pèse jusqu'à 250 Ko : inutile de le charger pour une liste.
        return super().get_queryset(request).defer("payload")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VerrouImport)
class VerrouImportAdmin(admin.ModelAdmin):
    """Verrou en cours, pour diagnostiquer un import qui semble bloqué."""

    list_display = ("cle", "pris_le", "motif", "lot")
    readonly_fields = ("cle", "pris_le", "motif", "lot")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
