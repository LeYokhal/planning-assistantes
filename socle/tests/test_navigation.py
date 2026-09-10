"""Navigation par rôle de la coquille (brique 6a, C6.6) : chaque entrée chez son rôle, absente chez les autres.

Une page par app pour chaque rôle ; la page planning, elle, ne reçoit rien de
la coquille (ses blocs `style_base` et `en_tete_page` sont vidés par `page.html`).
"""

import pytest

from absences.tests import fabrique as fabrique_absences
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

MOIS = fabrique.MOIS
PAGES_GESTION = ["/", "/absences/", f"/presences/{MOIS}/", "/personnes/"]
PAGES_PERSONNELLES = ["/mes-absences/", f"/mes-jours/{MOIS}/", "/mon-profil/"]

LIENS_GESTION = ('href="/planning/"', 'href="/absences/"', 'href="/presences/"')
LIENS_PERSONNELS = ('href="/mes-jours/"', 'href="/mes-absences/"', 'href="/mon-profil/"')
ADMIN = 'href="/admin/"'
DECONNEXION = 'action="/deconnexion/"'


def _page(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 200, url
    return reponse.content.decode()


@pytest.mark.parametrize("url", PAGES_GESTION)
def test_cabinet(client, cabinet, connecter, url):
    connecter(client, cabinet)
    contenu = _page(client, url)
    assert all(lien in contenu for lien in LIENS_GESTION)
    assert not any(lien in contenu for lien in LIENS_PERSONNELS)
    assert ADMIN in contenu
    assert DECONNEXION in contenu
    assert '<p class="menu-titre">Cabinet</p>' in contenu
    assert 'class="onglets-bas"' not in contenu


@pytest.mark.parametrize("url", PAGES_GESTION + PAGES_PERSONNELLES)
def test_principale(client, principale, connecter, url):
    connecter(client, principale)
    contenu = _page(client, url)
    assert all(lien in contenu for lien in LIENS_GESTION)
    assert all(lien in contenu for lien in LIENS_PERSONNELS)
    assert ADMIN not in contenu  # le rôle, pas `is_staff`
    assert DECONNEXION in contenu
    assert '<p class="menu-titre">Assistante principale</p>' in contenu
    assert 'class="onglets-bas"' not in contenu


def test_principale_rattachee_est_saluee_dans_le_menu(client, principale, connecter):
    fabrique_absences.lier(principale, fabrique_absences.personne())
    connecter(client, principale)
    contenu = _page(client, "/")
    assert '<p class="menu-titre">Bonjour Alice</p>' in contenu
    assert "<h1>Tableau de bord</h1>" in contenu  # D-8 : jamais dans le titre


@pytest.mark.parametrize("url", PAGES_PERSONNELLES)
def test_salariee(client, salariee, connecter, url):
    connecter(client, salariee)
    contenu = _page(client, url)
    assert all(lien in contenu for lien in LIENS_PERSONNELS)
    assert not any(lien in contenu for lien in LIENS_GESTION)
    assert 'href="/personnes/"' not in contenu
    assert ADMIN not in contenu
    assert DECONNEXION in contenu
    assert 'class="onglets-bas"' in contenu


# --- Page courante -----------------------------------------------------------


def test_page_courante(client, principale, connecter):
    connecter(client, principale)
    assert 'href="/absences/" aria-current="page">Absences</a>' in _page(client, "/absences/")
    presences = _page(client, f"/presences/{MOIS}/")
    assert 'href="/presences/" aria-current="page">Présences &amp; personnes</a>' in presences
    assert 'href="/presences/" aria-current="page">Présences</a>' in presences
    personnes = _page(client, "/personnes/")
    assert 'href="/presences/" aria-current="page">Présences &amp; personnes</a>' in personnes
    assert 'href="/personnes/" aria-current="page">Personnes</a>' in personnes
    assert 'href="/planning/" aria-current="page"' not in personnes


def test_onglet_bas_courant(client, salariee, connecter):
    connecter(client, salariee)
    contenu = _page(client, f"/mes-jours/{MOIS}/")
    assert 'href="/mes-jours/" aria-current="page">Mes jours</a>' in contenu
    assert 'href="/mes-absences/" aria-current="page"' not in contenu


# --- Page planning : rien de la coquille ------------------------------------


def test_page_planning_sans_coquille(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    contenu = _page(client, f"/planning/{MOIS}/")
    assert "planning-data" in contenu
    for marque in ('class="barre"', '<details class="avatar"', "socle/commun.css", "socle/polices.css"):
        assert marque not in contenu, marque
    assert "socle/favicon.png" in contenu  # le seul élément commun, hors bloc


def test_page_sans_import_avec_coquille(client, cabinet, connecter):
    connecter(client, cabinet)
    contenu = _page(client, f"/planning/{MOIS}/")
    assert "Aucun import de présences réussi" in contenu
    assert 'class="barre"' in contenu
    assert "socle/commun.css" in contenu


@pytest.mark.parametrize("role", ["cabinet", "principale"])
def test_une_seule_deconnexion_sur_le_tableau_de_bord(
    client, cabinet, principale, connecter, role
):
    connecter(client, cabinet if role == "cabinet" else principale)
    assert _page(client, "/").count(DECONNEXION) == 1
