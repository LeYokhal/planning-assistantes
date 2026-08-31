"""Fixtures communes aux tests des personnes.

Aucune adresse réelle : domaine `example.org` uniquement.
"""

import pytest
from django.contrib.auth import get_user_model
from sesame.utils import get_query_string


@pytest.fixture
def cabinet(db):
    """Compte cabinet : le seul à pouvoir importer et apparier."""
    return get_user_model().objects.create_superuser(email="cabinet@example.org")


@pytest.fixture
def principale(db):
    """Assistante principale : consultation seule."""
    return get_user_model().objects.create_user(
        email="principale@example.org", role="principale"
    )


@pytest.fixture
def salariee(db):
    """Salariée : aucun accès aux écrans des personnes."""
    return get_user_model().objects.create_user(email="salariee@example.org")


@pytest.fixture
def connecter():
    """Ouvre une session par lien magique (le seul moyen de se connecter)."""

    def _connecter(client, compte):
        return client.get("/connexion/lien/" + get_query_string(compte))

    return _connecter
