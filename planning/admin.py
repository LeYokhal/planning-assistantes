"""Administration des versions du planning : consultation seule, et import historique.

Une version n'est jamais modifiée ni supprimée depuis l'administration — c'est
la trace de ce qui a été enregistré. Le `state` est affiché tel quel : il ne
porte ni congé, ni type d'absence, ni nom, seulement des identifiants.

Brique 7a (C7.1) : l'écran « Importer un planning historique » ajoute une route
à `get_urls`, sur le patron **exact** de `absences/admin.py` (3-quater). Il ne
touche pas aux trois `has_*_permission`, qui restent à `False` : une route de
`get_urls` ne passe pas par elles, et rien ne devient modifiable pour autant.

⚠️ Les logs de ce module ne portent que le mois, un numéro et des comptages.
"""

import datetime
import logging

from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from comptes.acces import role_requis
from comptes.models import Compte

from . import historique, services
from .forms import FormulaireImportHistorique
from .models import PlanningVersion

logger = logging.getLogger(__name__)

# Brique 7a : l'état d'un import entre l'analyse et la confirmation vit en
# session — jamais sur disque — et périme après ce délai, le même que la
# 3-quater. Les deux helpers ci-dessous en sont recopiés (décision D10) : les
# factoriser toucherait une brique livrée et recettée.
CLE_SESSION_IMPORT_HISTORIQUE = "import_planning_historique"
IMPORT_SESSION_MINUTES = 15
GABARIT_IMPORT_HISTORIQUE = "admin/planning/planningversion/importer.html"


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


@admin.register(PlanningVersion)
class PlanningVersionAdmin(admin.ModelAdmin):
    """Historique des versions, strictement non modifiable."""

    list_display = (
        "mois",
        "numero",
        "version_de_base",
        "auteur",
        "cree_le",
        "publiee",
        "est_historique",
    )
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

    @admin.display(description="historique", boolean=True)
    def est_historique(self, obj):
        """Colonne calculée depuis `verifications` : aucun champ, donc aucun filtre."""
        return services.est_historique(obj)

    # --- Brique 7a : import d'un planning historique (C7.1) ---------------------

    def get_urls(self):
        """Ajoute `importer-historique/` AVANT les routes natives.

        `<path:object_id>/` capturerait la route si elle venait après.
        `role_requis(CABINET)` enveloppe `admin_view` de l'extérieur : un rôle
        `principale` ou `salariee` reçoit le 403 journalisé du projet, pas la
        redirection de connexion de l'admin. `admin_view` conserve la protection
        CSRF, `never_cache` et l'exigence `is_staff`. Aucune garde `is_superuser`.
        """
        propres = [
            path(
                "importer-historique/",
                role_requis(Compte.Role.CABINET)(
                    self.admin_site.admin_view(self.vue_import_historique)
                ),
                name="planning_planningversion_importer_historique",
            )
        ]
        return propres + super().get_urls()

    def _contexte_import(self, request, **extra):
        contexte = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "Importer un planning historique",
            "formulaire": FormulaireImportHistorique(),
            "analyse": None,
            "resultat": None,
        }
        contexte.update(extra)
        return contexte

    def vue_import_historique(self, request):
        """Écran d'import en deux temps : analyse du fichier, puis confirmation.

        GET repart toujours du formulaire vide et efface l'analyse en cours.
        Le premier POST porte le fichier ; le second, « confirmer », l'empreinte
        et le comptage du rapport lu. Rien n'est écrit avant la confirmation.
        """
        if request.method != "POST":
            request.session.pop(CLE_SESSION_IMPORT_HISTORIQUE, None)
            return render(
                request, GABARIT_IMPORT_HISTORIQUE, self._contexte_import(request)
            )
        if request.POST.get("confirmer"):
            return self._confirmer_historique(request)
        return self._analyser_historique(request)

    def _analyser_historique(self, request):
        """Premier temps : lecture, analyse, rapport. Le fichier décodé va en session."""
        request.session.pop(CLE_SESSION_IMPORT_HISTORIQUE, None)
        formulaire = FormulaireImportHistorique(request.POST, request.FILES)
        if not formulaire.is_valid():
            return render(
                request,
                GABARIT_IMPORT_HISTORIQUE,
                self._contexte_import(request, formulaire=formulaire),
            )

        planning = formulaire.cleaned_data["planning"]
        analyse = historique.analyser(planning)
        request.session[CLE_SESSION_IMPORT_HISTORIQUE] = {
            "empreinte": analyse.empreinte,
            "depuis": timezone.now().isoformat(),
            "planning": planning,
        }
        logger.info(
            "import planning historique : analyse %s, verdict %s, %s refus",
            analyse.mois or "?",
            analyse.verdict,
            len(analyse.erreurs),
        )
        return render(
            request,
            GABARIT_IMPORT_HISTORIQUE,
            self._contexte_import(request, analyse=analyse),
        )

    def _confirmer_historique(self, request):
        """Second temps : empreinte, fraîcheur, rejeu de l'analyse, puis écriture."""
        etat = request.session.get(CLE_SESSION_IMPORT_HISTORIQUE)
        empreinte = request.POST.get("empreinte", "")
        if not etat or not empreinte or etat.get("empreinte") != empreinte:
            request.session.pop(CLE_SESSION_IMPORT_HISTORIQUE, None)
            messages.error(
                request,
                "Aucune analyse en cours pour ce fichier : téléversez-le à nouveau.",
            )
            return render(
                request, GABARIT_IMPORT_HISTORIQUE, self._contexte_import(request)
            )
        if _perime(etat.get("depuis")):
            request.session.pop(CLE_SESSION_IMPORT_HISTORIQUE, None)
            messages.error(
                request,
                f"L'analyse date de plus de {IMPORT_SESSION_MINUTES} minutes : "
                "téléversez le fichier à nouveau.",
            )
            return render(
                request, GABARIT_IMPORT_HISTORIQUE, self._contexte_import(request)
            )

        # Rejeu : la base a pu changer entre les deux POST (une version
        # enregistrée depuis un autre onglet). Le rapport confirmé doit être
        # celui que l'écriture va suivre.
        analyse = historique.analyser(etat["planning"])
        if (
            not analyse.peut_confirmer
            or analyse.empreinte != empreinte
            or analyse.nb_briques != _entier(request.POST.get("nb_briques"))
        ):
            etat["depuis"] = timezone.now().isoformat()
            request.session[CLE_SESSION_IMPORT_HISTORIQUE] = etat
            logger.info(
                "import planning historique : confirmation refusee, rapport rejoue "
                "(verdict %s)",
                analyse.verdict,
            )
            messages.warning(
                request,
                "La base a changé depuis l'analyse : relisez le rapport avant de "
                "confirmer.",
            )
            return render(
                request,
                GABARIT_IMPORT_HISTORIQUE,
                self._contexte_import(request, analyse=analyse),
            )

        try:
            version = historique.executer(analyse, request.user)
        except historique.ActionImpossible as erreur:
            messages.error(request, str(erreur))
            return render(
                request,
                GABARIT_IMPORT_HISTORIQUE,
                self._contexte_import(request, analyse=analyse),
            )

        request.session.pop(CLE_SESSION_IMPORT_HISTORIQUE, None)
        messages.success(
            request,
            f"Import terminé : {analyse.mois} version {version.numero}, "
            f"{analyse.nb_briques} brique(s) sur {analyse.nb_jours} jour(s), "
            "publiée et marquée historique.",
        )
        return render(
            request,
            GABARIT_IMPORT_HISTORIQUE,
            self._contexte_import(request, analyse=analyse, resultat=version),
        )
