"""Recette de l'API des versions et du service `enregistrer`."""

import json

import pytest

from audit.models import EvenementAudit
from planning import services, views
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = f"/api/planning/{fabrique.MOIS}/versions/"


def poster(client, corps, **extra):
    return client.post(URL, data=json.dumps(corps), content_type="application/json", **extra)


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


# --- Accès et forme ---------------------------------------------------------


def test_anonyme_redirige(client, jeu):
    reponse = poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_salariee_refusee(client, salariee, connecter, jeu):
    connecter(client, salariee)
    assert poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()}).status_code == 403


def test_get_refuse(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = client.get(URL)
    assert reponse.status_code == 405
    assert reponse.json() == {"erreur": "methode_non_autorisee"}


def test_mois_invalide(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = client.post("/api/planning/2026-13/versions/", data="{}", content_type="application/json")
    assert reponse.status_code == 400


@pytest.mark.parametrize("corps", ["pas du json", "[]", '{"state": {}}', '{"version_de_base": "1", "state": {}}', '{"version_de_base": -1, "state": {}}', '{"version_de_base": true, "state": {}}'])
def test_corps_invalide(client, cabinet, connecter, jeu, corps):
    connecter(client, cabinet)
    reponse = client.post(URL, data=corps, content_type="application/json")
    assert reponse.status_code == 400
    assert PlanningVersion.objects.count() == 0


def test_plafond_du_corps(client, cabinet, connecter, jeu, monkeypatch):
    connecter(client, cabinet)
    monkeypatch.setattr(views, "CORPS_MAX_OCTETS", 20)
    reponse = poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})
    assert reponse.status_code == 413
    assert PlanningVersion.objects.count() == 0


# --- Enregistrement -----------------------------------------------------------


def test_premier_enregistrement(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    reponse = poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})

    assert reponse.status_code == 201
    assert reponse.json() == {"numero": 1}
    version = PlanningVersion.objects.get()
    assert version.mois == fabrique.MOIS and version.numero == 1
    assert version.version_de_base == 0
    assert version.auteur == cabinet
    assert version.state == fabrique.etat_propre()
    assert version.verifications == [] and version.publiee is False

    evenement = EvenementAudit.objects.get(action="planning_enregistre")
    assert evenement.qui == cabinet
    assert evenement.id_objet == str(version.pk)
    assert evenement.details == {"mois": fabrique.MOIS, "numero": 1, "nb_briques": 2}


def test_principale_enregistre_aussi(client, principale, connecter, jeu):
    connecter(client, principale)
    assert poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()}).status_code == 201


def test_versions_successives(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    assert poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()}).json() == {"numero": 1}
    assert poster(client, {"version_de_base": 1, "state": fabrique.etat_propre()}).json() == {"numero": 2}
    assert list(PlanningVersion.objects.values_list("numero", flat=True)) == [2, 1]   # ordering (mois, -numero)


def test_409_si_la_base_est_perimee(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})
    reponse = poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})

    assert reponse.status_code == 409
    assert reponse.json() == {"derniere": 1}
    assert PlanningVersion.objects.count() == 1


def test_409_par_integrity_error_jamais_500(client, cabinet, connecter, jeu, monkeypatch):
    """Deux workers, même base : la contrainte unique tranche, la réponse est 409."""
    connecter(client, cabinet)
    poster(client, {"version_de_base": 0, "state": fabrique.etat_propre()})
    poster(client, {"version_de_base": 1, "state": fabrique.etat_propre()})   # la base est à 2

    original = services.numero_courant
    appels = []

    def perime(mois):   # la première lecture voit encore 1, comme un worker en retard
        appels.append(mois)
        return 1 if len(appels) == 1 else original(mois)

    monkeypatch.setattr(services, "numero_courant", perime)
    reponse = poster(client, {"version_de_base": 1, "state": fabrique.etat_propre()})

    assert reponse.status_code == 409
    assert reponse.json() == {"derniere": 2}
    assert PlanningVersion.objects.count() == 2
    assert len(appels) == 2   # relecture après l'IntegrityError


def test_422_sans_texte_et_rien_d_ecrit(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    state = fabrique.etat({"2026-09-29": {"alice_dup": [fabrique.brique("zoe_gir")]}, "2026-10-13": {"alice_dup": [fabrique.brique("emma_ber")]}})
    reponse = poster(client, {"version_de_base": 0, "state": state})

    assert reponse.status_code == 422
    violations = reponse.json()["violations"]
    assert sorted(v["code"] for v in violations) == ["exclusive_ailleurs", "jour_bloque"]
    for v in violations:
        assert set(v) == {"code", "date", "slot", "s"}
    assert PlanningVersion.objects.count() == 0
    assert not EvenementAudit.objects.filter(action="planning_enregistre").exists()


def test_nettoyage_des_cles_et_des_notes(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    state = fabrique.etat_propre()
    state.update({"conges": [{"s": "emma_ber", "date": "2026-10-13", "type": "Maladie", "bloque": True}], "cours": {}, "modifie": "hier", "initialise": True, "notes": {"2026-09-29": "un mot"}})
    reponse = poster(client, {"version_de_base": 0, "state": state})

    assert reponse.status_code == 201
    enregistre = PlanningVersion.objects.get().state
    assert set(enregistre) == {"affectations", "feries", "feries_off", "notes"}
    assert enregistre["notes"] == {"2026-09-29": ["un mot"]}


def test_version_vide_puis_rechargement(client, cabinet, connecter, jeu):
    """Une version aux affectations vides reste vide au rechargement : la page ne re-propose pas."""
    connecter(client, cabinet)
    assert poster(client, {"version_de_base": 0, "state": fabrique.etat()}).status_code == 201

    reponse = client.get(f"/planning/{fabrique.MOIS}/")
    assert reponse.status_code == 200
    assert reponse.context["state"] == fabrique.etat()
    assert reponse.context["meta"]["numero"] == 1
    contenu = reponse.content.decode()
    assert '"numero": 1' in contenu


# --- Service --------------------------------------------------------------------


def test_service_enregistrer_direct(cabinet, jeu):
    version = services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    assert version.numero == 1
    with pytest.raises(services.Conflit) as conflit:
        services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    assert conflit.value.derniere == 1
    with pytest.raises(services.Invalide) as invalide:
        services.enregistrer(fabrique.MOIS, 1, fabrique.etat({"2026-12-01": {"alice_dup": [fabrique.brique("emma_ber")]}}), cabinet)
    assert [v.code for v in invalide.value.violations] == ["hors_plage"]
    assert services.numero_courant(fabrique.MOIS) == 1
    assert services.etat_vide() == {"affectations": {}, "feries": {}, "feries_off": [], "notes": {}}


def test_nb_briques():
    assert services.nb_briques(fabrique.etat_propre()) == 2
    assert services.nb_briques({"affectations": {"x": "pas un dict"}}) == 0
