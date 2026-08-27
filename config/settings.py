"""Réglages Django du projet Planning Assistantes (Espace K Dentaire).

Tous les réglages sensibles proviennent de l'environnement. En développement,
un fichier `.env` local (jamais versionné) est chargé automatiquement.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Charge un .env local s'il existe. En production (Railway), il n'y en a pas :
# les variables sont fournies par la plateforme.
load_dotenv(BASE_DIR / ".env")


def _env_bool(nom, defaut=False):
    """Lit une variable d'environnement booléenne. Absente = valeur par défaut."""
    brut = os.environ.get(nom)
    if brut is None or brut.strip() == "":
        return defaut
    return brut.strip().lower() in {"1", "true", "vrai", "yes", "oui", "on"}


def _env_liste(nom, defaut=()):
    """Lit une variable d'environnement en liste séparée par des virgules."""
    brut = os.environ.get(nom, "")
    valeurs = [v.strip() for v in brut.split(",") if v.strip()]
    return valeurs or list(defaut)


# --- Sécurité de base -------------------------------------------------------

try:
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
except KeyError:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY est absente de l'environnement : "
        "l'application refuse de démarrer sans clé secrète."
    ) from None

DEBUG = _env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = _env_liste("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = _env_liste(
    "CSRF_TRUSTED_ORIGINS",
    ["http://localhost:8000", "http://127.0.0.1:8000"],
)

# Railway termine TLS devant l'application : la requête arrive en HTTP interne.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# Laisser à False : la redirection HTTPS est assurée par Railway. La mettre à
# True provoque une boucle de redirection derrière son proxy.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0 if DEBUG else 3600  # volontairement court en 1a ; à porter à 31536000 après validation Phase 5
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "comptes",
    "audit",
    "socle",
    "presences",
    "n8n",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise doit suivre immédiatement SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Base de données --------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification -------------------------------------------------------

AUTH_USER_MODEL = "comptes.Compte"

# Seul backend : la connexion se fait exclusivement par lien magique.
# Aucun mot de passe n'est saisi ni vérifié nulle part dans l'application.
AUTHENTICATION_BACKENDS = ["sesame.backends.ModelBackend"]

# Aucun validateur : il n'y a pas de mot de passe utilisable.
AUTH_PASSWORD_VALIDATORS = []

# django-sesame : lien valable 15 minutes, à usage unique.
SESAME_MAX_AGE = 900
SESAME_ONE_TIME = True
SESAME_INVALIDATE_ON_EMAIL_CHANGE = True

LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/connexion/"

# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques -----------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- Journalisation ---------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{asctime} {name} {levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# --- Réglages propres à l'application ---------------------------------------

# Adresse publique utilisée pour construire les liens de connexion.
APP_URL = os.environ.get("APP_URL", "http://localhost:8000").rstrip("/")

# Webhook n8n chargé de l'envoi des mails (voir docs/n8n/MAIL_SORTANT.md).
# Absents = aucun envoi (fail-closed), l'utilisateur voit malgré tout la
# réponse neutre.
N8N_MAIL_WEBHOOK_URL = os.environ.get("N8N_MAIL_WEBHOOK_URL", "").strip()
N8N_WEBHOOK_SECRET = os.environ.get("N8N_WEBHOOK_SECRET", "").strip()

# Adresse du compte « cabinet » assuré au pré-déploiement.
CABINET_EMAIL = os.environ.get("CABINET_EMAIL", "").strip()

# --- Présences (brique 1b) --------------------------------------------------

# Endpoint « présences » du serveur MCP Doctolib (brique 0, NON LIVRÉE). Absents
# = chemin endpoint inactif : un tir demandé par n8n aboutit en échec
# « endpoint inactif », sans aucun appel réseau.
DOCTOLIB_PRESENCES_URL = os.environ.get("DOCTOLIB_PRESENCES_URL", "").strip()
DOCTOLIB_PRESENCES_SECRET = os.environ.get("DOCTOLIB_PRESENCES_SECRET", "").strip()

# Webhook n8n destinataire des événements import.termine / import.echec
# (voir docs/n8n/IMPORT_PRESENCES.md). Absent = aucune notification
# (fail-closed). Le secret est N8N_WEBHOOK_SECRET, en-tête X-Webhook-Secret.
N8N_IMPORT_WEBHOOK_URL = os.environ.get("N8N_IMPORT_WEBHOOK_URL", "").strip()

# Secret de l'API entrante n8n -> application (en-tête X-Api-Secret).
# Absent = API désactivée (503), sans exception.
N8N_API_SECRET = os.environ.get("N8N_API_SECRET", "").strip()

# Tirs endpoint en tâche de fond (thread). 0 = synchrone, réservé aux tests.
IMPORT_EN_ARRIERE_PLAN = _env_bool("IMPORT_EN_ARRIERE_PLAN", True)

# Péremption du verrou d'import et des lignes « en cours », en minutes.
VERROU_IMPORT_PEREMPTION_MINUTES = 15
