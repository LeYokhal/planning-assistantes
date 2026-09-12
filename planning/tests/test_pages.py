"""Recette des pages : accès, blocs de base, écran sans import, non-régression."""

import pytest
from django.utils import timezone

from planning import services
from planning.tests import fabrique
from presences.fenetres import mois_precedent

pytestmark = pytest.mark.django_db

URL = f"/planning/{fabrique.MOIS}/"


# --- Accès ----------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/planning/", URL, f"/planning/{fabrique.MOIS}/copie/"])
def test_anonyme_redirige_vers_la_connexion(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 302
    assert reponse.url == f"/connexion/?next={url}"


@pytest.mark.parametrize("url", ["/planning/", URL, f"/planning/{fabrique.MOIS}/copie/"])
def test_salariee_refusee(client, salariee, connecter, url):
    connecter(client, salariee)
    assert client.get(url).status_code == 403


def test_racine_redirige_vers_le_mois_courant(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get("/planning/")
    assert reponse.status_code == 302
    assert reponse.url == f"/planning/{timezone.localdate():%Y-%m}/"


def test_mois_invalide_introuvable(client, principale, connecter):
    connecter(client, principale)
    assert client.get("/planning/2026-13/").status_code == 404


# --- Sans import ------------------------------------------------------------------


def test_sans_import_ecran_dedie(client, cabinet, connecter):
    fabrique.personnes()
    connecter(client, cabinet)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert "Aucun import de présences réussi" in contenu
    assert "planning-data" not in contenu
    assert "/presences/importer/" in contenu       # rôle cabinet
    assert 'class="barre"' in contenu               # page ordinaire, coquille de base présente


def test_sans_import_principale_sans_lien_d_import(client, principale, connecter):
    connecter(client, principale)
    contenu = client.get(URL).content.decode()
    assert "/presences/importer/" not in contenu
    assert f"/presences/{fabrique.MOIS}/" in contenu


# --- La page --------------------------------------------------------------------


def test_page_servie(client, principale, connecter, cabinet):
    fabrique.jeu_complet(cabinet)
    connecter(client, principale)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert '<html lang="fr" class="planning">' in contenu
    assert 'class="planning"' in contenu
    for bloc in ("planning-data", "planning-state", "planning-meta"):
        assert f'<script id="{bloc}" type="application/json">' in contenu
    assert "planning/moteur.js" in contenu and "planning/page.js" in contenu
    assert "planning/styles.css" in contenu
    # Brique 6d : la barre commune vient de barre.css seule — ni commun.css (largeur de
    # lecture), ni polices.css, ni le titre de la coquille.
    assert 'class="barre"' in contenu
    assert "socle/barre.css" in contenu
    assert "socle/commun.css" not in contenu
    assert "socle/polices.css" not in contenu
    assert 'class="titre-page"' not in contenu
    # Navigation : la barre porte les liens de gestion — sur le mois de la page depuis la
    # brique 8 (D8.5) — et l'unique déconnexion ; l'en-tête porte les mois voisins.
    assert f'href="/presences/{fabrique.MOIS}/"' in contenu and f'href="/absences/?mois={fabrique.MOIS}"' in contenu
    assert f'href="/planning/{mois_precedent(fabrique.MOIS)}/"' in contenu
    assert contenu.count('action="/deconnexion/"') == 1


def test_page_pose_le_cookie_csrftoken(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    reponse = client.get(URL)
    assert "csrftoken" in reponse.cookies
    assert 'name="csrfmiddlewaretoken"' in reponse.content.decode()


def test_meta_numero_zero_sans_version_puis_un(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    meta = client.get(URL).context["meta"]
    assert meta["numero"] == 0 and meta["autonome"] is False
    assert set(meta["urls"]) == {"versions", "erreurs", "copie"}
    assert meta["urls"]["versions"] == f"/api/planning/{fabrique.MOIS}/versions/"

    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    reponse = client.get(URL)
    assert reponse.context["meta"]["numero"] == 1
    assert reponse.context["state"] == fabrique.etat_propre()


def test_data_de_la_page_porte_le_libelle_du_type_pour_les_roles_admis(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    data = client.get(URL).context["data"]
    assert any(c["type"] == "Congé payé" for c in data["conges"])


# --- Accueil et non-régression ------------------------------------------------


def test_entree_planning_dans_l_accueil(client, cabinet, salariee, connecter):
    connecter(client, cabinet)
    assert 'href="/planning/"' in client.get("/").content.decode()
    client.logout()
    connecter(client, salariee)
    # Brique 6a : `/` redirige la salariée ; sa coquille (« Mes jours ») ne mène pas au planning.
    assert 'href="/planning/"' not in client.get(f"/mes-jours/{fabrique.MOIS}/").content.decode()
