"""Vues des personnes : liste, import de la fiche, appariement Doctolib."""

import logging

from django.contrib import messages
from django.shortcuts import redirect, render

from comptes.acces import role_requis
from comptes.models import Compte, Personne
from regles.chargeur import verifier

from . import services
from .appariement import appliquer, apparier
from .forms import FormulaireImportFiche
from .lecture_fiche import FicheInvalide, lire

logger = logging.getLogger(__name__)

CABINET = Compte.Role.CABINET
PRINCIPALE = Compte.Role.PRINCIPALE


def _libelle_compte(personne):
    """« aucun », « invité le … » ou « activé le … » pour la colonne compte."""
    compte = getattr(personne, "compte", None)
    if compte is None:
        return "aucun"
    if compte.active_le:
        return f"activé le {compte.active_le:%d/%m/%Y}"
    if compte.invite_le:
        return f"invité le {compte.invite_le:%d/%m/%Y}"
    return "créé, non invité"


@role_requis(CABINET, PRINCIPALE)
def personnes_liste(request):
    """Toutes les personnes connues, et l'état des règles face à elles."""
    personnes = list(Personne.objects.select_related("compte"))
    for personne in personnes:
        personne.libelle_compte = _libelle_compte(personne)

    return render(
        request,
        "personnes/liste.html",
        {
            "personnes": personnes,
            "regles": verifier(personnes),
            "peut_agir": request.user.role == CABINET,
        },
    )


@role_requis(CABINET)
def importer_fiche(request):
    """Dépôt d'un export de la fiche. Synchrone : la lecture est immédiate."""
    if request.method != "POST":
        return render(
            request,
            "personnes/importer.html",
            {"formulaire": FormulaireImportFiche()},
        )

    formulaire = FormulaireImportFiche(request.POST, request.FILES)
    if not formulaire.is_valid():
        return render(request, "personnes/importer.html", {"formulaire": formulaire})

    try:
        lecture = lire(formulaire.cleaned_data["fichier"].read())
    except FicheInvalide as erreur:
        messages.error(request, f"Fichier refusé : {erreur}")
        return render(
            request,
            "personnes/importer.html",
            {"formulaire": FormulaireImportFiche()},
        )

    rapport = services.importer_fiche(lecture, request.user)
    return render(
        request,
        "personnes/importer.html",
        {"formulaire": FormulaireImportFiche(), "rapport": rapport},
    )


@role_requis(CABINET)
def appariement(request):
    """Propose un agenda Doctolib par praticien planifié, puis l'applique."""
    agendas = services.agendas_pour_appariement()
    rapport = apparier(agendas)

    if request.method == "POST":
        ecrits = appliquer(rapport, request.user)
        messages.success(
            request,
            f"Appariement appliqué : {ecrits['exact']} exact(s), "
            f"{ecrits['approche']} approché(s).",
        )
        return redirect("personnes:appariement")

    return render(
        request,
        "personnes/appariement.html",
        {"rapport": rapport, "agendas": agendas},
    )
