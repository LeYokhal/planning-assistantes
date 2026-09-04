"""Vues des absences : espace de la salariée, et écran de décision.

Deux publics, deux écrans. Une salariée ne voit **que** ses absences : le filtre
porte sur `request.user.personne`, jamais sur un identifiant venu de l'URL.

Décision H : un compte sans `Personne` liée existe légalement en base
(`Compte.personne` est nullable). Il ne doit ni provoquer un 500, ni se voir
proposer une saisie : il reçoit un message explicite et rien d'autre.
"""

import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from comptes.acces import role_requis
from comptes.models import Compte
from presences.fenetres import libelle_mois, mois_precedent, mois_suivant, plage_mois

from . import services
from .forms import FormulaireAbsence, FormulaireCorrection
from .models import AbsenceSalariee

logger = logging.getLogger(__name__)

CABINET = Compte.Role.CABINET
PRINCIPALE = Compte.Role.PRINCIPALE
SALARIEE = Compte.Role.SALARIEE
# Brique 3-bis : la principale est aussi une salariée qui pose ses congés. Son
# espace personnel lui est ouvert ; la règle K (`services.peut_decider`) fait
# qu'elle ne tranche jamais sa propre demande. Le cabinet en reste exclu.


def _sans_personne(request):
    """Écran de repli d'un compte non rattaché à une personne (décision H)."""
    return render(request, "absences/sans_personne.html", status=200)


@role_requis(SALARIEE, PRINCIPALE)
def mes_absences(request):
    """Les absences de la salariée connectée, et l'état de ses demandes."""
    personne = request.user.personne
    if personne is None:
        return _sans_personne(request)

    absences = list(
        AbsenceSalariee.objects.filter(personne=personne).select_related("type")
    )
    return render(
        request,
        "absences/mes_absences.html",
        {"absences": absences, "personne": personne},
    )


@role_requis(SALARIEE, PRINCIPALE)
def nouvelle_absence(request):
    """Saisie d'une absence par la salariée."""
    personne = request.user.personne
    if personne is None:
        return _sans_personne(request)

    if request.method != "POST":
        return render(
            request, "absences/nouvelle.html", {"formulaire": FormulaireAbsence()}
        )

    formulaire = FormulaireAbsence(request.POST)
    if not formulaire.is_valid():
        return render(request, "absences/nouvelle.html", {"formulaire": formulaire})

    try:
        absence, _ = services.creer(
            personne=personne,
            type_absence=formulaire.cleaned_data["type"],
            date_debut=formulaire.cleaned_data["date_debut"],
            date_fin=formulaire.cleaned_data["date_fin"],
            auteur=request.user,
            precision=formulaire.cleaned_data["precision"],
        )
    except services.ActionImpossible as erreur:
        messages.error(request, str(erreur))
        return render(request, "absences/nouvelle.html", {"formulaire": formulaire})

    if absence.statut == AbsenceSalariee.Statut.DECLAREE:
        messages.success(request, "Absence enregistrée.")
    else:
        messages.success(request, "Demande envoyée. Elle attend une décision.")
    return redirect("absences:mes_absences")


@role_requis(SALARIEE, PRINCIPALE)
def annuler_absence(request, identifiant):
    """Annulation d'une demande en attente, par la salariée elle-même."""
    if request.method != "POST":
        raise Http404("méthode non autorisée")

    personne = request.user.personne
    if personne is None:
        return _sans_personne(request)

    # Le filtre sur `personne` fait la garde : une salariée ne peut pas
    # atteindre l'absence d'une autre, même en devinant son identifiant.
    absence = get_object_or_404(AbsenceSalariee, pk=identifiant, personne=personne)
    try:
        services.annuler(absence, request.user)
        messages.success(request, "Demande annulée.")
    except services.ActionImpossible as erreur:
        messages.error(request, str(erreur))
    return redirect("absences:mes_absences")


@role_requis(CABINET, PRINCIPALE)
def absences_a_decider(request):
    """Demandes en attente, puis absences du mois."""
    mois = request.GET.get("mois") or timezone.localdate().strftime("%Y-%m")
    try:
        plage = plage_mois(mois)
    except ValueError:
        raise Http404("mois invalide") from None

    en_attente = list(
        AbsenceSalariee.objects.filter(statut=AbsenceSalariee.Statut.EN_ATTENTE)
        .select_related("personne", "type")
        .order_by("date_debut")
    )
    for absence in en_attente:
        absence.decidable = services.peut_decider(absence, request.user)

    du_mois = list(
        services.absences_du_mois(plage.debut, plage.fin, pour_la_paie=False)
    )

    return render(
        request,
        "absences/decider.html",
        {
            "en_attente": en_attente,
            "du_mois": du_mois,
            "mois": mois,
            "libelle": libelle_mois(mois),
            "precedent": mois_precedent(mois),
            "suivant": mois_suivant(mois),
            "formulaire_correction": FormulaireCorrection(),
        },
    )


@role_requis(CABINET, PRINCIPALE)
def decider_absence(request, identifiant):
    """Valide ou refuse une demande. La règle K est appliquée côté serveur."""
    if request.method != "POST":
        raise Http404("méthode non autorisée")

    absence = get_object_or_404(AbsenceSalariee, pk=identifiant)
    valider = request.POST.get("decision") == "valider"

    try:
        signal = services.decider(absence, valider, request.user)
    except services.ActionImpossible as erreur:
        messages.error(request, str(erreur))
        return redirect("absences:decider")

    messages.success(
        request, "Absence validée." if valider else "Demande refusée."
    )
    if signal:
        from .calcul import MESSAGES

        messages.info(request, MESSAGES.get(signal, ""))
    return redirect("absences:decider")


@role_requis(CABINET, PRINCIPALE)
def corriger_absence(request, identifiant):
    """Correction des jours comptés — seule porte des demi-journées."""
    if request.method != "POST":
        raise Http404("méthode non autorisée")

    absence = get_object_or_404(AbsenceSalariee, pk=identifiant)
    formulaire = FormulaireCorrection(request.POST)
    if not formulaire.is_valid():
        messages.error(request, "Valeur illisible.")
        return redirect("absences:decider")

    try:
        services.corriger(
            absence, formulaire.cleaned_data["jours_comptes"], request.user
        )
        messages.success(request, "Jours comptés corrigés.")
    except services.ActionImpossible as erreur:
        messages.error(request, str(erreur))
    return redirect("absences:decider")
