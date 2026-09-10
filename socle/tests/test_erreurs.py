"""Pages d'état de la coquille (brique 6a) : 403, 404, 500 et lien magique périmé."""

import re
from unittest.mock import patch

import pytest
from django.test import Client, RequestFactory
from django.views.defaults import server_error
from sesame.utils import get_query_string

pytestmark = pytest.mark.django_db

MOTIF_CSRF = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')
# Adresse IP de documentation (RFC 5737).
IP_TEST = "192.0.2.10"
ADRESSE_INCONNUE = "personne-sans-compte@example.org"


def _sans_jeton(reponse):
    return MOTIF_CSRF.sub('name="csrfmiddlewaretoken" value="X"', reponse.content.decode())


# --- 403 ---------------------------------------------------------------------


def test_403_salariee_vers_ses_jours(client, salariee, connecter):
    connecter(client, salariee)
    reponse = client.get("/planning/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 403
    assert "Vous n'avez pas accès à cette page" in contenu
    assert 'href="/mes-jours/">Aller à mes jours</a>' in contenu
    assert "Retour à l'accueil" not in contenu
    assert "Congé payé" not in contenu


def test_403_principale_vers_le_tableau_de_bord(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get("/personnes/importer/")
    assert reponse.status_code == 403
    assert 'href="/">Aller à mon tableau de bord</a>' in reponse.content.decode()


# --- 404 ---------------------------------------------------------------------


def test_404_connectee(client, salariee, principale, connecter):
    connecter(client, salariee)
    reponse = client.get("/nexiste-pas/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 404
    assert "Cette page n'existe pas" in contenu
    assert 'href="/mes-jours/">Aller à mes jours</a>' in contenu
    client.logout()
    connecter(client, principale)
    assert 'href="/">Aller à mon tableau de bord</a>' in client.get("/nexiste-pas/").content.decode()


def test_404_anonyme(client):
    reponse = client.get("/nexiste-pas/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 404
    assert "Cette page n'existe pas" in contenu
    assert 'href="/connexion/">Se connecter</a>' in contenu
    assert 'class="avatar"' not in contenu


# --- 500 ---------------------------------------------------------------------


def test_500_se_rend_sans_contexte():
    reponse = server_error(RequestFactory().get("/x/"))
    contenu = reponse.content.decode()
    assert reponse.status_code == 500
    assert "Une erreur est survenue" in contenu
    assert "{%" not in contenu and "{{" not in contenu
    assert 'class="barre"' not in contenu


def test_500_par_le_gestionnaire(principale):
    client = Client(raise_request_exception=False)
    client.get("/connexion/lien/" + get_query_string(principale))
    with patch("socle.views.render", side_effect=RuntimeError("boum")):
        reponse = client.get("/")
    assert reponse.status_code == 500
    assert "Une erreur est survenue" in reponse.content.decode()


# --- Lien magique périmé (décision A-1) -------------------------------------


@pytest.mark.parametrize("url", ["/connexion/lien/?sesame=jeton-invente", "/connexion/lien/"])
def test_lien_invalide_redirige_vers_la_connexion(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 302
    assert reponse["Location"] == "/connexion/?expire=1"


def test_bandeau_lien_expire(client):
    avec = client.get("/connexion/?expire=1").content.decode()
    assert "Ce lien a expiré ou a déjà été utilisé" in avec
    assert 'name="email"' in avec
    assert "Ce lien a expiré" not in client.get("/connexion/").content.decode()


def test_expire_n_altere_pas_la_reponse_neutre(client):
    with patch("comptes.views.envoyer_mail", return_value=True):
        avec = client.post("/connexion/?expire=1", {"email": ADRESSE_INCONNUE})
        sans = client.post("/connexion/", {"email": ADRESSE_INCONNUE})
    assert avec.status_code == sans.status_code == 200
    assert _sans_jeton(avec) == _sans_jeton(sans)


def test_429_sans_formulaire(client, settings):
    settings.DEBIT_CONNEXION_IP = (1, 900)
    client.post("/connexion/", {"email": ADRESSE_INCONNUE}, HTTP_X_FORWARDED_FOR=IP_TEST)
    reponse = client.post("/connexion/", {"email": ADRESSE_INCONNUE}, HTTP_X_FORWARDED_FOR=IP_TEST)
    contenu = reponse.content.decode()
    assert reponse.status_code == 429
    assert "Trop de demandes" in contenu
    assert 'name="email"' not in contenu
