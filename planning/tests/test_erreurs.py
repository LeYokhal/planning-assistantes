"""Recette de `/api/erreurs/` : journalisé, plafonné, sans message."""

import json
import logging

import pytest

pytestmark = pytest.mark.django_db

URL = "/api/erreurs/"
IP = "192.0.2.10"


def poster(client, corps, **extra):
    return client.post(URL, data=json.dumps(corps), content_type="application/json", REMOTE_ADDR=IP, **extra)


def test_erreur_journalisee_sans_message(client, cabinet, connecter, caplog):
    connecter(client, cabinet)
    with caplog.at_level(logging.ERROR, logger="planning.views"):
        reponse = poster(client, {"nom": "TypeError", "source": "page.js", "ligne": 42, "mois": "2026-10", "message": "SECRET_MESSAGE avec un nom dedans"})

    assert reponse.status_code == 202
    assert reponse.json() == {"recu": True}
    texte = " ".join(r.getMessage() for r in caplog.records)
    assert "TypeError" in texte and "page.js" in texte and "42" in texte and "2026-10" in texte
    assert "SECRET_MESSAGE" not in texte


def test_champs_tronques(client, cabinet, connecter, caplog):
    connecter(client, cabinet)
    with caplog.at_level(logging.ERROR, logger="planning.views"):
        poster(client, {"nom": "x" * 500})
    assert "x" * 80 in caplog.text and "x" * 81 not in caplog.text


def test_corps_illisible_tolere(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.post(URL, data="pas du json", content_type="application/json", REMOTE_ADDR=IP).status_code == 202


def test_get_refuse(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.get(URL).status_code == 405


def test_salariee_refusee(client, salariee, connecter):
    connecter(client, salariee)
    assert poster(client, {"nom": "x"}).status_code == 403


def test_plafond_par_ip(client, cabinet, connecter, settings):
    settings.DEBIT_ERREURS_IP = (2, 60)
    connecter(client, cabinet)
    codes = [poster(client, {"nom": "x"}).status_code for _ in range(3)]
    assert codes == [202, 202, 429]
    assert poster(client, {"nom": "x"}).json() == {"erreur": "trop_de_demandes"}


def test_le_plafond_precede_le_role(client, settings):
    """Anonyme : le premier POST est redirigé par le rôle, le second coupé par le plafond."""
    settings.DEBIT_ERREURS_IP = (1, 60)
    assert poster(client, {"nom": "x"}).status_code == 302
    assert poster(client, {"nom": "x"}).status_code == 429
