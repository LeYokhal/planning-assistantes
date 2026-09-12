"""Habillage de l'administration (brique 6a, C6.4) : titres, index en cinq blocs, zéro vue réécrite."""

import pytest
from django.utils.html import escape

pytestmark = pytest.mark.django_db

BLOCS = ("Comptes et personnes", "Absences", "Planning", "Présences", "Journal d'audit")


def test_index(client, cabinet, connecter):
    connecter(client, cabinet)
    reponse = client.get("/admin/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert "Espace K Dentaire · Administration" in contenu
    assert "← Retour à l'app" in contenu
    positions = [contenu.index(f">{escape(titre)}</a></h2>") for titre in BLOCS]
    assert positions == sorted(positions)
    assert 'href="/admin/absences/absencesalariee/importer/">Importer un fichier</a>' in contenu
    # Brique 6a-bis (D6a-bis.1) : « Ajouter » en pilule, une rangée par modèle rendu.
    assert contenu.count('class="ajout"') == 4
    assert contenu.count('class="rangee"') == 8
    assert 'href="/admin/absences/absencesalariee/add/">Ajouter</a>' in contenu
    assert 'id="recent-actions-module"' in contenu
    assert "Administration de Django" not in contenu
    assert "/admin/auth/group/" not in contenu
    assert "nav_sidebar" not in contenu and 'id="nav-sidebar"' not in contenu
    assert "theme-toggle" not in contenu and "dark_mode.css" not in contenu
    assert "socle/administration.css" in contenu and "socle/favicon.png" in contenu
    assert "<title>Administration | Administration · Espace K Dentaire</title>" in contenu


def test_liste_habillee(client, cabinet, connecter):
    connecter(client, cabinet)
    reponse = client.get("/admin/comptes/personne/")
    assert reponse.status_code == 200
    assert "Espace K Dentaire · Administration" in reponse.content.decode()


def test_groupes_toujours_servis(client, cabinet, connecter):
    """Masqué de l'index (H-2), jamais retiré : l'admin reste fonctionnellement identique."""
    connecter(client, cabinet)
    assert client.get("/admin/auth/group/").status_code == 200
