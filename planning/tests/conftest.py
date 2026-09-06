"""Fixtures des tests du planning.

Les vues appellent `donnees.construire(mois)` sans argument, donc les règles du
dépôt (noms de la fiche réelle). Sur le jeu fictif, aucun nom ne se résout : ni
binôme, ni exclusive. La fixture ci-dessous, automatique, substitue les règles
fictives de `fabrique.REGLES_BRUTES` pour toute la durée d'un test : les tests
de vue et d'API voient les mêmes règles que `test_donnees`.
"""

import pytest

from planning import donnees
from planning.tests import fabrique


@pytest.fixture(autouse=True)
def regles_fictives(monkeypatch):
    regles = fabrique.regles()
    monkeypatch.setattr(donnees, "charger", lambda: regles)
    return regles
