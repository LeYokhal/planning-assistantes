"""Navigation par rôle de la coquille (brique 6a, C6.6) : chaque entrée chez son rôle, absente chez les autres.

Une page par app pour chaque rôle ; la page planning, elle, reçoit la barre
(`barre.css`, brique 6d) mais ni `commun.css` ni le titre de la coquille.
"""

import re
from pathlib import Path

import pytest
from django.template.loader import get_template

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


def liens_attendus(url):
    """Brique 8 (D8.5) : les onglets de gestion portent le mois de la page quand elle en a un."""
    mois = re.search(r"\d{4}-\d{2}", url)
    if not mois:
        return LIENS_GESTION
    m = mois.group(0)
    return (f'href="/planning/{m}/"', f'href="/absences/?mois={m}"', f'href="/presences/{m}/"')


def _page(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 200, url
    return reponse.content.decode()


@pytest.mark.parametrize("url", PAGES_GESTION)
def test_cabinet(client, cabinet, connecter, url):
    connecter(client, cabinet)
    contenu = _page(client, url)
    assert all(lien in contenu for lien in liens_attendus(url))
    assert not any(lien in contenu for lien in LIENS_PERSONNELS)
    assert ADMIN in contenu
    assert DECONNEXION in contenu
    assert '<p class="menu-titre">Cabinet</p>' in contenu
    assert 'class="onglets-bas"' not in contenu


@pytest.mark.parametrize("url", PAGES_GESTION + PAGES_PERSONNELLES)
def test_principale(client, principale, connecter, url):
    connecter(client, principale)
    contenu = _page(client, url)
    assert all(lien in contenu for lien in liens_attendus(url))
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
    assert not any(lien in contenu for lien in liens_attendus(url))
    assert 'href="/personnes/"' not in contenu
    assert ADMIN not in contenu
    assert DECONNEXION in contenu
    assert 'class="onglets-bas"' in contenu


# --- Page courante -----------------------------------------------------------


def test_page_courante(client, principale, connecter):
    connecter(client, principale)
    assert 'href="/absences/" aria-current="page">Absences</a>' in _page(client, "/absences/")
    presences = _page(client, f"/presences/{MOIS}/")
    # Brique 8 (D8.5) : la page porte un mois, l'onglet et le sous-onglet le suivent.
    assert f'href="/presences/{MOIS}/" aria-current="page">Présences &amp; personnes</a>' in presences
    assert f'href="/presences/{MOIS}/" aria-current="page">Présences</a>' in presences
    personnes = _page(client, "/personnes/")
    assert 'href="/presences/" aria-current="page">Présences &amp; personnes</a>' in personnes
    assert 'href="/personnes/" aria-current="page">Personnes</a>' in personnes
    assert 'href="/planning/" aria-current="page"' not in personnes


def test_onglet_bas_courant(client, salariee, connecter):
    connecter(client, salariee)
    contenu = _page(client, f"/mes-jours/{MOIS}/")
    assert 'href="/mes-jours/" aria-current="page">Mes jours</a>' in contenu
    assert 'href="/mes-absences/" aria-current="page"' not in contenu


# --- Page planning : la barre, rien d'autre de la coquille --------------------


def test_page_planning_avec_barre_sans_commun(client, cabinet, connecter):
    """Brique 6d : la barre commune sur la page planning, sans la feuille ni le titre de la coquille."""
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    contenu = _page(client, f"/planning/{MOIS}/")
    assert "planning-data" in contenu
    for marque in (
        'class="barre"',
        '<details class="avatar"',
        "socle/barre.css",
        "socle/favicon.png",
        f'href="/planning/{MOIS}/" aria-current="page"',   # brique 8 : l'onglet suit le mois
        'id="script-avatar"',   # brique 6a-bis : le script de la barre vient avec elle
    ):
        assert marque in contenu, marque
    for marque in ("socle/commun.css", "socle/polices.css", 'class="titre-page"'):
        assert marque not in contenu, marque
    # script-avatar en tête (dans la barre), puis les trois `json_script`, puis moteur.js et page.js.
    assert contenu.count("<script") == 6


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


# --- Brique 8 (D8.5) : les onglets suivent le mois de la page ------------------


@pytest.mark.parametrize(
    ("url", "statut", "attendus"),
    [
        (f"/absences/?mois={MOIS}", 200, liens_attendus(f"/absences/?mois={MOIS}")),
        ("/", 200, LIENS_GESTION),
        # Mois invalide : la vue répond 404, la page 404 garde la barre, sur le mois courant.
        ("/absences/?mois=abcd", 404, LIENS_GESTION),
    ],
)
def test_onglets_suivent_le_mois(client, cabinet, connecter, url, statut, attendus):
    connecter(client, cabinet)
    reponse = client.get(url)
    assert reponse.status_code == statut, url
    contenu = reponse.content.decode()
    assert 'class="onglets"' in contenu
    assert all(lien in contenu for lien in attendus), attendus


# --- Brique 6a-bis (D6a-bis.2) : le script du menu avatar vit avec la barre ------


def test_script_avatar_une_fois_par_page_jamais_anonyme(client, cabinet, connecter):
    """Le `<details class="avatar">` n'est rendu qu'authentifié : son script aussi, une seule fois."""
    assert 'id="script-avatar"' not in _page(client, "/connexion/")
    connecter(client, cabinet)
    assert _page(client, "/").count('id="script-avatar"') == 1


def test_base_html_un_seul_script_apres_details():
    """Garde de source : la coquille porte un seul `<script`, inline, juste après `</details>` — hors du bloc `scripts`."""
    source = Path(get_template("socle/base.html").origin.name).read_text(encoding="utf-8")
    assert source.count("<script") == 1
    assert re.search(r'</details>\s*<script id="script-avatar">', source)
