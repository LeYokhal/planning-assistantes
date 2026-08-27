"""Recette de l'écran « présences du mois »."""

import datetime

import pytest
from django.utils import timezone

from presences import services
from presences.fenetres import plage_mois

from .fabrique import AGENDAS, en_direct, fabriquer_payload

pytestmark = pytest.mark.django_db

MOIS = "2026-10"
URL = f"/presences/{MOIS}/"
PLAGE = plage_mois(MOIS)


def _importer(cabinet, debut, fin, praticiens=AGENDAS, regle=None):
    """Fait entrer un payload fictif par le service, sans passer par la page."""
    return services.importer_fichier(
        en_direct(fabriquer_payload(debut, fin, praticiens, regle)), cabinet
    )


def _importer_le_mois(cabinet, regle=None):
    """Couvre toute la plage affichée : les deux fenêtres du mois."""
    return [
        _importer(cabinet, debut, fin, regle=regle) for debut, fin in PLAGE.fenetres
    ]


# --- Accès ------------------------------------------------------------------


def test_anonyme_redirige_vers_la_connexion(client):
    reponse = client.get(URL)
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_salariee_refusee(client, salariee, connecter):
    connecter(client, salariee)
    assert client.get(URL).status_code == 403


def test_principale_admise_sans_bouton_importer(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get(URL)

    assert reponse.status_code == 200
    assert "Importer un fichier S7" not in reponse.content.decode()


def test_cabinet_voit_le_bouton_importer(client, cabinet, connecter):
    connecter(client, cabinet)
    reponse = client.get(URL)

    assert reponse.status_code == 200
    assert "Importer un fichier S7" in reponse.content.decode()


# --- Navigation -------------------------------------------------------------


def test_racine_redirige_vers_le_mois_courant(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get("/presences/")

    assert reponse.status_code == 302
    assert reponse.url == f"/presences/{timezone.localdate():%Y-%m}/"


def test_mois_invalide_introuvable(client, principale, connecter):
    connecter(client, principale)
    assert client.get("/presences/2026-13/").status_code == 404


def test_liens_precedent_et_suivant(client, principale, connecter):
    connecter(client, principale)
    contenu = client.get(URL).content.decode()

    assert "/presences/2026-09/" in contenu
    assert "/presences/2026-11/" in contenu


# --- Contenu ----------------------------------------------------------------


def test_mois_entierement_couvert(client, cabinet, connecter):
    _importer_le_mois(cabinet)
    connecter(client, cabinet)
    contenu = client.get(URL).content.decode()

    for agenda in AGENDAS:
        assert agenda in contenu
    assert "✓" in contenu
    assert "non importé" not in contenu
    assert "jour(s) de la plage sans import" not in contenu


def test_sans_import_tout_est_signale(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert "35 jour(s) de la plage sans import" in contenu
    assert "non importé" in contenu
    assert reponse.context["couverture"].jours_non_couverts == 35


def test_couverture_partielle(client, cabinet, connecter):
    """Seule la première fenêtre est importée : les 4 derniers jours manquent."""
    debut, fin = PLAGE.fenetres[0]
    _importer(cabinet, debut, fin)
    connecter(client, cabinet)

    reponse = client.get(URL)
    assert reponse.context["couverture"].jours_non_couverts == 4
    assert "4 jour(s) de la plage sans import" in reponse.content.decode()


def test_import_recent_prime_sur_l_ancien(client, cabinet, connecter):
    """Un import plus récent corrige un plus ancien, sans rien supprimer."""

    def tout_ferme(jour, indice):
        return {"verdict": "fermé", "presence": False}

    ancien = _importer_le_mois(cabinet)[0]
    recents = _importer_le_mois(cabinet, regle=tout_ferme)

    connecter(client, cabinet)
    reponse = client.get(URL)
    couverture = reponse.context["couverture"]

    assert "fermé" in reponse.content.decode()
    assert "✓" not in reponse.content.decode()
    identifiants = {source.pk for source in couverture.sources}
    assert ancien.pk not in identifiants
    assert {recent.pk for recent in recents} == identifiants


def test_atypique_present_affiche_la_coche(client, cabinet, connecter):
    """`presence` est le signal primaire, jamais `creneaux_effectifs` seuls."""

    def atypique_present(jour, indice):
        return {
            "verdict": "ouvert (atypique)",
            "presence": True,
            "creneaux": (),
            "nb_rdv": 6,
            "duree_rdv": 330,
        }

    _importer_le_mois(cabinet, regle=atypique_present)
    connecter(client, cabinet)

    assert "✓ atypique · 6 RDV" in client.get(URL).content.decode()


def test_atypique_non_present_sans_coche(client, cabinet, connecter):
    def atypique_absent(jour, indice):
        return {
            "verdict": "ouvert (atypique)",
            "presence": False,
            "creneaux": (),
            "nb_rdv": 3,
            "duree_rdv": 90,
        }

    _importer_le_mois(cabinet, regle=atypique_absent)
    connecter(client, cabinet)
    contenu = client.get(URL).content.decode()

    assert "atypique · 3 RDV" in contenu
    assert "✓ atypique" not in contenu


def test_journee_courte_signalee(client, cabinet, connecter):
    def courte(jour, indice):
        return {
            "verdict": "ouvert",
            "presence": True,
            "creneaux": (("09:30", "13:30"),),
            "journee_courte": True,
            "nb_rdv": 5,
        }

    _importer_le_mois(cabinet, regle=courte)
    connecter(client, cabinet)

    assert "✓ 09:30–13:30 · courte" in client.get(URL).content.decode()


def test_agenda_absent_d_un_jour_couvert(client, cabinet, connecter):
    """Un agenda vu ailleurs mais absent d'un jour donne une case « ? »."""
    premiere, seconde = PLAGE.fenetres
    _importer(cabinet, premiere[0], premiere[1], praticiens=AGENDAS)
    _importer(cabinet, seconde[0], seconde[1], praticiens=(AGENDAS[0],))

    couverture = services.couverture(PLAGE.debut, PLAGE.fin)
    assert couverture.agendas == tuple(sorted(AGENDAS, key=str.casefold))

    dernier = couverture.semaines[-1].jours[-1]
    assert dernier.couvert
    assert [cellule.classe for cellule in dernier.cellules].count("inconnu") == 1


def test_panneau_sources(client, cabinet, connecter):
    imports = _importer_le_mois(cabinet)
    connecter(client, cabinet)
    contenu = client.get(URL).content.decode()

    for import_ in imports:
        assert f"Import #{import_.pk}" in contenu


def test_comptages_de_l_entete(client, cabinet, connecter):
    _importer_le_mois(cabinet)
    connecter(client, cabinet)
    couverture = client.get(URL).context["couverture"]

    lundi = couverture.semaines[0].jours[0]
    assert lundi.date == datetime.date(2026, 9, 28)
    assert lundi.nb_ouverts == 2 and lundi.nb_presents == 2

    samedi = couverture.semaines[0].jours[5]
    assert samedi.nb_ouverts == 0 and samedi.nb_presents == 0
