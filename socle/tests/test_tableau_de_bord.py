"""Tableau de bord (brique 6a, C6.10 / C6.12 / C7.10) : horizon, pastilles, demandes, données, rôles.

L'horizon dépend du jour : les tests de `construire` fixent la date ; les tests
HTTP ne lisent que ce qui ne dépend pas du calendrier réel.
"""

import datetime

import pytest

from absences.tests import fabrique as fabrique_absences
from planning.models import PlanningVersion
from planning.tests import fabrique
from presences.models import ImportPresences
from socle.tableau_de_bord import construire

pytestmark = pytest.mark.django_db

MOIS = fabrique.MOIS  # 2026-10
HISTORIQUE = fabrique.MOIS_HISTORIQUE  # 2026-03
AUJOURD_HUI = datetime.date(2026, 9, 15)


def _version(mois, numero, publiee=False, **extra):
    return PlanningVersion.objects.create(
        mois=mois, numero=numero, state=fabrique.etat(), publiee=publiee, **extra
    )


def _lignes(contexte):
    """Toutes les lignes de la carte Planning, indexées par mois."""
    planning = contexte["planning"]
    return {
        ligne["mois"]: ligne
        for ligne in planning["a_venir"] + [planning["en_cours"]] + planning["passes"]
    }


def _ligne_html(contenu, mois):
    """Le fragment `<li … data-mois="AAAA-MM">…</li>` d'une ligne rendue."""
    debut = contenu.index(f'data-mois="{mois}"')
    return contenu[debut : contenu.index("</li>", debut)]


# --- Accès -------------------------------------------------------------------


def test_anonyme_redirige_vers_la_connexion(client):
    reponse = client.get("/")
    assert reponse.status_code == 302 and reponse["Location"] == "/connexion/?next=/"


def test_salariee_redirigee_vers_ses_jours(client, salariee, connecter):
    connecter(client, salariee)
    reponse = client.get("/")
    assert reponse.status_code == 302 and reponse["Location"] == "/mes-jours/"
    assert "Congé payé" not in reponse.content.decode()


def test_salariee_sans_personne_aussi(client, salariee, connecter):
    assert salariee.personne_id is None
    connecter(client, salariee)
    assert client.get("/")["Location"] == "/mes-jours/"


# --- Horizon (fonction pure, date fixée) ------------------------------------


def test_horizon_sans_rien(principale):
    contexte = construire(principale, AUJOURD_HUI)
    planning = contexte["planning"]
    assert planning["a_venir"] == [] and planning["passes"] == []
    assert planning["en_cours"]["mois"] == "2026-09"
    assert planning["en_cours"]["etat"] == "Aucune version enregistrée"
    assert planning["importees_jusqu_au"] is None
    assert planning["preparer"] == "2026-10"
    assert contexte["demandes"] == [] and contexte["nb_demandes"] == 0
    assert contexte["dernier_import"] is None
    assert contexte["nb_planifiees"] == 0
    assert contexte["peut_importer"] is False


def test_horizon_trois_rubriques(principale):
    _version(MOIS, 1)  # à venir
    _version("2026-09", 3, publiee=True)  # en cours
    _version("2026-08", 1, publiee=True)  # passé
    planning = construire(principale, AUJOURD_HUI)["planning"]
    assert [ligne["mois"] for ligne in planning["a_venir"]] == [MOIS]
    assert planning["en_cours"]["mois"] == "2026-09"
    assert [ligne["mois"] for ligne in planning["passes"]] == ["2026-08"]
    assert planning["preparer"] == "2026-11"


def test_pastilles(principale):
    _version(MOIS, 1)
    ligne = _lignes(construire(principale, AUJOURD_HUI))[MOIS]
    assert ligne["etat"] == "Version 1 · non publiée"
    assert ligne["url"] == f"/planning/{MOIS}/"
    PlanningVersion.objects.filter(mois=MOIS, numero=1).update(publiee=True)
    assert _lignes(construire(principale, AUJOURD_HUI))[MOIS]["etat"] == "Publiée (v1)"
    _version(MOIS, 2)
    assert _lignes(construire(principale, AUJOURD_HUI))[MOIS]["etat"] == "Version 2 — publiée : v1"


def test_mois_historique_sans_marqueur(principale):
    _version(HISTORIQUE, 1, publiee=True, verifications={"historique": True, "imports": []})
    ligne = _lignes(construire(principale, AUJOURD_HUI))[HISTORIQUE]
    assert ligne["etat"] == "Publiée (v1)"
    assert ligne["historique"] is True
    assert ligne["manquantes"] is False  # C7.10 : sans présences, et ce n'est pas un manque
    assert ligne["url"] == f"/planning/{HISTORIQUE}/historique/"


def test_donnees_manquantes_des_un_jour_non_couvert(principale, cabinet):
    _version(MOIS, 1)
    assert _lignes(construire(principale, AUJOURD_HUI))[MOIS]["manquantes"] is True
    fabrique.importer(cabinet, *fabrique.PLAGE.fenetres[0])  # une fenêtre sur deux
    assert _lignes(construire(principale, AUJOURD_HUI))[MOIS]["manquantes"] is True
    fabrique.importer(cabinet, *fabrique.PLAGE.fenetres[1])
    assert _lignes(construire(principale, AUJOURD_HUI))[MOIS]["manquantes"] is False


def test_importees_jusqu_au(principale, cabinet):
    fabrique.importer_le_mois(cabinet)
    ImportPresences.objects.create(
        source=ImportPresences.Source.FICHIER,
        statut=ImportPresences.Statut.ECHEC,
        debut=datetime.date(2026, 12, 1),
        fin=datetime.date(2026, 12, 31),
    )
    planning = construire(principale, AUJOURD_HUI)["planning"]
    assert planning["importees_jusqu_au"] == fabrique.PLAGE.fin  # l'échec ne compte pas


# --- Demandes ----------------------------------------------------------------


def test_demandes_et_regle_k(principale, cabinet):
    alice = fabrique_absences.personne()
    bob = fabrique_absences.personne("MARTIN", "Bob")
    type_ = fabrique_absences.type_absence()
    fabrique_absences.absence(alice, type_)
    fabrique_absences.absence(bob, type_, debut=datetime.date(2026, 6, 2), fin=datetime.date(2026, 6, 2))

    contexte = construire(principale, AUJOURD_HUI)
    assert contexte["nb_demandes"] == 2
    assert [a.personne.prenom for a in contexte["demandes"]] == ["Alice", "Bob"]
    assert all(a.decidable for a in contexte["demandes"])

    fabrique_absences.lier(principale, alice)
    contexte = construire(principale, AUJOURD_HUI)
    assert [a.decidable for a in contexte["demandes"]] == [False, True]  # règle K
    assert all(a.decidable for a in construire(cabinet, AUJOURD_HUI)["demandes"])


def test_cinq_demandes_au_plus(principale):
    type_ = fabrique_absences.type_absence()
    for indice in range(6):
        personne = fabrique_absences.personne(nom=f"TEST{indice}", prenom="Zoe")
        jour = datetime.date(2026, 6, 1 + indice)
        fabrique_absences.absence(personne, type_, debut=jour, fin=jour)
    contexte = construire(principale, AUJOURD_HUI)
    assert contexte["nb_demandes"] == 6
    assert len(contexte["demandes"]) == 5


# --- Données -----------------------------------------------------------------


def test_donnees(principale, cabinet):
    fabrique.personnes()  # dix personnes planifiées
    imports = fabrique.importer_le_mois(cabinet)
    contexte = construire(cabinet, AUJOURD_HUI)
    assert contexte["nb_planifiees"] == 10
    assert contexte["dernier_import"].pk == imports[-1].pk
    assert contexte["peut_importer"] is True
    assert construire(principale, AUJOURD_HUI)["peut_importer"] is False


# --- Rendu -------------------------------------------------------------------


def test_page_principale_sans_rien(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get("/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert "<h1>Tableau de bord</h1>" in contenu
    assert "Bonjour" not in contenu
    assert "Aucune version enregistrée" in contenu
    assert "À venir" not in contenu
    assert "Aucune demande en attente." in contenu
    assert "Aucun import de présences réussi" in contenu
    assert "Importer un fichier" not in contenu
    assert 'href="/personnes/"' in contenu and 'href="/presences/"' in contenu


def test_page_cabinet(client, cabinet, connecter):
    _version(MOIS, 1)
    _version(HISTORIQUE, 1, publiee=True, verifications={"historique": True, "imports": []})
    fabrique.importer_le_mois(cabinet)
    connecter(client, cabinet)
    contenu = client.get("/").content.decode()

    octobre = _ligne_html(contenu, MOIS)
    assert "Octobre 2026" in octobre and "Version 1 · non publiée" in octobre
    assert f'href="/planning/{MOIS}/"' in octobre
    assert "Données Doctolib manquantes" not in octobre

    mars = _ligne_html(contenu, HISTORIQUE)
    assert "Mars 2026" in mars and "Publiée (v1)" in mars
    assert f'href="/planning/{HISTORIQUE}/historique/"' in mars
    assert "Données Doctolib manquantes" not in mars

    assert "Présences Doctolib importées jusqu'au 1 novembre 2026" in contenu
    assert 'href="/presences/importer/"' in contenu and "Importer un fichier" in contenu
    assert "Préparer un mois" in contenu


def test_page_demandes(client, principale, cabinet, connecter):
    alice = fabrique_absences.personne()
    type_ = fabrique_absences.type_absence()
    fabrique_absences.absence(alice, type_)
    fabrique_absences.absence(
        fabrique_absences.personne("MARTIN", "Bob"),
        type_,
        debut=datetime.date(2026, 6, 2),
        fin=datetime.date(2026, 6, 2),
    )
    fabrique_absences.lier(principale, alice)
    connecter(client, principale)
    contenu = client.get("/").content.decode()
    assert "2 demandes" in contenu
    assert "Alice DUPONT" in contenu and "Bob MARTIN" in contenu
    assert "Congé payé" in contenu
    assert contenu.count('class="demande"') == 2
    assert contenu.count("Décision réservée au cabinet") == 1
    assert 'href="/absences/">Voir tout</a>' in contenu

    client.logout()
    connecter(client, cabinet)
    assert "Décision réservée au cabinet" not in client.get("/").content.decode()
