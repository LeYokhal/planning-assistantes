"""Configuration commune des tests.

Les valeurs posées ici sont réservées aux tests : elles n'ont aucun rapport
avec la production, et aucune adresse réelle n'y figure (domaine example.org).

⚠️ Les fixtures de comptes importent Django et `sesame.utils` DANS LEUR CORPS,
jamais en tête de module (brique 3, décision M). Ce conftest est importé au
démarrage de pytest, avant que pytest-django n'ait configuré Django : un
`from sesame.utils import ...` en tête lève `ImproperlyConfigured` et fait
tomber la session entière avant le premier test.

Les fixtures homonymes de `comptes/tests/test_acces.py` et
`comptes/tests/test_admin.py` restent où elles sont : elles masquent
volontairement celles-ci, et la déduplication s'arrête aux conftest d'app.
"""

import os

# Doit être fait avant l'import des réglages Django par pytest-django.
os.environ.setdefault("DJANGO_SECRET_KEY", "cle-de-test-jetable-sans-valeur")
os.environ["DJANGO_DEBUG"] = "0"
# Fail-closed par défaut : aucun test ne doit pouvoir appeler un vrai webhook.
os.environ["N8N_MAIL_WEBHOOK_URL"] = ""
os.environ["N8N_WEBHOOK_SECRET"] = ""
os.environ["CABINET_EMAIL"] = ""
os.environ["APP_URL"] = "http://testserver"
os.environ["N8N_IMPORT_WEBHOOK_URL"] = ""
os.environ["N8N_API_SECRET"] = ""
os.environ["DOCTOLIB_PRESENCES_URL"] = ""
os.environ["DOCTOLIB_PRESENCES_SECRET"] = ""
# Les lots endpoint tournent en synchrone dans les tests : aucun thread sur la
# base de test.
os.environ["IMPORT_EN_ARRIERE_PLAN"] = "0"
os.environ["N8N_ABSENCE_WEBHOOK_URL"] = ""
os.environ["RETENTION_ABSENCES_JOURS"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def reglages_fail_closed(settings):
    """Force les réglages sensibles, quel que soit le `.env` de la machine.

    Le bloc `os.environ` ci-dessus ne suffit PAS : pytest-django configure
    Django avant d'exécuter le corps de ce conftest, si bien que les réglages
    ont déjà lu l'environnement — et le `.env` local. Sans cette fixture, un
    poste dont le `.env` porte une vraie URL de webhook ferait sortir les tests
    sur le réseau, et les lots endpoint partiraient dans un thread.

    Un test qui a besoin d'une valeur la pose lui-même : la fixture `settings`
    demandée explicitement s'applique après celle-ci.
    """
    settings.N8N_MAIL_WEBHOOK_URL = ""
    settings.N8N_IMPORT_WEBHOOK_URL = ""
    settings.N8N_WEBHOOK_SECRET = ""
    settings.N8N_API_SECRET = ""
    settings.DOCTOLIB_PRESENCES_URL = ""
    settings.DOCTOLIB_PRESENCES_SECRET = ""
    settings.IMPORT_EN_ARRIERE_PLAN = False
    settings.N8N_ABSENCE_WEBHOOK_URL = ""
    settings.RETENTION_ABSENCES_JOURS = ""


@pytest.fixture
def cabinet(db):
    """Compte cabinet : le rôle qui peut tout, y compris importer et apparier."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(email="cabinet@example.org")


@pytest.fixture
def principale(db):
    """Assistante principale : consultation, et décision des absences."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="principale@example.org", role="principale"
    )


@pytest.fixture
def salariee(db):
    """Salariée : son seul espace est celui de ses absences."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="salariee@example.org")


@pytest.fixture
def connecter():
    """Ouvre une session par lien magique (le seul moyen de se connecter)."""
    from sesame.utils import get_query_string

    def _connecter(client, compte):
        return client.get("/connexion/lien/" + get_query_string(compte))

    return _connecter


@pytest.fixture(autouse=True)
def stockage_statique_simple(settings):
    """Neutralise le stockage statique « manifest ».

    En production, WhiteNoise sert les fichiers collectés par collectstatic.
    En test, aucun manifeste n'existe : le stockage par défaut suffit et évite
    une erreur au rendu des pages d'administration.
    """
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
