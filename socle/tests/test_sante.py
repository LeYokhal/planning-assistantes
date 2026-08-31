"""Tests de la page de santé."""

import pytest


@pytest.mark.django_db
def test_sante_repond_ok(client):
    reponse = client.get("/sante/")
    assert reponse.status_code == 200
    assert reponse.json() == {
        "statut": "ok",
        "base": "ok",
        "migrations_en_attente": 0,
    }


@pytest.mark.django_db
def test_sante_est_publique(client):
    """La page de santé ne doit jamais rediriger vers la connexion."""
    reponse = client.get("/sante/")
    assert reponse.status_code == 200


@pytest.mark.django_db
def test_accueil_anonyme_redirige_vers_connexion(client):
    reponse = client.get("/")
    assert reponse.status_code == 302
    assert reponse["Location"].startswith("/connexion/")


@pytest.mark.django_db
def test_sante_jamais_limitee_en_debit(client):
    """Railway sonde `/sante/` sans relâche : aucun plafond ne doit s'y appliquer."""
    codes = {
        client.get("/sante/", HTTP_X_FORWARDED_FOR="192.0.2.10").status_code
        for _ in range(100)
    }

    assert codes == {200}
