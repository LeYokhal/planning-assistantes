"""Recette du déclenchement d'un import par n8n.

Les tests tournent en mode synchrone (`IMPORT_EN_ARRIERE_PLAN=0`, posé par le
conftest racine) : aucun thread n'est lancé sur la base de test.
"""

import datetime
import json
import uuid

import pytest
from django.test import Client
from django.utils import timezone

from audit.models import EvenementAudit
from presences import verrou
from presences.models import ImportPresences, VerrouImport

pytestmark = pytest.mark.django_db

SECRET = "secret-api-de-test-au-moins-32-caracteres"
IMPORTS = "/api/n8n/imports/"
SANTE = "/api/n8n/sante/"
ENTETES = {"X-Api-Secret": SECRET}


@pytest.fixture
def poser_secret(settings):
    settings.N8N_API_SECRET = SECRET


@pytest.fixture
def client_strict():
    """Client vérifiant le CSRF : l'API doit en être dispensée."""
    return Client(enforce_csrf_checks=True)


def _demander(client, corps, entetes=ENTETES):
    return client.post(
        IMPORTS,
        data=json.dumps(corps) if isinstance(corps, dict) else corps,
        content_type="application/json",
        headers=entetes,
    )


def test_declenchement_accepte(client_strict, poser_secret):
    reponse = _demander(client_strict, {"mois": "2026-10"})

    assert reponse.status_code == 202
    corps = reponse.json()
    assert corps["accepte"] is True
    assert corps["mois"] == "2026-10"
    assert corps["fenetres"] == [
        ["2026-09-28", "2026-10-28"],
        ["2026-10-29", "2026-11-01"],
    ]
    uuid.UUID(corps["lot"])  # lève si ce n'est pas un UUID


def test_lot_execute_en_synchrone_et_echoue_endpoint_inactif(
    client_strict, poser_secret
):
    """Chemin endpoint inactif en 1b : une seule ligne, en échec (fail-fast)."""
    reponse = _demander(client_strict, {"mois": "2026-10"})

    import_ = ImportPresences.objects.get()
    assert str(import_.lot) == reponse.json()["lot"]
    assert import_.source == ImportPresences.Source.ENDPOINT
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur == "endpoint inactif (brique 0 non livrée)"
    assert import_.mois == "2026-10"
    assert import_.debut == datetime.date(2026, 9, 28)


def test_audit_de_la_demande(client_strict, poser_secret):
    reponse = _demander(client_strict, {"mois": "2026-10"})

    evenement = EvenementAudit.objects.get(action="import_demande")
    assert evenement.qui is None
    assert evenement.details == {
        "mois": "2026-10",
        "lot": reponse.json()["lot"],
        "source": "endpoint",
    }


def test_verrou_libere_apres_le_lot(client_strict, poser_secret):
    _demander(client_strict, {"mois": "2026-10"})
    assert VerrouImport.objects.count() == 0


def test_import_deja_en_cours_refuse(client_strict, poser_secret):
    verrou.prendre("endpoint 2026-09", uuid.uuid4())

    reponse = _demander(client_strict, {"mois": "2026-10"})

    assert reponse.status_code == 409
    assert reponse.json() == {"accepte": False, "raison": "import_en_cours"}
    assert ImportPresences.objects.count() == 0


def test_verrou_perime_ne_bloque_pas(client_strict, poser_secret):
    verrou.prendre("endpoint 2026-09", uuid.uuid4())
    VerrouImport.objects.all().update(
        pris_le=timezone.now() - datetime.timedelta(minutes=30)
    )

    assert _demander(client_strict, {"mois": "2026-10"}).status_code == 202


@pytest.mark.parametrize("mois", ["2026-13", "202610", "", "octobre"])
def test_mois_invalide_refuse(client_strict, poser_secret, mois):
    reponse = _demander(client_strict, {"mois": mois})

    assert reponse.status_code == 400
    assert reponse.json() == {"accepte": False, "raison": "mois_invalide"}
    assert ImportPresences.objects.count() == 0


def test_mois_absent_refuse(client_strict, poser_secret):
    reponse = _demander(client_strict, {})

    assert reponse.status_code == 400
    assert reponse.json() == {"accepte": False, "raison": "mois_invalide"}


def test_corps_non_json_refuse(client_strict, poser_secret):
    reponse = _demander(client_strict, b"pas du json")

    assert reponse.status_code == 400
    assert reponse.json() == {"accepte": False, "raison": "corps_invalide"}


def test_corps_qui_n_est_pas_un_objet_refuse(client_strict, poser_secret):
    reponse = _demander(client_strict, b"[1, 2, 3]")

    assert reponse.status_code == 400
    assert reponse.json() == {"accepte": False, "raison": "corps_invalide"}


def test_sante_signale_un_import_en_cours(client, poser_secret):
    assert client.get(SANTE, headers=ENTETES).json()["import_en_cours"] is False

    verrou.prendre("endpoint 2026-10", uuid.uuid4())
    assert client.get(SANTE, headers=ENTETES).json()["import_en_cours"] is True


def test_sante_ignore_un_verrou_perime(client, poser_secret):
    verrou.prendre("endpoint 2026-10", uuid.uuid4())
    VerrouImport.objects.all().update(
        pris_le=timezone.now() - datetime.timedelta(minutes=30)
    )

    assert client.get(SANTE, headers=ENTETES).json()["import_en_cours"] is False


def test_sante_requalifie_les_lignes_interrompues(client, poser_secret):
    ligne = ImportPresences.objects.create(
        source=ImportPresences.Source.ENDPOINT,
        statut=ImportPresences.Statut.EN_COURS,
        mois="2026-10",
    )
    ImportPresences.objects.filter(pk=ligne.pk).update(
        importe_le=timezone.now() - datetime.timedelta(minutes=30)
    )

    client.get(SANTE, headers=ENTETES)

    ligne.refresh_from_db()
    assert ligne.statut == ImportPresences.Statut.ECHEC
    assert ligne.erreur == "interrompu (délai dépassé)"
