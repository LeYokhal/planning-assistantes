"""Administration des personnes et des comptes."""

from django import forms
from django.contrib import admin, messages
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser

from .mails import OBJET_INVITATION, envoyer_mail, texte_invitation
from .models import Compte, Personne


@admin.register(Personne)
class PersonneAdmin(admin.ModelAdmin):
    list_display = ("nom", "prenom", "role_metier", "planifiee", "actif", "code")
    list_filter = ("role_metier", "planifiee", "actif")
    search_fields = ("nom", "prenom", "code")
    readonly_fields = ("cree_le", "modifie_le")
    fieldsets = (
        (None, {"fields": ("nom", "prenom", "role_metier", "actif", "code")}),
        (
            "Planification",
            {"fields": ("planifiee", "heures_hebdo", "jours_fixes", "couleur", "agenda_doctolib")},
        ),
        ("Contact", {"fields": ("email_contact",)}),
        ("Suivi", {"fields": ("cree_le", "modifie_le")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        journaliser(
            Action.PERSONNE_MODIFIEE if change else Action.PERSONNE_CREEE,
            qui=request.user,
            objet=obj,
        )


class FormulaireCompte(forms.ModelForm):
    """Formulaire de compte sans mot de passe : la connexion se fait par lien."""

    class Meta:
        model = Compte
        fields = (
            "email",
            "personne",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    form = FormulaireCompte
    list_display = ("email", "role", "personne", "is_active", "is_staff", "active_le")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email",)
    readonly_fields = ("date_creation", "invite_le", "active_le", "last_login")
    filter_horizontal = ("groups", "user_permissions")
    actions = ("envoyer_invitation",)
    fieldsets = (
        (None, {"fields": ("email", "personne", "role", "is_active")}),
        ("Droits", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Suivi", {"fields": ("date_creation", "invite_le", "active_le", "last_login")}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # A la creation, les champs de suivi n'existent pas encore.
            return (
                (None, {"fields": ("email", "personne", "role", "is_active")}),
                ("Droits", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
            )
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            # Aucun mot de passe utilisable n'est jamais defini.
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)
        journaliser(
            Action.COMPTE_MODIFIE if change else Action.COMPTE_CREE,
            qui=request.user,
            objet=obj,
        )

    @admin.action(description="Envoyer une invitation")
    def envoyer_invitation(self, request, queryset):
        """Envoie le mail d'invitation. Ce mail ne contient AUCUN jeton."""
        envoyees = 0
        echecs = 0
        for compte in queryset:
            if envoyer_mail(compte.email, OBJET_INVITATION, texte_invitation()):
                compte.invite_le = timezone.now()
                compte.save(update_fields=["invite_le"])
                journaliser(Action.INVITATION_ENVOYEE, qui=request.user, objet=compte)
                envoyees += 1
            else:
                echecs += 1

        if envoyees:
            self.message_user(
                request, f"{envoyees} invitation(s) envoyée(s).", messages.SUCCESS
            )
        if echecs:
            self.message_user(
                request,
                f"{echecs} invitation(s) non envoyée(s) : webhook mail indisponible "
                "ou non configuré.",
                messages.WARNING,
            )
