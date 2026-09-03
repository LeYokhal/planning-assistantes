"""Recette de l'endpoint de paie `GET /api/n8n/paie/<AAAA-MM>/`."""

import datetime
import json
from decimal import Decimal

import pytest

from absences import services
from absences.models import AbsenceSalariee
from absences.tests import fabrique
from audit.models import EvenementAudit

pytestmark = pytest.mark.django_db

SECRET = "secret-api-de-test"
URL = "/api/n8n/paie/2026-05/"
DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)


@pytest.fixture
def api_active(settings):
    settings.N8N_API_SECRET = SECRET


def _appeler(client, url=URL, secret=SECRET):
    entetes = {"HTTP_X_API_SECRET": secret} if secret is not None else {}
    return client.get(url, **entetes)


def _absence_validee(principale, nom="DUPONT", prenom="Alice", **extra):
    personne = fabrique.personne(nom=nom, prenom=prenom, **extra)
    absence = fabrique.absence(personne, fabrique.type_absence(paie=True), DEBUT, FIN)
    services.decider(absence, True, principale)
    return absence


# --- Contrôles négatifs (patron `secret_n8n_requis`) ------------------------


def test_sans_secret_401(client, api_active):
    reponse = _appeler(client, secret=None)
    assert reponse.status_code == 401
    assert reponse.json() == {"verdict": "unauthorized"}


def test_secret_bidon_401(client, api_active):
    reponse = _appeler(client, secret="pas-le-bon")
    assert reponse.status_code == 401
    assert reponse.json() == {"verdict": "unauthorized"}


def test_api_desactivee_503(client, settings):
    settings.N8N_API_SECRET = ""
    reponse = _appeler(client)
    assert reponse.status_code == 503
    assert reponse.json() == {"verdict": "disabled"}


def test_mauvaise_methode_405(client, api_active):
    reponse = client.post(URL, **{"HTTP_X_API_SECRET": SECRET})
    assert reponse.status_code == 405
    assert reponse.json() == {"erreur": "methode_non_autorisee"}


def test_le_secret_passe_avant_la_methode(client, api_active):
    """Un POST sans secret reçoit 401, jamais 405 : rien n'apprend la route."""
    reponse = client.post(URL)
    assert reponse.status_code == 401


def test_debit_depasse_429(client, api_active, settings):
    settings.DEBIT_API_N8N_IP = (2, 60)
    _appeler(client)
    _appeler(client)
    reponse = _appeler(client)
    assert reponse.status_code == 429
    assert reponse.json() == {"verdict": "too_many"}


def test_mois_invalide_400(client, api_active):
    """« 2026-13 » passe le motif `\\d{4}-\\d{2}` mais pas `plage_mois`."""
    reponse = _appeler(client, url="/api/n8n/paie/2026-13/")
    assert reponse.status_code == 400
    assert reponse.json() == {"erreur": "mois_invalide"}


def test_mois_hors_motif_404(client, api_active):
    assert _appeler(client, url="/api/n8n/paie/202605/").status_code == 404


def test_slash_final_obligatoire(client, api_active):
    """Patron de `presences/urls.py` : la route porte un slash final."""
    assert _appeler(client, url="/api/n8n/paie/2026-05").status_code != 200


# --- Contenu ----------------------------------------------------------------


def test_mois_vide_rend_une_liste_vide(client, api_active):
    corps = _appeler(client).json()
    assert corps["mois"] == "2026-05"
    assert corps["salariees"] == []
    assert "aucune absence" in corps["paragraphe"]


def test_une_absence_validee_apparait(client, api_active, principale):
    absence = _absence_validee(principale)

    corps = _appeler(client).json()

    assert len(corps["salariees"]) == 1
    entree = corps["salariees"][0]
    assert entree["nom"] == "DUPONT Alice"
    assert entree["jours_comptes"] == "4.0"
    assert entree["absences"][0]["absence_id"] == absence.pk


def test_une_salariee_sans_absence_est_absente_du_resultat(client, api_active, principale):
    _absence_validee(principale)
    fabrique.personne(nom="MARTIN", prenom="Bob")

    corps = _appeler(client).json()

    assert [e["nom"] for e in corps["salariees"]] == ["DUPONT Alice"]


def test_une_demande_en_attente_n_apparait_pas(client, api_active):
    fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    corps = _appeler(client).json()
    assert corps["salariees"] == []


def test_une_absence_refusee_n_apparait_pas(client, api_active, principale):
    absence = fabrique.absence(
        fabrique.personne(), fabrique.type_absence(), DEBUT, FIN
    )
    services.decider(absence, False, principale)

    assert _appeler(client).json()["salariees"] == []


def test_un_type_hors_paie_n_apparait_pas(client, api_active, principale):
    personne = fabrique.personne()
    absence = fabrique.absence(
        personne, fabrique.type_absence(libelle="Retard", paie=False), DEBUT, FIN
    )
    services.decider(absence, True, principale)

    assert _appeler(client).json()["salariees"] == []


def test_deux_absences_de_la_meme_salariee_sont_cumulees(client, api_active, principale):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(paie=True)
    for debut, fin in (
        (datetime.date(2026, 5, 5), datetime.date(2026, 5, 6)),
        (datetime.date(2026, 5, 26), datetime.date(2026, 5, 27)),
    ):
        absence = fabrique.absence(personne, type_, debut, fin)
        services.decider(absence, True, principale)

    entree = _appeler(client).json()["salariees"][0]
    assert entree["jours_comptes"] == "4.0"
    assert len(entree["absences"]) == 2


def test_la_correction_manuelle_est_celle_qui_sort(client, api_active, principale):
    absence = _absence_validee(principale)
    services.corriger(absence, Decimal("0.5"), principale)

    entree = _appeler(client).json()["salariees"][0]
    assert entree["jours_comptes"] == "0.5"
    assert entree["absences"][0]["corrigee"] is True


def test_paragraphe_mis_en_forme_cote_serveur(client, api_active, principale):
    _absence_validee(principale)
    paragraphe = _appeler(client).json()["paragraphe"]
    assert paragraphe.startswith("Paie 2026-05 — absences à décompter :")
    assert "DUPONT Alice : 4 jour(s)" in paragraphe


def test_paragraphe_avec_demi_journee(client, api_active, principale):
    absence = _absence_validee(principale)
    services.corriger(absence, Decimal("2.5"), principale)

    assert "2,5 jour(s)" in _appeler(client).json()["paragraphe"]


def test_salariees_triees_par_nom(client, api_active, principale):
    _absence_validee(principale, nom="ZOLA", prenom="Emile")
    _absence_validee(principale, nom="ABEL", prenom="Bob")

    noms = [e["nom"] for e in _appeler(client).json()["salariees"]]
    assert noms == ["ABEL Bob", "ZOLA Emile"]


# --- Audit ------------------------------------------------------------------


def test_consultation_journalisee_sans_contenu(client, api_active, principale):
    _absence_validee(principale)

    _appeler(client)

    evenement = EvenementAudit.objects.get(action="paie_consultee")
    assert evenement.details["mois"] == "2026-05"
    assert evenement.details["nb_salariees"] == 1
    assert "DUPONT" not in str(evenement.details)


def test_un_refus_n_ecrit_rien_au_journal(client, api_active):
    _appeler(client, secret="pas-le-bon")
    assert not EvenementAudit.objects.filter(action="paie_consultee").exists()
