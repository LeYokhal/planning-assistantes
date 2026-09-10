"""Processeur de contexte de la coquille (brique 6a) : garde, navigation courante, paresse, coût.

Les nombres de requêtes sont figés : la barre ne coûte rien à un compte sans
personne ; la page planning porte en plus, depuis la brique 6d, la requête
`Max("importe_le")` de la pastille « Données Doctolib du … », et une lecture
de `personne` pour un compte rattaché.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import ResolverMatch

from absences.tests import fabrique as fabrique_absences
from planning import services
from planning.tests import fabrique
from socle.contexte import coquille

pytestmark = pytest.mark.django_db

VIDE = {"nav_courante": "", "initiales": "", "prenom": ""}


def _requete(utilisateur=None, app_name="", url_name=""):
    requete = RequestFactory().get("/")
    if utilisateur is not None:
        requete.user = utilisateur
    requete.resolver_match = ResolverMatch(
        lambda r: None, (), {}, url_name=url_name, app_names=[app_name] if app_name else []
    )
    return requete


# --- Garde -------------------------------------------------------------------


def test_requete_sans_utilisateur():
    assert coquille(RequestFactory().get("/")) == VIDE


def test_anonyme():
    assert coquille(_requete(AnonymousUser())) == VIDE


def test_compte_sans_personne(principale):
    contexte = coquille(_requete(principale))
    assert str(contexte["initiales"]) == "A"  # « Assistante principale »
    assert str(contexte["prenom"]) == ""
    assert not contexte["prenom"]


def test_compte_rattache(principale):
    fabrique_absences.lier(principale, fabrique_absences.personne())
    contexte = coquille(_requete(principale))
    assert str(contexte["initiales"]) == "AD"
    assert str(contexte["prenom"]) == "Alice"
    assert contexte["prenom"]


def test_cabinet_sans_personne(cabinet):
    assert str(coquille(_requete(cabinet))["initiales"]) == "C"


# --- Navigation courante -----------------------------------------------------


@pytest.mark.parametrize(
    ("app_name", "url_name", "attendu"),
    [
        ("planning", "mois", "planning"),
        ("planning", "courant", "planning"),
        ("planning", "mes_jours", "mes_jours"),
        ("planning", "mes_jours_courant", "mes_jours"),
        ("absences", "decider", "absences"),
        ("absences", "mes_absences", "mes_absences"),
        ("absences", "nouvelle", "mes_absences"),
        ("absences", "annuler", "mes_absences"),
        ("presences", "mois", "donnees"),
        ("personnes", "liste", "donnees"),
        ("comptes", "profil", "profil"),
        ("comptes", "connexion", ""),
        ("", "accueil", "tableau_de_bord"),
    ],
)
def test_nav_courante(app_name, url_name, attendu):
    assert coquille(_requete(AnonymousUser(), app_name, url_name))["nav_courante"] == attendu


def test_sans_resolution():
    """Une URL inconnue (404) n'a pas de `resolver_match`."""
    requete = RequestFactory().get("/nexiste-pas/")
    requete.user = AnonymousUser()
    assert requete.resolver_match is None
    assert coquille(requete)["nav_courante"] == ""


# --- Paresse -----------------------------------------------------------------


def test_paresse(principale, django_assert_num_queries):
    fabrique_absences.lier(principale, fabrique_absences.personne())
    compte = get_user_model().objects.get(pk=principale.pk)  # relation non mise en cache
    with django_assert_num_queries(0):
        contexte = coquille(_requete(compte))
    with django_assert_num_queries(1):
        str(contexte["initiales"])
        str(contexte["prenom"])


# --- Coût des pages : figé ------------------------------------------------------


def test_cout_page_planning(client, cabinet, connecter, django_assert_num_queries):
    """9 sur `main` avant la 6d, + 1 : la date du dernier import retenu (`_donnees_du`)."""
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    connecter(client, cabinet)
    with django_assert_num_queries(10):
        assert client.get(f"/planning/{fabrique.MOIS}/").status_code == 200


def test_cout_page_planning_principale_rattachee(
    client, principale, cabinet, connecter, django_assert_num_queries
):
    """Compte rattaché : la barre lit `personne` une fois (prénom, initiales) — 10 + 1."""
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    fabrique_absences.lier(principale, fabrique_absences.personne(nom="LEFEVRE", prenom="Manon"))
    connecter(client, principale)
    with django_assert_num_queries(11):
        assert client.get(f"/planning/{fabrique.MOIS}/").status_code == 200


def test_cout_page_sans_import(client, cabinet, connecter, django_assert_num_queries):
    connecter(client, cabinet)
    with django_assert_num_queries(4):
        assert client.get(f"/planning/{fabrique.MOIS}/").status_code == 200


def test_cout_admin(client, cabinet, connecter, django_assert_num_queries):
    connecter(client, cabinet)
    with django_assert_num_queries(3):
        assert client.get("/admin/").status_code == 200


def test_cout_pages_anonymes(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert client.get("/connexion/").status_code == 200
    with django_assert_num_queries(0):
        assert client.get("/nexiste-pas/").status_code == 404
