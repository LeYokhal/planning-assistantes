"""Administration des absences.

`AbsenceSalariee` est modifiable ici — c'est le canal de reprise de l'existant
Notion, qui n'est pas migré (décision du 01/09). Toute écriture est journalisée,
sur le patron de `comptes/admin.py`.

⚠️ Les événements d'audit émis d'ici ne portent **ni le type ni la précision**.
"""

import datetime
import logging

from django import forms
from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser
from comptes.acces import role_requis
from comptes.models import Compte

from . import calcul, services
from .forms import FormulaireImport
from .models import AbsenceSalariee, TypeAbsence

logger = logging.getLogger(__name__)

# Brique 3-quater (C3.9) : l'état d'un import entre l'analyse et la
# confirmation vit en session — jamais sur disque — et périme après ce délai,
# le même que le verrou d'import de la 1b, en constante locale.
CLE_SESSION_IMPORT = "import_absences"
IMPORT_SESSION_MINUTES = 15
GABARIT_IMPORT = "admin/absences/absencesalariee/importer.html"


def _peut_confirmer(compteurs):
    """Le bouton n'apparaît que sans erreur et avec au moins une absence à créer."""
    return (
        compteurs[services.VERDICT_ERREUR] == 0
        and compteurs[services.VERDICT_CREER] > 0
    )


def _perime(depuis):
    """Vrai si l'analyse en session a dépassé le délai, ou si l'horodatage est illisible."""
    try:
        horodatage = datetime.datetime.fromisoformat(str(depuis))
    except (TypeError, ValueError):
        return True
    if timezone.is_naive(horodatage):
        return True
    return timezone.now() - horodatage > datetime.timedelta(
        minutes=IMPORT_SESSION_MINUTES
    )


def _entier(valeur):
    """Un compteur de champ caché, ou -1 s'il est absent ou illisible."""
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return -1


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

    # --- Brique 3-quater : import exceptionnel de l'existant Notion (C3.9) -----

    def get_urls(self):
        """Ajoute `importer/` AVANT les routes natives : `<path:object_id>/` la capturerait.

        `role_requis(CABINET)` enveloppe `admin_view` de l'extérieur : un rôle
        `principale` ou `salariee` reçoit le 403 journalisé du projet, pas la
        redirection de connexion de l'admin. `admin_view` conserve la protection
        CSRF, `never_cache` et l'exigence `is_staff`. Aucune garde `is_superuser`.
        """
        propres = [
            path(
                "importer/",
                role_requis(Compte.Role.CABINET)(
                    self.admin_site.admin_view(self.vue_import)
                ),
                name="absences_absencesalariee_importer",
            )
        ]
        return propres + super().get_urls()

    def _contexte_import(self, request, **extra):
        contexte = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "Importer des absences",
            "formulaire": FormulaireImport(),
            "rapport": None,
            "compteurs": None,
            "empreinte": "",
            "peut_confirmer": False,
            "resultat": None,
        }
        contexte.update(extra)
        return contexte

    def vue_import(self, request):
        """Écran d'import en deux temps : analyse du fichier, puis confirmation (J2).

        GET repart toujours du formulaire vide et efface l'analyse en cours.
        Le premier POST porte le fichier ; le second, « confirmer », l'empreinte
        et les compteurs du rapport lu. Rien n'est écrit avant la confirmation.
        """
        if request.method != "POST":
            request.session.pop(CLE_SESSION_IMPORT, None)
            return render(request, GABARIT_IMPORT, self._contexte_import(request))
        if request.POST.get("confirmer"):
            return self._confirmer_import(request)
        return self._analyser_fichier(request)

    def _analyser_fichier(self, request):
        """Premier temps : lecture, analyse, rapport. Le fichier normalisé va en session."""
        request.session.pop(CLE_SESSION_IMPORT, None)
        formulaire = FormulaireImport(request.POST, request.FILES)
        if not formulaire.is_valid():
            return render(
                request,
                GABARIT_IMPORT,
                self._contexte_import(request, formulaire=formulaire),
            )

        absences = formulaire.cleaned_data["absences"]
        empreinte = formulaire.cleaned_data["empreinte"]
        lignes = services.analyser_import(absences)
        compteurs = services.compter_verdicts(lignes)
        request.session[CLE_SESSION_IMPORT] = {
            "empreinte": empreinte,
            "depuis": timezone.now().isoformat(),
            "absences": absences,
        }
        logger.info(
            "import absences : analyse, %s ligne(s), %s erreur(s)",
            len(lignes),
            compteurs[services.VERDICT_ERREUR],
        )
        return render(
            request,
            GABARIT_IMPORT,
            self._contexte_import(
                request,
                rapport=lignes,
                compteurs=compteurs,
                empreinte=empreinte,
                peut_confirmer=_peut_confirmer(compteurs),
            ),
        )

    def _confirmer_import(self, request):
        """Second temps : empreinte, fraîcheur, rejeu de l'analyse, puis écriture."""
        etat = request.session.get(CLE_SESSION_IMPORT)
        empreinte = request.POST.get("empreinte", "")
        if not etat or not empreinte or etat.get("empreinte") != empreinte:
            request.session.pop(CLE_SESSION_IMPORT, None)
            messages.error(
                request,
                "Aucune analyse en cours pour ce fichier : téléversez-le à nouveau.",
            )
            return render(request, GABARIT_IMPORT, self._contexte_import(request))
        if _perime(etat.get("depuis")):
            request.session.pop(CLE_SESSION_IMPORT, None)
            messages.error(
                request,
                f"L'analyse date de plus de {IMPORT_SESSION_MINUTES} minutes : "
                "téléversez le fichier à nouveau.",
            )
            return render(request, GABARIT_IMPORT, self._contexte_import(request))

        # Rejeu (E5) : la base a pu changer entre les deux POST. Le rapport
        # confirmé doit être celui que l'écriture va suivre.
        lignes = services.analyser_import(etat["absences"])
        compteurs = services.compter_verdicts(lignes)
        attendus = {
            verdict: _entier(request.POST.get(f"nb_{verdict}"))
            for verdict in (services.VERDICT_CREER, services.VERDICT_DEJA_PRESENTE)
        }
        if compteurs[services.VERDICT_ERREUR] or any(
            compteurs[verdict] != attendu for verdict, attendu in attendus.items()
        ):
            etat["depuis"] = timezone.now().isoformat()
            request.session[CLE_SESSION_IMPORT] = etat
            logger.info(
                "import absences : confirmation refusee, rapport rejoue (%s erreur(s))",
                compteurs[services.VERDICT_ERREUR],
            )
            messages.warning(
                request,
                "La base a changé depuis l'analyse : relisez le rapport avant de "
                "confirmer.",
            )
            return render(
                request,
                GABARIT_IMPORT,
                self._contexte_import(
                    request,
                    rapport=lignes,
                    compteurs=compteurs,
                    empreinte=empreinte,
                    peut_confirmer=_peut_confirmer(compteurs),
                ),
            )

        try:
            resultat = services.executer_import(lignes, request.user, empreinte)
        except services.ActionImpossible as erreur:
            messages.error(request, str(erreur))
            return render(
                request,
                GABARIT_IMPORT,
                self._contexte_import(
                    request, rapport=lignes, compteurs=compteurs, empreinte=empreinte
                ),
            )

        request.session.pop(CLE_SESSION_IMPORT, None)
        messages.success(
            request,
            f"Import terminé : {resultat['nb_creees']} absence(s) créée(s), "
            f"{resultat['nb_ignorees']} déjà présente(s).",
        )
        return render(
            request,
            GABARIT_IMPORT,
            self._contexte_import(
                request, rapport=lignes, compteurs=compteurs, resultat=resultat
            ),
        )

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
