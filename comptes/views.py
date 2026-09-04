"""Vues d'authentification : demande de lien, connexion, déconnexion."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from sesame.utils import get_query_string
from sesame.views import LoginView as LoginViewSesame

from audit.models import Action
from audit.services import journaliser
from socle.debit import depasse, limite_par_ip

from . import profil as profil_adresse
from .acces import role_requis
from .forms import FormulaireConnexion, FormulaireAdresse
from .mails import (
    OBJET_ADRESSE,
    OBJET_LIEN,
    envoyer_mail,
    texte_adresse,
    texte_lien,
)
from .models import Compte

# Plafonds par défaut si le réglage manque : les mêmes que `config/settings.py`.
DEBIT_IP_DEFAUT = (10, 900)
DEBIT_ADRESSE_DEFAUT = (5, 3600)


def construire_lien(compte):
    """Construit l'URL de connexion à usage unique pour un compte."""
    return f"{settings.APP_URL}/connexion/lien/{get_query_string(compte)}"


def _contexte_envoye():
    """Contexte de la reponse neutre, strictement identique dans tous les cas."""
    return {"formulaire": FormulaireConnexion(), "envoye": True}


def _reponse_429(request):
    """Page de blocage par adresse IP. Seul cas où la page de connexion diffère."""
    return render(
        request,
        "comptes/connexion.html",
        {"formulaire": FormulaireConnexion(), "bloque": True},
        status=429,
    )


@limite_par_ip(
    "connexion", "DEBIT_CONNEXION_IP", reponse=_reponse_429, defaut=DEBIT_IP_DEFAUT
)
def demander_lien(request):
    """Formulaire de demande d'un lien de connexion.

    Quel que soit le sort de la demande — adresse inconnue, compte inactif,
    envoi impossible, débit dépassé sur l'adresse — la page renvoyée est
    strictement la même. Seul le plafond par IP répond différemment (429) : il
    protège la page elle-même, et ne dit rien d'un compte en particulier.
    """
    formulaire = FormulaireConnexion(request.POST or None)

    if request.method != "POST":
        return render(request, "comptes/connexion.html", {"formulaire": formulaire})

    if not formulaire.is_valid():
        # Adresse mal formée : traitée comme une adresse inconnue.
        journaliser(Action.LIEN_REFUSE, motif="inconnu")
        return render(request, "comptes/connexion.html", _contexte_envoye())

    email = formulaire.cleaned_data["email"]

    # Plafond par adresse, AVANT toute requête sur `Compte` : le temps de
    # réponse ne doit pas trahir l'existence du compte.
    if depasse(
        "connexion-adresse",
        email,
        getattr(settings, "DEBIT_CONNEXION_ADRESSE", DEBIT_ADRESSE_DEFAUT),
    ):
        journaliser(Action.LIEN_REFUSE, motif="debit")
        return render(request, "comptes/connexion.html", _contexte_envoye())

    Compte = get_user_model()
    compte = Compte.objects.filter(email__iexact=email).first()

    if compte is None:
        journaliser(Action.LIEN_REFUSE, motif="inconnu")
    elif not compte.is_active:
        journaliser(Action.LIEN_REFUSE, qui=None, objet=compte, motif="inactif")
    else:
        envoye = envoyer_mail(compte.email, OBJET_LIEN, texte_lien(construire_lien(compte)))
        journaliser(Action.LIEN_DEMANDE, objet=compte, envoye=envoye)

    return render(request, "comptes/connexion.html", _contexte_envoye())


class VueConnexionLien(LoginViewSesame):
    """Consomme le lien de connexion.

    django-sesame renvoie bien 403 sur un jeton invalide ou déjà utilisé, mais
    n'écrit aucun événement d'audit. On utilise son crochet d'échec dédié
    `login_failed()` pour journaliser `connexion_refusee` avant de laisser
    remonter la PermissionDenied telle quelle. `lien_refuse` reste réservé aux
    refus d'envoi (adresse inconnue, compte inactif).
    """

    next_page = "/"

    def login_failed(self):
        journaliser(Action.CONNEXION_REFUSEE, motif="jeton_invalide")
        return super().login_failed()


@role_requis(Compte.Role.SALARIEE, Compte.Role.PRINCIPALE)
def profil(request):
    """Demande de changement de l'adresse de connexion (décision L).

    Réponse strictement identique que l'adresse soit libre ou déjà prise : le
    formulaire ne doit pas devenir un oracle d'existence de comptes. Dans le
    second cas, aucun mail n'est envoyé.
    """
    formulaire = FormulaireAdresse(request.POST or None)

    if request.method != "POST":
        return render(request, "comptes/profil.html", {"formulaire": formulaire})

    if not formulaire.is_valid():
        return render(request, "comptes/profil.html", {"formulaire": formulaire})

    adresse = formulaire.cleaned_data["email"]
    Compte_ = get_user_model()
    deja_prise = (
        Compte_.objects.filter(email__iexact=adresse)
        .exclude(pk=request.user.pk)
        .exists()
    )

    if not deja_prise:
        request.user.email_en_attente = adresse
        request.user.save(update_fields=["email_en_attente"])
        lien = (
            f"{settings.APP_URL}/mon-profil/confirmer/"
            f"{profil_adresse.fabriquer_jeton(request.user, adresse)}/"
        )
        envoyer_mail(adresse, OBJET_ADRESSE, texte_adresse(lien))

    return render(
        request,
        "comptes/profil.html",
        {"formulaire": FormulaireAdresse(), "envoye": True},
    )


@login_required
def confirmer_adresse(request, jeton):
    """Consomme le lien de confirmation et bascule l'adresse de connexion.

    `SESAME_INVALIDATE_ON_EMAIL_CHANGE` étant vrai, tous les liens magiques en
    circulation meurent à cet instant : c'est voulu.
    """
    identifiant, adresse = profil_adresse.lire_jeton(jeton)
    compte = request.user

    refus = (
        identifiant is None
        or identifiant != compte.pk
        # L'usage unique tient à ce champ : vidé à la confirmation, il fait
        # échouer tout rejeu du même lien.
        or (compte.email_en_attente or "").casefold() != adresse.casefold()
    )
    if refus:
        messages.error(
            request, "Ce lien de confirmation n'est plus valable. Recommencez."
        )
        return redirect("comptes:profil")

    Compte_ = get_user_model()
    if Compte_.objects.filter(email__iexact=adresse).exclude(pk=compte.pk).exists():
        compte.email_en_attente = ""
        compte.save(update_fields=["email_en_attente"])
        messages.error(
            request, "Ce lien de confirmation n'est plus valable. Recommencez."
        )
        return redirect("comptes:profil")

    compte.email = adresse
    compte.email_en_attente = ""
    compte.save(update_fields=["email", "email_en_attente"])

    # L'adresse de contact suit, sinon la prochaine invitation repartirait sur
    # l'ancienne.
    personne = compte.personne
    if personne is not None:
        personne.email_contact = adresse
        personne.save(update_fields=["email_contact"])

    journaliser(Action.ADRESSE_CHANGEE, qui=compte, objet=compte)
    messages.success(request, "Votre adresse de connexion est à jour.")
    return redirect("comptes:profil")


class VueDeconnexion(LogoutView):
    """Déconnexion. POST uniquement, conformément à Django 5."""

    next_page = settings.LOGOUT_REDIRECT_URL


class VueDeconnexionAdmin(LogoutView):
    """Point d'entrée /admin/logout/.

    En GET, redirige vers l'accueil : /deconnexion/ n'accepte que le POST et
    renverrait un 405. En POST — la forme employée par le bouton de déconnexion
    de l'administration — la déconnexion est effectuée normalement.
    """

    next_page = settings.LOGOUT_REDIRECT_URL

    def get(self, request, *args, **kwargs):
        return redirect("/")
