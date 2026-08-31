"""Configuration commune des tests.

Les valeurs posées ici sont réservées aux tests : elles n'ont aucun rapport
avec la production, et aucune adresse réelle n'y figure (domaine example.org).
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
