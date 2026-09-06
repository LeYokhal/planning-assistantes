"""Administration des absences.

`AbsenceSalariee` est modifiable ici — c'est le canal de reprise de l'existant
Notion, qui n'est pas migré (décision du 01/09). Toute écriture est journalisée,
sur le patron de `comptes/admin.py`.

⚠️ Les événements d'audit émis d'ici ne portent **ni le type ni la précision**.
"""

from django import forms
from django.contrib import admin

from audit.models import Action
from audit.services import journaliser

from . import calcul, services
from .models import AbsenceSalariee, TypeAbsence


def _journaliser_suppression(request, absence):
    """Trace d'une suppression : identifiants, statut, dates. Ni type ni précision."""
    journaliser(
        Action.ABSENCE_SUPPRIMEE,
        qui=request.user,
        objet=absence,
        personne_id=absence.personne_id,
        statut=absence.statut,
        debut=absence.date_debut.isoformat(),
        fin=absence.date_fin.isoformat(),
    )


class FormulaireAbsenceAdmin(forms.ModelForm):
    """Formulaire d'admin, qui tient la décision P à la saisie.

    `limit_choices_to` restreint déjà la liste déroulante, mais ce n'est qu'un
    filtre d'affichage : il ne valide rien. Cette garde-ci rend une erreur de
    champ lisible ; celle de `save_model` est le dernier rempart.
    """

    class Meta:
        model = AbsenceSalariee
        fields = "__all__"

    def clean_personne(self):
        personne = self.cleaned_data["personne"]
        if not calcul.est_salariee(personne):
            raise forms.ValidationError(
                "Une absence ne peut porter que sur une assistante ou une secrétaire."
            )
        return personne


@admin.register(TypeAbsence)
class TypeAbsenceAdmin(admin.ModelAdmin):
    """Référentiel des types. Posé par migration, ajustable par le cabinet."""

    list_display = ("libelle", "categorie", "bloquant", "paie", "actif", "ordre")
    list_filter = ("categorie", "bloquant", "paie", "actif")
    search_fields = ("libelle",)
    ordering = ("ordre", "libelle")


@admin.register(AbsenceSalariee)
class AbsenceSalarieeAdmin(admin.ModelAdmin):
    """Saisie et reprise des absences. Chaque écriture laisse une trace."""

    form = FormulaireAbsenceAdmin
    list_display = (
        "id",
        "personne",
        "date_debut",
        "date_fin",
        "type",
        "statut",
        "jours_comptes_calcules",
        "jours_comptes",
        "a_effacer_le",
    )
    list_filter = ("statut", "type", "personne__role_metier")
    search_fields = ("personne__nom", "personne__prenom")
    date_hierarchy = "date_debut"
    autocomplete_fields = ()
    readonly_fields = (
        "cree_le",
        "auteur",
        "decide_par",
        "decide_le",
        "corrige_par",
        "corrige_le",
        "jours_comptes_calcules",
    )
    fieldsets = (
        (None, {"fields": ("personne", "type", "date_debut", "date_fin", "statut")}),
        ("Détail", {"fields": ("precision",)}),
        (
            "Paie",
            {"fields": ("jours_comptes_calcules", "jours_comptes", "a_effacer_le")},
        ),
        (
            "Suivi",
            {
                "fields": (
                    "cree_le",
                    "auteur",
                    "decide_par",
                    "decide_le",
                    "corrige_par",
                    "corrige_le",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Pose l'auteur à la création, recalcule si l'absence devient effective.

        La garde de la décision P est ici le **dernier rempart** : le formulaire
        l'attrape en amont et rend une erreur de champ lisible. Elle n'est donc
        pas atteignable par l'interface, et c'est bien ainsi — elle protège les
        chemins qui contourneraient le formulaire.
        """
        if not calcul.est_salariee(obj.personne):
            raise services.ActionImpossible(
                "Une absence ne peut porter que sur une assistante ou une secrétaire."
            )
        if not change:
            obj.auteur = request.user

        super().save_model(request, obj, form, change)

        # Une reprise saisie directement en « validée » ou « déclarée » doit
        # repartir avec ses jours comptés, comme si elle était passée par le
        # service. La correction manuelle éventuelle n'est pas écrasée.
        if obj.effective and obj.jours_comptes_calcules is None:
            services.recalculer(obj)

        journaliser(
            Action.ABSENCE_DECIDEE if change else Action.ABSENCE_DECLAREE,
            qui=request.user,
            objet=obj,
            personne_id=obj.personne_id,
            statut=obj.statut,
            saisie_admin=True,
        )

        # Brique 4b : une reprise qui DEVIENT effective peut contredire un
        # planning déjà publié. Sur la transition seulement : une création, ou
        # un changement de statut ; modifier la précision ou une date d'une
        # absence déjà effective ne signale rien. `form` peut être absent
        # (appel direct, hors interface) : la création vaut alors transition.
        changes = getattr(form, "changed_data", None) or []
        if (not change or "statut" in changes) and obj.effective:
            services.signaler_conflits(obj, request.user)

    def delete_model(self, request, obj):
        """Supprimer efface l'objet mais pas sa trace : l'événement porte le
        type d'objet, l'identifiant, la personne, le statut et les dates. Hors
        purge de rétention, c'est un geste d'administration (reprise, jeu de
        test) ; le cycle de vie normal passe par « annulée ».
        """
        _journaliser_suppression(request, obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Suppression groupée : une trace par objet, avant l'effacement."""
        for objet in queryset:
            _journaliser_suppression(request, objet)
        super().delete_queryset(request, queryset)
