"""Vues d'authentification : demande de lien, connexion, déconnexion."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from sesame.utils import get_query_string
from sesame.views import LoginView as LoginViewSesame

from audit.models import Action
from audit.services import journaliser
from socle.debit import depasse, limite_par_ip

from .forms import FormulaireConnexion
from .mails import OBJET_LIEN, envoyer_mail, texte_lien

# Plafonds par défaut si le réglage manque : les mêmes que `config/settings.py`.
# DEBIT_IP_DEFAUT provisoirement large (brique 2-ter) : voir config/settings.py.
DEBIT_IP_DEFAUT = (100, 900)
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
