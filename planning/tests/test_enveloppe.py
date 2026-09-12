"""Enveloppe de la page planning (brique 6d).

Barre commune par rôle, menu « Plus », pastille « Données Doctolib du … »,
bandeau « écran large », alertes reformulées par rôle, registre de `page.js`,
`_corps.html` sans lien vers l'application (il sert aussi à la copie autonome).
Noms fictifs de `planning/tests/fabrique.py` uniquement.
"""

import json
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.utils import timezone

from planning import services
from planning.tests import fabrique
from presences.models import ImportPresences

pytestmark = pytest.mark.django_db

URL = f"/planning/{fabrique.MOIS}/"
URL_COPIE = f"/planning/{fabrique.MOIS}/copie/"
LIENS_PERSONNELS = ('href="/mes-jours/"', 'href="/mes-absences/"', 'href="/mon-profil/"')
ADMIN = 'href="/admin/"'
ONGLET_COURANT = f'href="/planning/{fabrique.MOIS}/" aria-current="page"'   # brique 8 : l'onglet suit le mois
# Les six boutons rangés dans « Plus », dans l'ordre du dossier ; les trois qui restent au premier plan.
IDS_PLUS = ("btnPropose", "btnExport", "btnImport", "btnCopie", "btnPrint", "btnReset")
IDS_BARRE = ("btnUndo", "btnSave", "btnPublier")
BANDEAU = "Le planning se travaille sur un écran large"
COLLISION = "code en collision"
SAISIR = "à saisir dans l'administration"
SIGNALER = "à signaler au cabinet"


def _page(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 200, url
    return reponse.content.decode()


def _bloc(contenu, nom):
    """Le JSON d'un `json_script` de la copie (les accents y sont échappés : on le lit, on ne le cherche pas)."""
    motif = rf'<script id="{nom}" type="application/json">(.*?)</script>'
    return json.loads(re.search(motif, contenu, re.S).group(1))


def _jeu_enregistre(cabinet):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)


# --- 1. La barre par rôle ---------------------------------------------------------


def test_barre_du_cabinet(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    contenu = _page(client, URL)
    assert ADMIN in contenu
    assert ONGLET_COURANT in contenu
    assert not any(lien in contenu for lien in LIENS_PERSONNELS)


def test_barre_de_la_principale(client, principale, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, principale)
    contenu = _page(client, URL)
    assert all(lien in contenu for lien in LIENS_PERSONNELS)
    assert ADMIN not in contenu
    assert ONGLET_COURANT in contenu


# --- 2. Le menu « Plus » ------------------------------------------------------------


def test_menu_plus_six_boutons_dans_l_ordre(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    contenu = _page(client, URL)
    debut = contenu.index('<details class="plus">')
    menu = contenu[debut : contenu.index("</details>", debut)]
    positions = [menu.index(f'id="{id_}"') for id_ in IDS_PLUS]
    assert positions == sorted(positions)
    for id_ in IDS_BARRE:
        assert f'id="{id_}"' in contenu and f'id="{id_}"' not in menu, id_
    for libelle in (
        "Exporter (JSON)",
        "Importer un planning (HTML ou JSON)",
        "Télécharger une copie",
        "Refaire la proposition",
    ):
        assert libelle in menu, libelle


# --- 3. « Données Doctolib du … » -----------------------------------------------------


def test_donnees_du_page_et_copie(client, cabinet, connecter):
    _jeu_enregistre(cabinet)
    connecter(client, cabinet)
    meta = client.get(URL).context["meta"]
    dernier = max(import_.importe_le for import_ in ImportPresences.objects.all())
    attendu = timezone.localdate(dernier).isoformat()
    assert meta["donnees_du"] == attendu
    assert set(meta["urls"]) == {"versions", "erreurs", "copie", "publier"}
    copie = _bloc(_page(client, URL_COPIE), "planning-meta")
    assert copie["donnees_du"] == attendu and copie["autonome"] is True


# --- 4. Bandeau « écran large » -----------------------------------------------------


def test_bandeau_ecran_large_page_et_copie(client, cabinet, connecter):
    _jeu_enregistre(cabinet)
    connecter(client, cabinet)
    assert BANDEAU in _page(client, URL)
    assert BANDEAU in _page(client, URL_COPIE)


# --- 5. Alertes selon le rôle (E4) ------------------------------------------------------


def test_alerte_de_collision_selon_le_role(client, cabinet, principale, connecter):
    _jeu_enregistre(cabinet)
    # Même prénom, mêmes trois lettres de nom que « BERNARD Emma » : `code_pour`
    # entre en collision et `Personne.save` laisse `code` nul.
    doublon = fabrique.salariee("BERTIN", "Emma", 39, "gray")
    assert doublon.code is None

    connecter(client, cabinet)
    alertes_cabinet = client.get(URL).context["data"]["meta"]["alertes"]
    assert any(COLLISION in a and SAISIR in a for a in alertes_cabinet)
    assert not any(SIGNALER in a for a in alertes_cabinet)
    copie_cabinet = _bloc(_page(client, URL_COPIE), "planning-data")["meta"]["alertes"]
    assert any(SAISIR in a for a in copie_cabinet) and not any(SIGNALER in a for a in copie_cabinet)
    client.logout()

    connecter(client, principale)
    alertes_principale = client.get(URL).context["data"]["meta"]["alertes"]
    assert any(COLLISION in a and SIGNALER in a for a in alertes_principale)
    assert not any(SAISIR in a for a in alertes_principale)
    sans_collision = [a for a in alertes_principale if COLLISION not in a]
    assert sans_collision == [a for a in alertes_cabinet if COLLISION not in a]
    copie_principale = _bloc(_page(client, URL_COPIE), "planning-data")["meta"]["alertes"]
    assert any(SIGNALER in a for a in copie_principale) and not any(SAISIR in a for a in copie_principale)


# --- 6. Registre de `page.js` (C6.11) ---------------------------------------------------

TUTOIEMENTS = (
    "reprends-la",
    "Utilise +",
    "clique ",
    "clique-la",
    "déplace-la",
    "déplace ou retire",
    "Corrige puis",
    "exporte ton",
    "recharge la page",
    "ton enregistrement",
    "Exporter JSON",
)


def test_page_js_vouvoie():
    source = Path(finders.find("planning/page.js")).read_text(encoding="utf-8")
    for tutoiement in TUTOIEMENTS:
        assert tutoiement not in source, tutoiement


# --- 7. `_corps.html` : partagé avec la copie, sans lien vers l'application -----------------


def test_corps_sans_lien_vers_l_application():
    source = Path(get_template("planning/_corps.html").origin.name).read_text(encoding="utf-8")
    for interdit in ("{% url", 'href="/', "/static/"):
        assert interdit not in source, interdit
    assert source.count("{% if nav_mois %}") == 2


# --- 8. Brique 8 : en-tête allégé (D8.2 → D8.4) et gardes de source -------------------


def _source(chemin):
    return Path(finders.find(chemin)).read_text(encoding="utf-8")


def test_entete_sans_selecteur_ni_pastille_donnees(client, cabinet, connecter):
    """D8.3 et D8.4 : plus de pastille « Données Doctolib du … » ni de sélecteur « Planning individuel »."""
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    contenu = _page(client, URL)
    assert 'id="filtre"' not in contenu and 'id="donnees"' not in contenu
    assert 'id="version"' in contenu


def test_sous_titre_et_pastille_de_version():
    """D8.3 : la date des données remplace « Généré le … » ; D8.2 : `hidden` doit battre `display:inline-block`."""
    page_js = _source("planning/page.js")
    assert "Données Doctolib du" in page_js and "Généré le" not in page_js
    assert ".version[hidden]" in _source("planning/styles.css")


def test_filtre_multiple_sans_comparaison_simple():
    """D8.6 : `FILTER` porte des listes ; aucune comparaison à un identifiant seul ne doit subsister."""
    page_js = _source("planning/page.js")
    for interdit in ("FILTER.s !==", "FILTER.p !==", "FILTER?.s ===", "FILTER?.p ==="):
        assert interdit not in page_js, interdit


def test_lignes_de_role_pictogrammes_et_repli():
    """D8.7 : pictogrammes avec libellé accessible ; D8.8 : repli mémorisé dans le navigateur, jamais dans `STATE`."""
    page_js = _source("planning/page.js")
    for attendu in ("aria-label", "Secrétariat", "Administratif", "Sureffectif", "Absent", "localStorage"):
        assert attendu in page_js, attendu


def test_semaines_sommaire_et_fleches():
    """D8.9 → D8.13 : flèches ← →, défilement vers une semaine, jour actuel calculé côté client."""
    page_js = _source("planning/page.js")
    for attendu in ("ArrowLeft", "scrollIntoView", "AUJOURDHUI"):
        assert attendu in page_js, attendu
