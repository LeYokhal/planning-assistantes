"""Recette du secret de l'API entrante n8n.

Contrôles négatifs de la recette S5 : mauvais secret, en-tête absent, variable
non posée.
"""

import logging

import pytest

# `sante` interroge la base (verrou, lignes interrompues) dès que le secret passe.
pytestmark = pytest.mark.django_db

SECRET = "secret-api-de-test-au-moins-32-caracteres"
SANTE = "/api/n8n/sante/"
IMPORTS = "/api/n8n/imports/"


@pytest.fixture
def poser_secret(settings):
    settings.N8N_API_SECRET = SECRET


def test_variable_absente_desactive_l_api(client, settings, caplog):
    settings.N8N_API_SECRET = ""

    with caplog.at_level(logging.WARNING, logger="n8n.securite"):
        reponse = client.get(SANTE, headers={"X-Api-Secret": SECRET})

    assert reponse.status_code == 503
    assert reponse.json() == {"verdict": "disabled"}
    assert "N8N_API_SECRET absente" in caplog.text


def test_entete_absente_refusee(client, poser_secret):
    reponse = client.get(SANTE)

    assert reponse.status_code == 401
    assert reponse.json() == {"verdict": "unauthorized"}


def test_secret_faux_refuse(client, poser_secret, caplog):
    with caplog.at_level(logging.WARNING, logger="n8n.securite"):
        reponse = client.get(SANTE, headers={"X-Api-Secret": "pas-le-bon"})

    assert reponse.status_code == 401
    assert reponse.json() == {"verdict": "unauthorized"}
    # La valeur reçue ne doit jamais atterrir dans les logs.
    assert "pas-le-bon" not in caplog.text
    assert SECRET not in caplog.text


def test_reponses_identiques_pour_absent_et_faux(client, poser_secret):
    """Rien ne doit distinguer « pas de secret » de « mauvais secret »."""
    sans = client.get(SANTE)
    faux = client.get(SANTE, headers={"X-Api-Secret": "pas-le-bon"})

    assert sans.status_code == faux.status_code == 401
    assert sans.content == faux.content


def test_secret_correct_admis(client, poser_secret):
    reponse = client.get(SANTE, headers={"X-Api-Secret": SECRET})

    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "ok"


def test_secret_verifie_avant_la_methode(client, poser_secret):
    """Un GET sans secret reçoit 401, pas 405 : la route ne se devine pas."""
    assert client.get(IMPORTS).status_code == 401


def test_methode_non_autorisee_en_json(client, poser_secret):
    reponse = client.get(IMPORTS, headers={"X-Api-Secret": SECRET})

    assert reponse.status_code == 405
    assert reponse.json() == {"erreur": "methode_non_autorisee"}


def test_sante_refuse_le_post(client, poser_secret):
    reponse = client.post(SANTE, headers={"X-Api-Secret": SECRET})

    assert reponse.status_code == 405
    assert reponse.json() == {"erreur": "methode_non_autorisee"}
