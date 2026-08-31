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


# --- Limitation de débit -----------------------------------------------------

IP_TEST = "192.0.2.10"


def test_plafond_par_ip_repond_429(client, poser_secret, settings):
    settings.DEBIT_API_N8N_IP = (60, 60)

    codes = [
        client.get(
            SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=IP_TEST
        ).status_code
        for _ in range(61)
    ]

    assert codes[:60] == [200] * 60
    assert codes[60] == 429


def test_plafond_atteint_meme_sans_secret(client, poser_secret, settings):
    """Un appelant sans secret ne doit pas pouvoir marteler la route."""
    settings.DEBIT_API_N8N_IP = (2, 60)

    codes = [
        client.get(SANTE, HTTP_X_FORWARDED_FOR=IP_TEST).status_code for _ in range(3)
    ]

    assert codes == [401, 401, 429]


def test_debit_precede_le_503(client, settings):
    """API désactivée : le plafond s'applique quand même, et passe devant."""
    settings.N8N_API_SECRET = ""
    settings.DEBIT_API_N8N_IP = (2, 60)

    codes = [
        client.get(SANTE, HTTP_X_FORWARDED_FOR=IP_TEST).status_code for _ in range(3)
    ]

    assert codes == [503, 503, 429]


def test_reponse_429_en_json(client, poser_secret, settings, caplog):
    settings.DEBIT_API_N8N_IP = (1, 60)
    client.get(SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=IP_TEST)

    with caplog.at_level(logging.WARNING, logger="n8n.securite"):
        reponse = client.get(
            SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=IP_TEST
        )

    assert reponse.status_code == 429
    assert reponse.json() == {"verdict": "too_many"}
    assert "debit depasse" in caplog.text
    # Ni l'adresse ni le secret ne doivent atterrir dans les logs.
    assert IP_TEST not in caplog.text
    assert SECRET not in caplog.text


def test_adresses_differentes_comptent_separement(client, poser_secret, settings):
    settings.DEBIT_API_N8N_IP = (1, 60)
    client.get(SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR="192.0.2.1")
    client.get(SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR="192.0.2.1")

    reponse = client.get(
        SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR="192.0.2.2"
    )

    assert reponse.status_code == 200


def test_deux_clients_derriere_le_meme_saut_comptent_separement(
    client, poser_secret, settings
):
    """Le saut interne Railway est partagé : c'est l'IP cliente qui compte."""
    settings.DEBIT_API_N8N_IP = (1, 60)
    premier = "198.51.100.1, 100.64.3.4"
    second = "198.51.100.2, 100.64.3.4"

    # Le premier client sature son propre plafond.
    client.get(SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=premier)
    sature = client.get(
        SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=premier
    )

    # Le second, derrière le même saut interne, n'est pas affecté.
    autre = client.get(
        SANTE, headers={"X-Api-Secret": SECRET}, HTTP_X_FORWARDED_FOR=second
    )

    assert sature.status_code == 429
    assert autre.status_code == 200
