"""Recette du client de mails (webhook n8n)."""

import logging
from unittest.mock import Mock, patch

import pytest

from comptes.mails import OBJET_LIEN, envoyer_mail, texte_invitation, texte_lien

DESTINATAIRE = "assistante@example.org"
LIEN = "http://testserver/connexion/lien/?sesame=jeton-de-test"


def test_fail_closed_sans_url_ni_secret(settings, caplog):
    settings.N8N_MAIL_WEBHOOK_URL = ""
    settings.N8N_WEBHOOK_SECRET = ""

    with patch("comptes.mails.requests.post") as poste:
        with caplog.at_level(logging.WARNING, logger="comptes.mails"):
            resultat = envoyer_mail(DESTINATAIRE, OBJET_LIEN, texte_lien(LIEN))

    assert resultat is False
    assert poste.call_count == 0
    assert "webhook mail non configure" in caplog.text


def test_fail_closed_sans_secret(settings):
    settings.N8N_MAIL_WEBHOOK_URL = "http://n8n.example.org/webhook/mail-sortant-planning"
    settings.N8N_WEBHOOK_SECRET = ""

    with patch("comptes.mails.requests.post") as poste:
        assert envoyer_mail(DESTINATAIRE, OBJET_LIEN, "texte") is False
    assert poste.call_count == 0


def test_entete_secret_transmise(settings):
    settings.N8N_MAIL_WEBHOOK_URL = "http://n8n.example.org/webhook/mail-sortant-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"

    with patch("comptes.mails.requests.post", return_value=Mock(status_code=200)) as poste:
        assert envoyer_mail(DESTINATAIRE, OBJET_LIEN, texte_lien(LIEN)) is True

    _, arguments = poste.call_args
    assert arguments["headers"]["X-Mail-Secret"] == "secret-de-test"
    assert arguments["headers"]["Content-Type"] == "application/json"
    assert arguments["timeout"] == 10
    assert arguments["json"] == {
        "destinataire": DESTINATAIRE,
        "objet": OBJET_LIEN,
        "texte": texte_lien(LIEN),
    }


@pytest.mark.parametrize("statut", [401, 403, 500])
def test_echec_http_ne_journalise_que_le_statut(settings, caplog, statut):
    settings.N8N_MAIL_WEBHOOK_URL = "http://n8n.example.org/webhook/mail-sortant-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"

    with patch("comptes.mails.requests.post", return_value=Mock(status_code=statut)):
        with caplog.at_level(logging.INFO, logger="comptes.mails"):
            resultat = envoyer_mail(DESTINATAIRE, OBJET_LIEN, texte_lien(LIEN))

    assert resultat is False
    assert str(statut) in caplog.text
    assert DESTINATAIRE not in caplog.text
    assert "sesame" not in caplog.text


def test_aucune_adresse_ni_lien_dans_les_logs(settings, caplog):
    """Ni l'adresse, ni le jeton, ni le secret ne doivent apparaître dans les logs."""
    settings.N8N_MAIL_WEBHOOK_URL = "http://n8n.example.org/webhook/mail-sortant-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"

    with patch("comptes.mails.requests.post", return_value=Mock(status_code=200)):
        with caplog.at_level(logging.DEBUG):
            envoyer_mail(DESTINATAIRE, OBJET_LIEN, texte_lien(LIEN))

    assert DESTINATAIRE not in caplog.text
    assert LIEN not in caplog.text
    assert "secret-de-test" not in caplog.text


def test_erreur_reseau_renvoie_faux(settings, caplog):
    import requests

    settings.N8N_MAIL_WEBHOOK_URL = "http://n8n.example.org/webhook/mail-sortant-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"

    with patch("comptes.mails.requests.post", side_effect=requests.Timeout("boum")):
        with caplog.at_level(logging.WARNING, logger="comptes.mails"):
            assert envoyer_mail(DESTINATAIRE, OBJET_LIEN, "texte") is False

    assert "Timeout" in caplog.text


def test_invitation_ne_contient_aucun_jeton(settings):
    settings.APP_URL = "http://testserver"
    texte = texte_invitation()
    assert "sesame" not in texte
    assert "http://testserver/connexion/" in texte
