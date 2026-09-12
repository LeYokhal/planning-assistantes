"""Recette de la publication d'une version (brique 4b).

Décisions A (dernière version, numéro explicite, 409 sinon), B (revérification
sur `DATA` recalculé, 422 et rien d'écrit), G (republier = 200 `deja_publiee`,
aucune écriture), H (`verifications`), K (webhook `planning.publie`, muet sans
URL). Jeu fictif de `fabrique`, webhook bouchonné : aucun réseau.
"""

import datetime
import json
import logging
from unittest.mock import Mock, patch

import pytest

from absences.models import AbsenceSalariee
from absences.tests import fabrique as fabrique_absences
from audit.models import EvenementAudit
from planning import services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL_WEBHOOK = "http://n8n.example.org/webhook/planning"
SECRET = "secret-de-test"
NOMS = ("BERNARD", "Emma", "PETIT", "Sara", "DUPONT", "Alice")


def url_publier(numero, mois=fabrique.MOIS):
    return f"/api/planning/{mois}/versions/{numero}/publier/"


def publier(client, numero):
    return client.post(url_publier(numero))


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_PLANNING_WEBHOOK_URL = URL_WEBHOOK
    settings.N8N_WEBHOOK_SECRET = SECRET
    settings.APP_URL = "http://testserver"


def _version(cabinet, base=0, state=None):
    return services.enregistrer(fabrique.MOIS, base, state or fabrique.etat_propre(), cabinet)


# --- Accès et forme ---------------------------------------------------------


def test_anonyme_redirige(client, jeu):
    reponse = publier(client, 1)
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_salariee_refusee(client, salariee, connecter, jeu):
    connecter(client, salariee)
    assert publier(client, 1).status_code == 403


def test_get_refuse(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = client.get(url_publier(1))
    assert reponse.status_code == 405
    assert reponse.json() == {"erreur": "methode_non_autorisee"}


def test_mois_invalide(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    assert client.post("/api/planning/2026-13/versions/1/publier/").status_code == 400


def test_numero_zero_refuse(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = publier(client, 0)
    assert reponse.status_code == 400
    assert reponse.json() == {"erreur": "numero_invalide"}


# --- Publication --------------------------------------------------------------


def test_publie_la_derniere_version(client, cabinet, connecter, jeu, caplog):
    _version(cabinet)
    connecter(client, cabinet)
    with caplog.at_level(logging.INFO, logger="planning.services"):
        reponse = publier(client, 1)

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["numero"] == 1 and corps["publie_le"] and "deja_publiee" not in corps

    version = PlanningVersion.objects.get()
    assert version.publiee is True
    assert version.publie_par == cabinet and version.publie_le is not None
    assert set(version.verifications) == {"verifie_le", "imports", "nb_briques", "effectif"}
    assert version.verifications["nb_briques"] == 2
    imports = version.verifications["imports"]
    assert {x["id"] for x in imports} == {i.pk for i in jeu["imports"]}
    assert all(len(x["empreinte"]) == 64 for x in imports)
    # Brique 6b (C6.9) : le compte-rendu d'effectif, jour par jour, horodaté comme la vérification.
    compte_rendu = version.verifications["effectif"]
    assert compte_rendu["jours"]
    assert compte_rendu["calcule_le"] == version.verifications["verifie_le"]

    evenement = EvenementAudit.objects.get(action="planning_publie")
    assert evenement.qui == cabinet and evenement.id_objet == str(version.pk)
    assert evenement.details == {"mois": fabrique.MOIS, "numero": 1, "nb_briques": 2}
    texte = json.dumps(version.verifications) + caplog.text + str(evenement.details)
    for nom in NOMS:
        assert nom not in texte, nom


def test_principale_publie_aussi(client, principale, cabinet, connecter, jeu):
    _version(cabinet)
    connecter(client, principale)
    assert publier(client, 1).status_code == 200
    assert PlanningVersion.objects.get().publie_par == principale


def test_meta_de_la_page_porte_la_publiee_et_l_url(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    meta = client.get(f"/planning/{fabrique.MOIS}/").context["meta"]
    assert meta["publiee"] == 0 and "publier" not in meta["urls"]

    _version(cabinet)
    meta = client.get(f"/planning/{fabrique.MOIS}/").context["meta"]
    assert meta["publiee"] == 0 and meta["urls"]["publier"] == url_publier(1)

    publier(client, 1)
    meta = client.get(f"/planning/{fabrique.MOIS}/").context["meta"]
    assert meta["publiee"] == 1 and meta["numero"] == 1


def test_numero_perime_409(client, cabinet, connecter, jeu):
    _version(cabinet)
    _version(cabinet, base=1)
    connecter(client, cabinet)
    reponse = publier(client, 1)
    assert reponse.status_code == 409
    assert reponse.json() == {"derniere": 2}
    assert not PlanningVersion.objects.filter(publiee=True).exists()


def test_mois_sans_version_409(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = publier(client, 1)
    assert reponse.status_code == 409
    assert reponse.json() == {"derniere": 0}


def test_deja_publiee_200_sans_second_audit(client, cabinet, connecter, jeu):
    _version(cabinet)
    connecter(client, cabinet)
    assert publier(client, 1).status_code == 200
    premiere = PlanningVersion.objects.get()

    reponse = publier(client, 1)

    assert reponse.status_code == 200
    assert reponse.json() == {"numero": 1, "deja_publiee": True}
    assert EvenementAudit.objects.filter(action="planning_publie").count() == 1
    seconde = PlanningVersion.objects.get()
    assert seconde.publie_le == premiere.publie_le
    assert seconde.verifications == premiere.verifications


def test_violation_a_la_publication_422_et_rien_d_ecrit(client, cabinet, connecter, jeu):
    """Une absence devenue effective APRÈS l'enregistrement : la revérification la voit."""
    _version(cabinet)
    fabrique_absences.absence(
        jeu["personnes"]["Emma"],
        fabrique.type_absence("Congé payé"),
        datetime.date(2026, 9, 29),
        datetime.date(2026, 9, 29),
        statut=AbsenceSalariee.Statut.VALIDEE,
    )
    connecter(client, cabinet)
    reponse = publier(client, 1)

    assert reponse.status_code == 422
    violations = reponse.json()["violations"]
    assert [v["code"] for v in violations] == ["jour_bloque"]
    assert all(set(v) == {"code", "date", "slot", "s"} for v in violations)
    version = PlanningVersion.objects.get()
    assert version.publiee is False and version.publie_le is None and version.publie_par is None
    assert version.verifications == []
    assert not EvenementAudit.objects.filter(action="planning_publie").exists()


def test_version_publiee_est_la_derniere_par_numero(cabinet, jeu):
    _version(cabinet)
    services.publier(fabrique.MOIS, 1, cabinet)
    _version(cabinet, base=1)
    assert services.version_publiee(fabrique.MOIS).numero == 1   # v2 enregistrée, pas encore publiée
    services.publier(fabrique.MOIS, 2, cabinet)
    assert services.version_publiee(fabrique.MOIS).numero == 2
    assert list(PlanningVersion.objects.filter(publiee=True).values_list("numero", flat=True)) == [2, 1]


def test_service_publier_direct(cabinet, jeu):
    with pytest.raises(services.Conflit) as conflit:
        services.publier(fabrique.MOIS, 1, cabinet)
    assert conflit.value.derniere == 0

    _version(cabinet)
    version = services.publier(fabrique.MOIS, 1, cabinet)
    assert version.publiee is True and version.numero == 1

    with pytest.raises(services.DejaPubliee) as deja:
        services.publier(fabrique.MOIS, 1, cabinet)
    assert deja.value.numero == 1


# --- Webhook ------------------------------------------------------------------


def test_webhook_muet_sans_url(cabinet, jeu, caplog):
    _version(cabinet)
    with caplog.at_level(logging.WARNING, logger="planning.webhooks"), patch(
        "socle.client_n8n.requests.post"
    ) as poste:
        version = services.publier(fabrique.MOIS, 1, cabinet)
    poste.assert_not_called()
    assert version.publiee is True
    assert "webhook planning non configure" in caplog.text


def test_webhook_planning_publie(poser_webhook, cabinet, jeu):
    _version(cabinet)
    with patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        version = services.publier(fabrique.MOIS, 1, cabinet)

    args, kwargs = poste.call_args
    assert args[0] == URL_WEBHOOK
    assert kwargs["headers"]["X-Webhook-Secret"] == SECRET
    assert kwargs["timeout"] == 10
    corps = kwargs["json"]
    assert set(corps) == {
        "evenement", "mois", "numero", "nb_briques", "publie_par_id", "lien", "horodatage",
    }
    assert corps["evenement"] == "planning.publie"
    assert corps["mois"] == fabrique.MOIS and corps["numero"] == 1
    assert corps["nb_briques"] == 2 and corps["publie_par_id"] == cabinet.pk
    assert corps["lien"] == f"http://testserver/planning/{fabrique.MOIS}/"
    texte = json.dumps(corps, ensure_ascii=False)
    for mot in NOMS + ("Maladie", "Congé", "affectations"):
        assert mot not in texte, mot
    assert version.publiee is True


def test_webhook_en_echec_n_empeche_pas_la_publication(poser_webhook, cabinet, jeu, caplog):
    _version(cabinet)
    with caplog.at_level(logging.WARNING, logger="planning.webhooks"), patch(
        "socle.client_n8n.requests.post", return_value=Mock(status_code=500)
    ):
        version = services.publier(fabrique.MOIS, 1, cabinet)
    assert version.publiee is True
    assert "webhook planning refuse (statut 500)" in caplog.text
