"""Recette de la copie HTML autonome."""

import pytest

from planning import services
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = f"/planning/{fabrique.MOIS}/copie/"


def test_404_sans_version(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    assert client.get(URL).status_code == 404


def test_copie_de_la_derniere_version(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat(), cabinet)
    services.enregistrer(fabrique.MOIS, 1, fabrique.etat_propre(), cabinet)
    connecter(client, cabinet)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert reponse["Content-Type"].startswith("text/html")
    assert reponse["Content-Disposition"] == f'attachment; filename="planning-assistantes_{fabrique.MOIS}_v2.html"'
    assert contenu.startswith("<!doctype html>")
    assert '<html lang="fr" class="planning">' in contenu
    assert '<body class="planning autonome">' in contenu
    for bloc in ("planning-data", "planning-state", "planning-meta"):
        assert f'<script id="{bloc}" type="application/json">' in contenu
    assert '"numero": 2' in contenu and '"autonome": true' in contenu
    assert "emma_ber" in contenu and "sara_pet" in contenu   # le state de la version 2
    # Scripts et styles inlinés, aucun lien vers l'application.
    assert "PlanningMoteur.creer" in contenu and "function creer(DATA, state)" in contenu
    assert "Satoshi" in contenu
    assert "/static/" not in contenu
    assert 'href="/' not in contenu and "{% url" not in contenu
    # Brique 6d : l'enveloppe est dans la copie (neuf boutons, menu « Plus », bandeau,
    # date des données), la coquille et les mois voisins n'y sont pas.
    for id_ in (
        "btnPropose", "btnUndo", "btnImport", "btnExport", "btnPrint", "btnReset",
        "btnCopie", "btnSave", "btnPublier",
    ):
        assert f'id="{id_}"' in contenu, id_
    assert '<details class="plus">' in contenu
    assert "Le planning se travaille sur un écran large" in contenu
    assert 'class="barre"' not in contenu and 'class="mois"' not in contenu
    assert '"donnees_du": "' in contenu


def test_aucune_sequence_de_fermeture_dans_les_scripts_inlines(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    connecter(client, cabinet)
    contenu = client.get(URL).content.decode()

    # Cinq scripts (trois blocs JSON, moteur, page), cinq fermetures et pas
    # une de plus : rien dans les scripts inlinés ne referme la balise plus
    # tôt. (`page.js` cite « <script id="planning-state" » dans une regex, ce
    # qui est inoffensif ; seule la séquence de fermeture compte.)
    assert contenu.count('type="application/json"') == 3
    assert contenu.count("<script>") == 2
    assert contenu.count("</script>") == 5
    assert contenu.count("<style>") == contenu.count("</style>") == 1


def test_principale_peut_copier(client, principale, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    connecter(client, principale)
    assert client.get(URL).status_code == 200


def test_mois_invalide(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.get("/planning/2026-13/copie/").status_code == 404
