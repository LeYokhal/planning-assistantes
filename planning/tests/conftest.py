"""Fixtures des tests du planning.

Les vues appellent `donnees.construire(mois)` sans argument, donc les règles du
dépôt (noms de la fiche réelle). Sur le jeu fictif, aucun nom ne se résout : ni
binôme, ni exclusive. La fixture ci-dessous, automatique, substitue les règles
fictives de `fabrique.REGLES_BRUTES` pour toute la durée d'un test : les tests
de vue et d'API voient les mêmes règles que `test_donnees`.

Brique 7b : `views.planning_historique` charge les règles pour son compte (jours
d'ouverture, praticiens à part, palette) sans passer par `donnees` — la fixture
substitue donc les deux, sinon la page de lecture lirait le fichier du dépôt là
où tout le reste du test voit le jeu fictif.
"""

import pytest

from planning import donnees, views
from planning.tests import fabrique


@pytest.fixture(autouse=True)
def regles_fictives(monkeypatch):
    regles = fabrique.regles()
    monkeypatch.setattr(donnees, "charger", lambda: regles)
    monkeypatch.setattr(views, "charger", lambda: regles)
    return regles
