"""Recette des écrans des personnes : liste, import, appariement, accueil."""

import datetime
import io

import pytest

from comptes.models import Personne
from presences.services import importer_fichier
from presences.tests.fabrique import en_direct, fabriquer_payload

from .fabrique_fiche import fiche, ligne_fiche

pytestmark = pytest.mark.django_db

LISTE = "/personnes/"
IMPORTER = "/personnes/importer/"
APPARIEMENT = "/personnes/appariement/"


def fichier(octets, nom="fiche.json"):
    flux = io.BytesIO(octets)
    flux.name = nom
    return flux


@pytest.fixture
def agendas_importes():
    """Un import de présences réussi, donc des agendas à apparier."""
    return importer_fichier(
        en_direct(
            fabriquer_payload(
                datetime.date(2026, 9, 1),
                datetime.date(2026, 9, 2),
                praticiens=("DUPONT Alice", "INCONNU Zoe"),
            )
        ),
        None,
    )


# --- Accès -------------------------------------------------------------------


@pytest.mark.parametrize("url", [LISTE, IMPORTER, APPARIEMENT])
def test_anonyme_redirige_vers_la_connexion(client, url):
    reponse = client.get(url)

    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


@pytest.mark.parametrize("url", [LISTE, IMPORTER, APPARIEMENT])
def test_salariee_refusee(client, salariee, connecter, url):
    connecter(client, salariee)

    assert client.get(url).status_code == 403


def test_principale_voit_la_liste_sans_liens_d_action(client, principale, connecter):
    connecter(client, principale)

    reponse = client.get(LISTE)

    assert reponse.status_code == 200
    assert IMPORTER not in reponse.content.decode()
    assert APPARIEMENT not in reponse.content.decode()


def test_cabinet_voit_la_liste_avec_les_liens(client, cabinet, connecter):
    connecter(client, cabinet)

    contenu = client.get(LISTE).content.decode()

    assert IMPORTER in contenu
    assert APPARIEMENT in contenu


@pytest.mark.parametrize("url", [IMPORTER, APPARIEMENT])
def test_principale_refusee_sur_les_actions(client, principale, connecter, url):
    connecter(client, principale)

    assert client.get(url).status_code == 403


# --- Liste -------------------------------------------------------------------


def test_liste_affiche_les_personnes_et_le_bandeau_regles(client, cabinet, connecter):
    Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.ASSISTANTE,
        heures_hebdo=39,
        jours_fixes=["Mardi"],
    )
    connecter(client, cabinet)

    contenu = client.get(LISTE).content.decode()

    assert "DUPONT" in contenu
    assert "Alice" in contenu
    assert "alice_dup" in contenu
    assert "Règles :" in contenu


def test_liste_dit_l_etat_du_compte(client, cabinet, connecter):
    Personne.objects.create(
        nom="DUPONT", prenom="Alice", role_metier=Personne.RoleMetier.ASSISTANTE
    )
    connecter(client, cabinet)

    assert "aucun" in client.get(LISTE).content.decode()


# --- Import ------------------------------------------------------------------


def test_import_par_la_page(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = client.post(
        IMPORTER,
        {"fichier": fichier(fiche([ligne_fiche("DUPONT Alice")]))},
    )

    assert reponse.status_code == 200
    assert Personne.objects.filter(nom="DUPONT", prenom="Alice").exists()
    assert "1 ligne exploitable" in reponse.content.decode()


def test_import_affiche_ignorees_et_avertissements(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = client.post(
        IMPORTER,
        {
            "fichier": fichier(
                fiche(
                    [
                        ligne_fiche("New team member"),
                        ligne_fiche("DUPONT Alice", heures=30),
                    ]
                )
            )
        },
    )

    contenu = reponse.content.decode()
    assert "hors convention" in contenu
    assert "hors gabarits" in contenu


def test_import_refuse_une_colonne_inattendue(client, cabinet, connecter):
    connecter(client, cabinet)
    ligne = ligne_fiche("DUPONT Alice")
    ligne["NSS"] = "peu importe"

    reponse = client.post(IMPORTER, {"fichier": fichier(fiche([ligne]))})

    contenu = reponse.content.decode()
    assert "Fichier refusé" in contenu
    assert "NSS" in contenu
    assert "peu importe" not in contenu
    assert not Personne.objects.exists()


def test_import_refuse_une_mauvaise_extension(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = client.post(
        IMPORTER,
        {"fichier": fichier(fiche([ligne_fiche("DUPONT Alice")]), nom="fiche.txt")},
    )

    assert "extension .json" in reponse.content.decode()
    assert not Personne.objects.exists()


# --- Appariement -------------------------------------------------------------


def test_appariement_sans_import_le_dit(client, cabinet, connecter):
    connecter(client, cabinet)

    contenu = client.get(APPARIEMENT).content.decode()

    assert "Aucun import de présences réussi" in contenu


def test_appariement_propose(client, cabinet, connecter, agendas_importes):
    Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=True,
    )
    connecter(client, cabinet)

    contenu = client.get(APPARIEMENT).content.decode()

    assert "DUPONT Alice" in contenu
    assert "exact" in contenu
    # L'agenda que personne ne réclame apparaît en orphelin.
    assert "INCONNU Zoe" in contenu


def test_appariement_applique(client, cabinet, connecter, agendas_importes):
    alice = Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=True,
    )
    connecter(client, cabinet)

    reponse = client.post(APPARIEMENT)

    assert reponse.status_code == 302
    assert reponse.url == APPARIEMENT
    alice.refresh_from_db()
    assert alice.agenda_doctolib == "DUPONT Alice"


def test_appariement_get_n_ecrit_rien(client, cabinet, connecter, agendas_importes):
    alice = Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=True,
    )
    connecter(client, cabinet)

    client.get(APPARIEMENT)

    alice.refresh_from_db()
    assert alice.agenda_doctolib == ""


# --- Accueil -----------------------------------------------------------------


def test_accueil_message_pour_la_salariee(client, salariee, connecter):
    connecter(client, salariee)

    contenu = client.get("/").content.decode()

    assert "Votre compte est actif" in contenu
    assert LISTE not in contenu


@pytest.mark.parametrize("role", ["cabinet", "principale"])
def test_accueil_lien_personnes_selon_le_role(
    client, connecter, cabinet, principale, role
):
    connecter(client, cabinet if role == "cabinet" else principale)

    contenu = client.get("/").content.decode()

    assert LISTE in contenu
    assert "Votre compte est actif" not in contenu
