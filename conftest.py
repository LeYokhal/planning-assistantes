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

import pytest  # noqa: E402


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
