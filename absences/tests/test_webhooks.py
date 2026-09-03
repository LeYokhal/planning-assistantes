"""Recette des webhooks d'absence.

Trois événements, et **aucun type d'absence ni précision** dans le corps.
"""

import datetime
import logging
from unittest.mock import Mock, patch

import pytest
import requests

from absences import services, webhooks
from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique

pytestmark = pytest.mark.django_db

URL = "http://n8n.example.org/webhook/absence-planning"
SECRET = "secret-de-test"


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_ABSENCE_WEBHOOK_URL = URL
    settings.N8N_WEBHOOK_SECRET = SECRET
    settings.APP_URL = "http://testserver"


def _absence():
    return fabrique.absence(fabrique.personne(), fabrique.type_absence())


def test_fail_closed_sans_url(settings, caplog):
    settings.N8N_ABSENCE_WEBHOOK_URL = ""
    settings.N8N_WEBHOOK_SECRET = SECRET

    with patch("socle.client_n8n.requests.post") as poste:
        with caplog.at_level(logging.WARNING, logger="absences.webhooks"):
            assert webhooks.notifier(webhooks.EVENEMENT_DEMANDEE, _absence()) is False

    assert poste.call_count == 0
    assert "webhook absence non configure" in caplog.text


def test_fail_closed_sans_secret(settings):
    settings.N8N_ABSENCE_WEBHOOK_URL = URL
    settings.N8N_WEBHOOK_SECRET = ""

    with patch("socle.client_n8n.requests.post") as poste:
        assert webhooks.notifier(webhooks.EVENEMENT_DEMANDEE, _absence()) is False
    assert poste.call_count == 0


def test_entete_corps_et_delai(poser_webhook):
    absence = _absence()

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        assert webhooks.notifier(webhooks.EVENEMENT_DEMANDEE, absence) is True

    _, arguments = poste.call_args
    assert arguments["headers"]["X-Webhook-Secret"] == SECRET
    assert arguments["headers"]["Content-Type"] == "application/json"
    assert arguments["timeout"] == 10

    corps = arguments["json"]
    assert corps["evenement"] == "absence.demandee"
    assert corps["absence_id"] == absence.pk
    assert corps["personne_id"] == absence.personne_id
    assert corps["debut"] == "2026-05-26"
    assert corps["fin"] == "2026-05-30"
    assert corps["statut"] == "en_attente"
    assert corps["lien"] == "http://testserver/absences/"
    assert corps["horodatage"]


def test_demande_emet_absence_demandee(poser_webhook, salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DEMANDE)

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services.creer(
            personne, type_, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), salariee
        )

    assert poste.call_args[1]["json"]["evenement"] == "absence.demandee"


def test_declaration_emet_absence_declaree(poser_webhook, salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(
        libelle="Maladie", categorie=TypeAbsence.Categorie.DECLARE
    )

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services.creer(
            personne, type_, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), salariee
        )

    assert poste.call_args[1]["json"]["evenement"] == "absence.declaree"


def test_decision_emet_absence_decidee(poser_webhook, principale):
    absence = _absence()

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services.decider(absence, True, principale)

    corps = poste.call_args[1]["json"]
    assert corps["evenement"] == "absence.decidee"
    assert corps["statut"] == "validee"


def test_annulation_n_emet_aucun_webhook(poser_webhook, salariee):
    """L'annulation est auditée, mais elle ne demande d'action à personne."""
    absence = _absence()

    with patch("socle.client_n8n.requests.post") as poste:
        services.annuler(absence, salariee)

    assert poste.call_count == 0


def test_statut_en_erreur_renvoie_faux(poser_webhook, caplog):
    with patch("socle.client_n8n.requests.post", return_value=Mock(status_code=500)):
        with caplog.at_level(logging.WARNING, logger="absences.webhooks"):
            assert webhooks.notifier(webhooks.EVENEMENT_DEMANDEE, _absence()) is False

    assert "500" in caplog.text
    assert SECRET not in caplog.text


def test_erreur_reseau_renvoie_faux(poser_webhook, caplog):
    with patch(
        "socle.client_n8n.requests.post", side_effect=requests.Timeout("boum")
    ):
        with caplog.at_level(logging.WARNING, logger="absences.webhooks"):
            assert webhooks.notifier(webhooks.EVENEMENT_DEMANDEE, _absence()) is False

    assert "Timeout" in caplog.text
    assert URL not in caplog.text


def test_un_webhook_muet_n_empeche_pas_la_saisie(poser_webhook, salariee):
    """Une salariée doit pouvoir poser son absence même si n8n est à terre."""
    personne = fabrique.personne()
    type_ = fabrique.type_absence()

    with patch(
        "socle.client_n8n.requests.post", side_effect=requests.Timeout("boum")
    ):
        absence, _ = services.creer(
            personne, type_, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), salariee
        )

    assert AbsenceSalariee.objects.filter(pk=absence.pk).exists()
