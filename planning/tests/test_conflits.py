"""Recette du conflit absence ↔ planning publié (brique 4b).

Décisions C (à l'entrée en état effectif, quel que soit le chemin, jamais
bloquant), I (tout slot, `x` compris, types bloquants seulement), J (rien de
stocké), L (webhook `absence.conflit` sur l'URL des absences), B4 (admin : sur
la transition seulement). Ni type, ni précision, ni nom dans l'audit ni dans le
webhook.
"""

import datetime
import json
from unittest.mock import Mock, patch

import pytest

from absences import services as services_absences
from absences.tests import fabrique as fabrique_absences
from audit.models import EvenementAudit
from planning import services
from planning.conflits import conflits, conflits_dans_state, mois_candidats
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

D = datetime.date
URL_WEBHOOK = "http://n8n.example.org/webhook/absence"
SECRET = "secret-de-test"


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_ABSENCE_WEBHOOK_URL = URL_WEBHOOK
    settings.N8N_WEBHOOK_SECRET = SECRET
    settings.APP_URL = "http://testserver"


def _publiee(cabinet, state=None):
    version = services.enregistrer(fabrique.MOIS, 0, state or fabrique.etat_propre(), cabinet)
    return services.publier(fabrique.MOIS, version.numero, cabinet)


def _journal_conflits():
    return list(EvenementAudit.objects.filter(action="absence_conflit_publication"))


def _evenements(poste):
    return [appel[1]["json"]["evenement"] for appel in poste.call_args_list]


# --- Fonctions pures ------------------------------------------------------------


def test_conflits_dans_state_tout_slot_hors_quota_compris():
    state = fabrique.etat({
        "2026-09-29": {"alice_dup": [fabrique.brique("emma_ber")], "secretariat": [fabrique.brique("sara_pet")]},
        "2026-09-30": {"sureffectif": [fabrique.brique("emma_ber", "C", x=True)]},
        "2026-10-01": {"bob_mar": [fabrique.brique("lina_rou")]},
        "2026-10-02": "illisible",
    })
    dates = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03"]
    assert conflits_dans_state(state, "emma_ber", dates) == ["2026-09-29", "2026-09-30"]
    assert conflits_dans_state(state, "sara_pet", dates) == ["2026-09-29"]
    assert conflits_dans_state(state, "zoe_gir", dates) == []
    assert conflits_dans_state({}, "emma_ber", dates) == []
    assert conflits_dans_state(None, "emma_ber", dates) == []


def test_mois_candidats():
    assert mois_candidats(D(2026, 10, 13), D(2026, 10, 15)) == ["2026-10"]
    # Le 29 septembre est dans la plage de septembre ET dans celle d'octobre.
    assert mois_candidats(D(2026, 9, 29), D(2026, 9, 29)) == ["2026-09", "2026-10"]
    # Absence à cheval sur deux mois.
    assert mois_candidats(D(2026, 10, 30), D(2026, 11, 3)) == ["2026-10", "2026-11"]
    assert mois_candidats(D(2026, 12, 15), D(2027, 1, 5)) == ["2026-12", "2027-01"]


def test_conflits_avec_version_publiee(cabinet, jeu):
    emma = jeu["personnes"]["Emma"]
    assert conflits(emma, D(2026, 9, 29), D(2026, 9, 29)) == []   # rien de publié

    _publiee(cabinet)
    assert conflits(emma, D(2026, 9, 29), D(2026, 9, 30)) == [
        {"mois": fabrique.MOIS, "numero": 1, "dates": ["2026-09-29"]}
    ]
    assert conflits(emma, D(2026, 10, 6), D(2026, 10, 6)) == []
    assert conflits(jeu["personnes"]["Lina"], D(2026, 9, 29), D(2026, 9, 29)) == []

    cache = {}
    conflits(emma, D(2026, 9, 29), D(2026, 9, 29), cache)
    assert set(cache) == {"2026-09", "2026-10"}
    assert cache["2026-09"] is None and cache["2026-10"].numero == 1


# --- Crochet : déclaration, décision, admin ----------------------------------------


def test_declaration_bloquante_signalee(poser_webhook, cabinet, jeu):
    _publiee(cabinet)
    emma = jeu["personnes"]["Emma"]
    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        absence, _ = services_absences.creer(
            emma, fabrique.type_absence("Maladie"), D(2026, 9, 29), D(2026, 9, 30), cabinet,
            precision="rendez-vous médical",
        )

    assert absence.statut == "declaree"
    evenements = _journal_conflits()
    assert len(evenements) == 1
    assert evenements[0].qui == cabinet and evenements[0].id_objet == str(absence.pk)
    assert evenements[0].details == {
        "personne_id": emma.pk, "mois": fabrique.MOIS, "numero": 1, "dates": ["2026-09-29"],
    }
    assert _evenements(poste) == ["absence.declaree", "absence.conflit"]
    conflit = poste.call_args_list[1][1]["json"]
    assert conflit["conflits"] == [{"mois": fabrique.MOIS, "numero": 1, "dates": ["2026-09-29"]}]
    assert conflit["absence_id"] == absence.pk and conflit["lien"] == "http://testserver/absences/"
    texte = str(evenements[0].details) + json.dumps(conflit, ensure_ascii=False)
    for mot in ("Maladie", "médical", "alice_dup", "Emma", "BERNARD"):
        assert mot not in texte, mot


def test_validation_signalee_refus_non(poser_webhook, cabinet, principale, jeu):
    _publiee(cabinet)
    emma = jeu["personnes"]["Emma"]
    conge = fabrique.type_absence("Congé payé")
    demande = fabrique_absences.absence(emma, conge, D(2026, 9, 29), D(2026, 9, 29))
    refusee = fabrique_absences.absence(emma, conge, D(2026, 9, 29), D(2026, 9, 29))

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services_absences.decider(refusee, False, principale)
        assert _journal_conflits() == []
        services_absences.decider(demande, True, principale)

    assert len(_journal_conflits()) == 1
    assert _evenements(poste) == ["absence.decidee", "absence.decidee", "absence.conflit"]


def test_type_non_bloquant_annulation_correction_sans_signal(cabinet, salariee, jeu):
    _publiee(cabinet)
    emma = jeu["personnes"]["Emma"]
    retard, _ = services_absences.creer(
        emma, fabrique.type_absence("Retard"), D(2026, 9, 29), D(2026, 9, 29), cabinet
    )
    assert retard.effective and _journal_conflits() == []

    demande = fabrique_absences.absence(
        emma, fabrique.type_absence("Congé payé"), D(2026, 9, 29), D(2026, 9, 29)
    )
    services_absences.annuler(demande, salariee)
    services_absences.corriger(retard, 1, cabinet)
    assert _journal_conflits() == []


def test_hors_du_planning_publie_rien(poser_webhook, cabinet, jeu):
    _publiee(cabinet)
    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        services_absences.creer(
            jeu["personnes"]["Emma"], fabrique.type_absence("Maladie"), D(2026, 10, 6), D(2026, 10, 6), cabinet
        )
    assert _journal_conflits() == []
    assert _evenements(poste) == ["absence.declaree"]


def test_admin_transition_signalee_edition_non(client, cabinet, connecter, poser_webhook, jeu):
    _publiee(cabinet)
    emma = jeu["personnes"]["Emma"]
    conge = fabrique.type_absence("Congé payé")
    absence = fabrique_absences.absence(emma, conge, D(2026, 9, 29), D(2026, 9, 29))   # en attente
    connecter(client, cabinet)
    url = f"/admin/absences/absencesalariee/{absence.pk}/change/"
    formulaire = {
        "personne": emma.pk, "type": conge.pk,
        "date_debut": "2026-09-29", "date_fin": "2026-09-29",
        "precision": "", "jours_comptes": "", "a_effacer_le": "",
    }

    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        reponse = client.post(url, {**formulaire, "statut": "validee"})
        assert reponse.status_code == 302
        assert len(_journal_conflits()) == 1
        assert _evenements(poste) == ["absence.conflit"]

        # Modifier la précision d'une absence déjà effective : aucun nouveau signal.
        reponse = client.post(url, {**formulaire, "statut": "validee", "precision": "note"})
        assert reponse.status_code == 302

    assert len(_journal_conflits()) == 1
    assert poste.call_count == 1
