"""Le type d'absence et la précision ne sortent jamais de la base.

C'est la contrainte structurante de la brique 3 (§ 3 du plan) : « Maladie » est
une donnée de santé, et une précision libre — « rendez-vous médical » — peut en
être une aussi. Le garde-fou « @ » d'`audit/services.py` ne les reconnaîtrait
pas : ces tests sont le seul filet.

Trois sorties possibles, toutes couvertes ici : le journal d'audit, les logs
applicatifs, et le corps des webhooks.
"""

import datetime
import logging
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from absences import services
from absences.models import TypeAbsence
from absences.tests import fabrique
from audit.models import EvenementAudit

pytestmark = pytest.mark.django_db

TYPE_SENSIBLE = "Maladie"
PRECISION_SENSIBLE = "rendez-vous médical au CHU"
DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)


@pytest.fixture
def webhook_actif(settings):
    settings.N8N_ABSENCE_WEBHOOK_URL = "http://n8n.example.org/webhook/absence"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"
    settings.APP_URL = "http://testserver"


def _journal():
    """Tout le journal d'audit, rendu en une seule chaîne."""
    return " ".join(
        f"{evenement.action} {evenement.details} {evenement.type_objet} {evenement.id_objet}"
        for evenement in EvenementAudit.objects.all()
    )


def _absence_sensible(**extra):
    return fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(
            libelle=TYPE_SENSIBLE, categorie=TypeAbsence.Categorie.DECLARE
        ),
        DEBUT,
        FIN,
        precision=PRECISION_SENSIBLE,
        **extra,
    )


# --- Journal d'audit --------------------------------------------------------


def test_creation_ne_journalise_ni_type_ni_precision(salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(
        libelle=TYPE_SENSIBLE, categorie=TypeAbsence.Categorie.DECLARE
    )

    services.creer(personne, type_, DEBUT, FIN, salariee, precision=PRECISION_SENSIBLE)

    journal = _journal()
    assert TYPE_SENSIBLE not in journal
    assert "médical" not in journal
    assert "CHU" not in journal


def test_decision_ne_journalise_ni_type_ni_precision(principale):
    absence = _absence_sensible(statut="en_attente")

    services.decider(absence, True, principale)

    journal = _journal()
    assert TYPE_SENSIBLE not in journal
    assert "médical" not in journal


def test_annulation_ne_journalise_ni_type_ni_precision(salariee):
    absence = _absence_sensible(statut="en_attente")

    services.annuler(absence, salariee)

    journal = _journal()
    assert TYPE_SENSIBLE not in journal
    assert "médical" not in journal


def test_correction_ne_journalise_ni_type_ni_precision(principale):
    absence = _absence_sensible(statut="validee")

    services.corriger(absence, Decimal("1"), principale)

    journal = _journal()
    assert TYPE_SENSIBLE not in journal
    assert "médical" not in journal


def test_le_journal_ne_porte_aucun_nom_de_personne(salariee):
    """L'identité passe par `personne_id`, jamais par un nom."""
    personne = fabrique.personne(nom="DUPONT", prenom="Alice")
    type_ = fabrique.type_absence()

    services.creer(personne, type_, DEBUT, FIN, salariee, precision=PRECISION_SENSIBLE)

    journal = _journal()
    assert "DUPONT" not in journal
    assert "Alice" not in journal


# --- Logs applicatifs -------------------------------------------------------


def test_les_logs_ne_portent_ni_type_ni_precision(salariee, caplog):
    personne = fabrique.personne(nom="DUPONT", prenom="Alice")
    type_ = fabrique.type_absence(
        libelle=TYPE_SENSIBLE, categorie=TypeAbsence.Categorie.DECLARE
    )

    with caplog.at_level(logging.DEBUG):
        services.creer(
            personne, type_, DEBUT, FIN, salariee, precision=PRECISION_SENSIBLE
        )

    assert TYPE_SENSIBLE not in caplog.text
    assert "médical" not in caplog.text
    assert "DUPONT" not in caplog.text


def test_les_logs_de_decision_restent_muets(principale, caplog):
    absence = _absence_sensible(statut="en_attente")

    with caplog.at_level(logging.DEBUG):
        services.decider(absence, True, principale)

    assert TYPE_SENSIBLE not in caplog.text
    assert "médical" not in caplog.text


# --- Webhooks ---------------------------------------------------------------


def test_le_webhook_ne_porte_ni_type_ni_precision(webhook_actif, salariee):
    personne = fabrique.personne(nom="DUPONT", prenom="Alice")
    type_ = fabrique.type_absence(
        libelle=TYPE_SENSIBLE, categorie=TypeAbsence.Categorie.DECLARE
    )

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services.creer(
            personne, type_, DEBUT, FIN, salariee, precision=PRECISION_SENSIBLE
        )

    corps = str(poste.call_args[1]["json"])
    assert TYPE_SENSIBLE not in corps
    assert "médical" not in corps
    assert "DUPONT" not in corps
    assert "Alice" not in corps


def test_le_webhook_de_decision_reste_muet(webhook_actif, principale):
    absence = _absence_sensible(statut="en_attente")

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services.decider(absence, True, principale)

    corps = str(poste.call_args[1]["json"])
    assert TYPE_SENSIBLE not in corps
    assert "médical" not in corps


# --- Endpoint de paie -------------------------------------------------------


def test_la_paie_ne_porte_ni_type_ni_precision(principale):
    """La comptable reçoit un nombre de jours, pas un motif médical."""
    from absences import paie

    absence = _absence_sensible(statut="en_attente")
    services.decider(absence, True, principale)

    donnees = str(paie.donnees_du_mois("2026-05", paie.plage_calendaire("2026-05")))
    assert TYPE_SENSIBLE not in donnees
    assert "médical" not in donnees
