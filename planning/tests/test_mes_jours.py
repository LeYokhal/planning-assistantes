"""Recette de « Mes jours » (brique 4b) : ses jours publiés, rien d'une autre, sans `DATA`.

Décisions D (page serveur minimale, sans `DATA`), P2 (plage entière, mois
calendaire prioritaire pour une date partagée), Q7 (libellé « Prénom Nom »),
P3 (praticiens sans filtre `actif`). La salariée du jeu est BERNARD Emma
(`emma_ber`, celle d'`etat_propre`) ; PETIT Sara est au secrétariat le même jour
et ne doit jamais apparaître.
"""

import datetime

import pytest

from absences.models import AbsenceSalariee
from absences.tests import fabrique as fabrique_absences
from planning import historique, services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = f"/mes-jours/{fabrique.MOIS}/"
TYPES = ("Maladie", "Congé payé", "Retard", "Ecole")


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


@pytest.fixture
def emma(salariee, jeu):
    """Le compte salariée rattaché à BERNARD Emma."""
    return fabrique_absences.lier(salariee, jeu["personnes"]["Emma"])


def _publier(cabinet, state=None):
    version = services.enregistrer(fabrique.MOIS, 0, state or fabrique.etat_propre(), cabinet)
    return services.publier(fabrique.MOIS, version.numero, cabinet)


def _version_publiee(mois, numero, affectations):
    """Une version publiée posée directement en base : état non vérifié, voulu."""
    return PlanningVersion.objects.create(
        mois=mois, numero=numero, state=fabrique.etat(affectations), publiee=True
    )


# --- Accès --------------------------------------------------------------------


def test_anonyme_redirige(client, jeu):
    reponse = client.get(URL)
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_cabinet_refuse(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    assert client.get(URL).status_code == 403


def test_racine_redirige_vers_le_mois_courant(client, salariee, connecter):
    connecter(client, salariee)
    reponse = client.get("/mes-jours/")
    assert reponse.status_code == 302
    assert reponse.url.startswith("/mes-jours/20")


def test_mois_invalide_introuvable(client, salariee, connecter):
    connecter(client, salariee)
    assert client.get("/mes-jours/2026-13/").status_code == 404


def test_lien_dans_l_accueil(client, salariee, cabinet, connecter):
    """Brique 6a : `/` redirige la salariée vers ses jours ; le cabinet n'a pas ce lien."""
    connecter(client, salariee)
    reponse = client.get("/")
    assert reponse.status_code == 302 and reponse["Location"] == "/mes-jours/"
    assert 'href="/mes-jours/"' in client.get(URL).content.decode()
    client.logout()
    connecter(client, cabinet)
    assert 'href="/mes-jours/"' not in client.get("/").content.decode()


# --- Contenu ------------------------------------------------------------------


def test_compte_sans_personne_voit_un_message(client, salariee, connecter, jeu):
    connecter(client, salariee)
    reponse = client.get(URL)
    assert reponse.status_code == 200
    assert "pas encore rattaché" in reponse.content.decode()


def test_mois_non_publie(client, emma, connecter, cabinet):
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)   # enregistrée, pas publiée
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    assert "pas encore publié" in contenu
    assert "DUPONT" not in contenu


def test_ses_jours_et_rien_d_une_autre(client, emma, connecter, cabinet):
    _publier(cabinet)
    connecter(client, emma)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert "Version 1, publiée le" in contenu
    assert "29/09/2026" in contenu and "Alice DUPONT" in contenu and "journée" in contenu
    # Sara est au secrétariat le même jour : rien d'elle, ni de sa case, ni de DATA.
    for mot in ("Sara", "PETIT", "sara_pet", "Secrétariat", "planning-data", "conges"):
        assert mot not in contenu, mot
    # Le 29 septembre est dans la plage d'octobre (semaines complètes) mais hors du mois : marqué.
    jours = reponse.context["resultat"]["jours"]
    assert [(j["date"].isoformat(), j["t"], j["x"], j["slot_libelle"], j["hors_mois"]) for j in jours] == [
        ("2026-09-29", "J", False, "Alice DUPONT", True)
    ]
    assert 'class="voisin"' in contenu


def test_case_misc_journee_courte_et_hors_quota(client, emma, connecter, cabinet):
    state = fabrique.etat({"2026-09-29": {"sureffectif": [fabrique.brique("emma_ber", "C", x=True)]}})
    _publier(cabinet, state)
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    assert "Sureffectif" in contenu
    assert "journée courte (fin 16h30)" in contenu and "(heures sup)" in contenu


def test_principale_rattachee_voit_ses_jours(client, principale, connecter, cabinet, jeu):
    fabrique_absences.lier(principale, jeu["personnes"]["Emma"])
    _publier(cabinet)
    connecter(client, principale)
    assert "Alice DUPONT" in client.get(URL).content.decode()


def test_aucun_type_d_absence_dans_la_page(client, emma, connecter, cabinet, jeu):
    """`DATA` n'est jamais servi : avec des absences de tout type, la page n'en dit rien."""
    for libelle, jour in (("Maladie", 6), ("Congé payé", 7)):
        fabrique_absences.absence(
            jeu["personnes"]["Emma"],
            fabrique.type_absence(libelle),
            datetime.date(2026, 10, jour),
            datetime.date(2026, 10, jour),
            statut=AbsenceSalariee.Statut.DECLAREE,
        )
    _publier(cabinet)
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    for mot in TYPES + ("planning-data", "planning-state", "planning-meta"):
        assert mot not in contenu, mot


def test_slot_inconnu_reste_brut(client, emma, connecter):
    _version_publiee(fabrique.MOIS, 1, {"2026-10-06": {"praticien_parti": [fabrique.brique("emma_ber")]}})
    connecter(client, emma)
    assert "praticien_parti" in client.get(URL).content.decode()


def test_praticien_inactif_garde_son_libelle(client, emma, connecter, cabinet, jeu):
    _publier(cabinet)
    alice = jeu["personnes"]["Alice"]
    alice.actif = False
    alice.save(update_fields=["actif"])
    connecter(client, emma)
    assert "Alice DUPONT" in client.get(URL).content.decode()


def test_plage_entiere_et_mois_calendaire_prioritaire(client, emma, connecter):
    """P2 : les jours du mois voisin sont montrés ; pour une date partagée, le mois calendaire fait foi."""
    _version_publiee("2026-10", 1, {
        "2026-10-27": {"alice_dup": [fabrique.brique("emma_ber")]},
        "2026-11-01": {"sureffectif": [fabrique.brique("emma_ber")]},
    })
    _version_publiee("2026-11", 1, {
        "2026-10-27": {"sureffectif": [fabrique.brique("emma_ber")]},
        "2026-11-01": {"administratif": [fabrique.brique("emma_ber")]},
    })
    connecter(client, emma)
    reponse = client.get(URL)
    jours = [
        (j["date"].isoformat(), j["slot_libelle"], j["hors_mois"], j["source_numero"])
        for j in reponse.context["resultat"]["jours"]
    ]
    assert jours == [("2026-10-27", "Alice DUPONT", False, 1), ("2026-11-01", "Administratif", True, 1)]
    assert 'class="voisin"' in reponse.content.decode()


def test_service_sans_version_publiee(jeu):
    assert services.jours_publies(jeu["personnes"]["Emma"], fabrique.MOIS) is None


def test_mois_historique_importe(client, salariee, connecter, cabinet):
    """Brique 7a (C7.1) : « Mes jours » lit une version historique **sans changement**.

    Aucune présence Doctolib n'est importée pour ce mois : `jours_publies` ne lit
    que le `state` et les personnes, jamais `DATA`. La colonne d'une fiche close
    et non planifiée garde son libellé (P3, C7.4).
    """
    fiches = fabrique.personnes_historiques()
    fabrique_absences.lier(salariee, fiches["test_ass"])
    affectations = dict(fabrique.affectations_historiques())
    # Jeudi 2 avril : dans la plage de mars (semaines complètes), hors du mois.
    affectations["2026-04-02"] = {"secretariat": [fabrique.brique("test_ass", "C", x=True)]}
    version = historique.executer(
        historique.analyser(fabrique.planning_exporte(affectations=affectations)), cabinet
    )

    connecter(client, salariee)
    reponse = client.get(f"/mes-jours/{fabrique.MOIS_HISTORIQUE}/")
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert f"Version {version.numero}, publiée le" in contenu
    assert [
        (j["date"].isoformat(), j["t"], j["x"], j["slot_libelle"], j["hors_mois"])
        for j in reponse.context["resultat"]["jours"]
    ] == [
        ("2026-03-03", "J", False, "Test PRATICIEN", False),
        ("2026-03-04", "J", False, "Test PRATICIEN", False),
        ("2026-04-02", "C", True, "Secrétariat", True),
    ]
    assert 'class="voisin"' in contenu and "(heures sup)" in contenu
    # Rien de la secrétaire du même jour, et toujours pas de `DATA`.
    for mot in ("test_sec", "SECRETAIRE", "planning-data", "conges"):
        assert mot not in contenu, mot
