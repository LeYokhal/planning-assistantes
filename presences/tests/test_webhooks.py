"""Recette du webhook n8n des événements d'import."""

import datetime
import logging
import uuid
from unittest.mock import Mock, patch

import pytest
import requests

from presences import webhooks
from presences.models import ImportPresences

pytestmark = pytest.mark.django_db

URL = "http://n8n.example.org/webhook/import-planning"
SECRET = "secret-de-test"


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_IMPORT_WEBHOOK_URL = URL
    settings.N8N_WEBHOOK_SECRET = SECRET
    settings.APP_URL = "http://testserver"


def _import(statut=ImportPresences.Statut.REUSSI, **extra):
    valeurs = {
        "source": ImportPresences.Source.ENDPOINT,
        "statut": statut,
        "lot": uuid.uuid4(),
        "mois": "2026-10",
        "debut": datetime.date(2026, 9, 28),
        "fin": datetime.date(2026, 10, 28),
        "invariant_ok": statut == ImportPresences.Statut.REUSSI,
        "nb_lignes": 62,
    }
    valeurs.update(extra)
    return ImportPresences.objects.create(**valeurs)


def test_fail_closed_sans_url(settings, caplog):
    settings.N8N_IMPORT_WEBHOOK_URL = ""
    settings.N8N_WEBHOOK_SECRET = SECRET

    with patch("presences.webhooks.requests.post") as poste:
        with caplog.at_level(logging.WARNING, logger="presences.webhooks"):
            assert webhooks.notifier_lot([_import()]) is False

    assert poste.call_count == 0
    assert "webhook import non configure" in caplog.text


def test_fail_closed_sans_secret(settings):
    settings.N8N_IMPORT_WEBHOOK_URL = URL
    settings.N8N_WEBHOOK_SECRET = ""

    with patch("presences.webhooks.requests.post") as poste:
        assert webhooks.notifier_lot([_import()]) is False
    assert poste.call_count == 0


def test_lot_vide_ne_notifie_rien(poser_webhook):
    with patch("presences.webhooks.requests.post") as poste:
        assert webhooks.notifier_lot([]) is False
    assert poste.call_count == 0


def test_entete_corps_et_delai(poser_webhook):
    import_ = _import()

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        assert webhooks.notifier_lot([import_]) is True

    _, arguments = poste.call_args
    assert arguments["headers"]["X-Webhook-Secret"] == SECRET
    assert arguments["headers"]["Content-Type"] == "application/json"
    assert arguments["timeout"] == 10

    corps = arguments["json"]
    assert corps["evenement"] == "import.termine"
    assert corps["lot"] == str(import_.lot)
    assert corps["mois"] == "2026-10"
    assert corps["source"] == "endpoint"
    assert corps["lien"] == "http://testserver/presences/2026-10/"
    assert corps["fenetres"] == [
        {
            "import_id": import_.pk,
            "debut": "2026-09-28",
            "fin": "2026-10-28",
            "statut": "reussi",
            "invariant_ok": True,
            "nb_lignes": 62,
            "erreur": "",
        }
    ]
    assert corps["horodatage"]


def test_une_fenetre_en_echec_bascule_l_evenement(poser_webhook):
    lot = uuid.uuid4()
    reussi = _import(lot=lot)
    echoue = _import(
        statut=ImportPresences.Statut.ECHEC,
        lot=lot,
        erreur="endpoint inactif (brique 0 non livrée)",
        invariant_ok=None,
        nb_lignes=0,
    )

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        webhooks.notifier_lot([reussi, echoue])

    assert poste.call_args[1]["json"]["evenement"] == "import.echec"


def test_lien_deduit_de_la_fenetre_pour_un_fichier(poser_webhook):
    """Un import fichier n'a pas de mois : il est déduit de sa fenêtre."""
    import_ = _import(source=ImportPresences.Source.FICHIER, mois="")

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        webhooks.notifier_lot([import_])

    corps = poste.call_args[1]["json"]
    assert corps["mois"] is None
    assert corps["lien"] == "http://testserver/presences/2026-10/"


def test_lien_de_repli_sans_fenetre_lisible(poser_webhook):
    import_ = _import(
        source=ImportPresences.Source.FICHIER,
        statut=ImportPresences.Statut.ECHEC,
        mois="",
        debut=None,
        fin=None,
    )

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        webhooks.notifier_lot([import_])

    lien = poste.call_args[1]["json"]["lien"]
    assert lien == "http://testserver/admin/presences/importpresences/"


def test_statut_en_erreur_renvoie_faux(poser_webhook, caplog):
    with patch("presences.webhooks.requests.post", return_value=Mock(status_code=500)):
        with caplog.at_level(logging.WARNING, logger="presences.webhooks"):
            assert webhooks.notifier_lot([_import()]) is False

    assert "500" in caplog.text
    assert SECRET not in caplog.text


def test_erreur_reseau_renvoie_faux(poser_webhook, caplog):
    with patch(
        "presences.webhooks.requests.post", side_effect=requests.Timeout("boum")
    ):
        with caplog.at_level(logging.WARNING, logger="presences.webhooks"):
            assert webhooks.notifier_lot([_import()]) is False

    assert "Timeout" in caplog.text
    assert URL not in caplog.text


def test_webhook_envoye_note_sur_chaque_ligne(poser_webhook):
    lot = uuid.uuid4()
    lignes = [_import(lot=lot), _import(lot=lot)]

    with patch("presences.webhooks.requests.post", return_value=Mock(status_code=200)):
        assert webhooks.notifier_lot(lignes) is True

    for ligne in lignes:
        ligne.refresh_from_db()
        assert ligne.webhook_envoye is True


def test_aucun_agenda_ni_secret_dans_les_logs(poser_webhook, caplog):
    with patch("presences.webhooks.requests.post", return_value=Mock(status_code=200)):
        with caplog.at_level(logging.DEBUG):
            webhooks.notifier_lot([_import()])

    assert SECRET not in caplog.text
    assert URL not in caplog.text
    assert "DUPONT" not in caplog.text
