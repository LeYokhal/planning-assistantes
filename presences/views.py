"""Vues des présences : écran du mois et import d'un fichier S7."""

import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from comptes.acces import role_requis
from comptes.models import Compte

from . import services
from .fenetres import libelle_mois, mois_de_fenetre, mois_precedent, mois_suivant, plage_mois
from .forms import FormulaireImportFichier
from .models import ImportPresences

logger = logging.getLogger(__name__)

CABINET = Compte.Role.CABINET
PRINCIPALE = Compte.Role.PRINCIPALE


@role_requis(CABINET, PRINCIPALE)
def presences_courant(request):
    """`/presences/` → l'écran du mois en cours (fuseau Europe/Paris)."""
    return redirect("presences:mois", mois=timezone.localdate().strftime("%Y-%m"))


@role_requis(CABINET, PRINCIPALE)
def presences_mois(request, mois):
    """Écran « présences du mois » : semaines complètes, un agenda par ligne."""
    try:
        plage = plage_mois(mois)
    except ValueError:
        raise Http404("mois invalide") from None

    return render(
        request,
        "presences/mois.html",
        {
            "mois": mois,
            "libelle": libelle_mois(mois),
            "plage": plage,
            "couverture": services.couverture(plage.debut, plage.fin),
            "precedent": mois_precedent(mois),
            "suivant": mois_suivant(mois),
            "peut_importer": request.user.role == CABINET,
        },
    )


@role_requis(CABINET)
def importer_fichier(request):
    """Dépôt d'un payload S7. Synchrone : la lecture dure moins d'une seconde."""
    if request.method != "POST":
        return render(
            request,
            "presences/importer.html",
            {"formulaire": FormulaireImportFichier()},
        )

    formulaire = FormulaireImportFichier(request.POST, request.FILES)
    if not formulaire.is_valid():
        return render(request, "presences/importer.html", {"formulaire": formulaire})

    fichier = formulaire.cleaned_data["fichier"]
    import_ = services.importer_fichier(fichier.read(), request.user, fichier.name)

    if import_.statut != ImportPresences.Statut.REUSSI:
        messages.error(request, f"Import #{import_.pk} en échec : {import_.erreur}")
        return redirect("presences:importer")

    messages.success(
        request,
        f"Import #{import_.pk} : fenêtre du {import_.debut:%d/%m/%Y} "
        f"au {import_.fin:%d/%m/%Y}, invariant OK, {import_.nb_lignes} lignes.",
    )
    doublon = services.doublon_de(import_)
    if doublon is not None:
        messages.info(request, f"Identique à l'import #{doublon.pk} déjà en base.")

    return redirect(
        "presences:mois", mois=mois_de_fenetre(import_.debut, import_.fin)
    )
