"""Recette du client HTTP n8n factorisé (décision J).

Le point sensible n'est pas le client lui-même mais la façon dont il coexiste
avec les bouchons des tests existants : `comptes.mails.requests` et
`presences.webhooks.requests` désignent le MÊME module que
`socle.client_n8n.requests`. Patcher l'un des trois patche les trois — c'est
voulu, c'est ce qui laisse les douze tests de brique 1a/1b intacts, et c'est
vérifié ici explicitement.
"""

import logging
from unittest.mock import Mock, patch

import pytest
import requests

from socle import client_n8n

URL = "http://n8n.example.org/webhook/quelque-chose"
SECRET = "secret-de-test"


def _poster(url=URL, secret=SECRET, corps=None):
    return client_n8n.poster(url, "X-Test-Secret", secret, corps or {"a": 1})


# --- Fail-closed ------------------------------------------------------------


def test_fail_closed_sans_url():
    with patch("socle.client_n8n.requests.post") as poste:
        resultat = _poster(url="")

    assert resultat.ok is False
    assert resultat.motif == client_n8n.MOTIF_NON_CONFIGURE
    assert poste.call_count == 0


def test_fail_closed_sans_secret():
    with patch("socle.client_n8n.requests.post") as poste:
        resultat = _poster(secret="")

    assert resultat.ok is False
    assert resultat.motif == client_n8n.MOTIF_NON_CONFIGURE
    assert poste.call_count == 0


# --- Appel ------------------------------------------------------------------


def test_entete_corps_et_delai():
    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        resultat = _poster(corps={"evenement": "essai"})

    assert resultat.ok is True
    assert resultat.statut == 200

    arguments_positionnels, arguments = poste.call_args
    # L'URL est POSITIONNELLE : la fixture `Routeur` de test_endpoint.py en
    # dépend pour aiguiller les appels d'un lot.
    assert arguments_positionnels[0] == URL
    assert arguments["headers"]["X-Test-Secret"] == SECRET
    assert arguments["headers"]["Content-Type"] == "application/json"
    assert arguments["timeout"] == 10
    assert arguments["json"] == {"evenement": "essai"}


def test_statut_en_erreur():
    with patch("socle.client_n8n.requests.post", return_value=Mock(status_code=500)):
        resultat = _poster()

    assert resultat.ok is False
    assert resultat.motif == client_n8n.MOTIF_STATUT
    assert resultat.statut == 500


def test_erreur_reseau_ne_leve_pas():
    with patch("socle.client_n8n.requests.post", side_effect=requests.Timeout("boum")):
        resultat = _poster()

    assert resultat.ok is False
    assert resultat.motif == client_n8n.MOTIF_RESEAU
    assert resultat.erreur == "Timeout"


def test_le_message_de_l_exception_ne_ressort_jamais():
    """Le message de `requests` contient l'URL : seul le type remonte."""
    with patch(
        "socle.client_n8n.requests.post",
        side_effect=requests.ConnectionError(f"impossible de joindre {URL}"),
    ):
        resultat = _poster()

    assert URL not in resultat.erreur
    assert resultat.erreur == "ConnectionError"


def test_le_client_ne_journalise_rien(caplog):
    """Chaque appelant garde son logger : le client, lui, se tait."""
    with patch("socle.client_n8n.requests.post", side_effect=requests.Timeout("boum")):
        with caplog.at_level(logging.DEBUG, logger="socle.client_n8n"):
            _poster()

    assert caplog.text == ""


def test_resultat_utilisable_en_booleen():
    with patch("socle.client_n8n.requests.post", return_value=Mock(status_code=200)):
        assert bool(_poster()) is True
    with patch("socle.client_n8n.requests.post", return_value=Mock(status_code=502)):
        assert bool(_poster()) is False


# --- Coexistence avec les bouchons existants --------------------------------


def test_les_trois_modules_partagent_le_module_requests():
    """C'est ce qui rend les douze patches de brique 1a/1b encore efficaces."""
    from comptes import mails
    from presences import webhooks

    assert mails.requests is client_n8n.requests
    assert webhooks.requests is client_n8n.requests


def test_patcher_un_appelant_intercepte_le_client_factorise():
    """Patcher `comptes.mails.requests.post` intercepte bien l'appel réel."""
    with patch(
        "comptes.mails.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        resultat = _poster()

    assert resultat.ok is True
    assert poste.call_count == 1


@pytest.mark.parametrize(
    "module, en_tete",
    [("comptes.mails", "X-Mail-Secret"), ("presences.webhooks", "X-Webhook-Secret")],
)
def test_chaque_appelant_garde_son_en_tete(module, en_tete):
    """La factorisation ne mélange pas les en-têtes des deux flux."""
    import importlib

    assert importlib.import_module(module).EN_TETE_SECRET == en_tete


def test_le_delai_est_partage():
    from comptes import mails
    from presences import webhooks

    assert mails.DELAI_SECONDES == webhooks.DELAI_SECONDES == 10
