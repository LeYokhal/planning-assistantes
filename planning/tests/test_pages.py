"""Recette des pages : accès, blocs de base, écran sans import, non-régression."""

import re

import pytest
from django.utils import timezone

from planning import services
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = f"/planning/{fabrique.MOIS}/"

# `socle/base.html` tel qu'il était avant la brique 4a. Les blocs ajoutés
# doivent rendre exactement ce texte pour les pages qui ne les utilisent pas.
ANCIEN_BASE = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titre %}Planning Assistantes{% endblock %}</title>
  <style>
    :root { color-scheme: light dark; }
    body {
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      max-width: 40rem; margin: 3rem auto; padding: 0 1.25rem; line-height: 1.55;
    }
    /* Les écrans à tableaux (présences) ont besoin de toute la largeur. */
    body.large { max-width: 90rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    .sous-titre { color: #666; margin-top: 0; }
    form p { margin: 0.75rem 0; }
    label { display: block; font-weight: 600; margin-bottom: 0.25rem; }
    input[type="email"] { width: 100%; padding: 0.5rem; font-size: 1rem; box-sizing: border-box; }
    button { padding: 0.55rem 1.1rem; font-size: 1rem; cursor: pointer; }
    .message { border-left: 3px solid #4a7; padding: 0.75rem 1rem; background: rgba(68,170,119,.08); }
    .messages { list-style: none; padding: 0; margin: 0 0 1.5rem; }
    .messages li { border-left: 3px solid #4a7; padding: 0.75rem 1rem; margin-bottom: 0.5rem; background: rgba(68,170,119,.08); }
    .messages li.info { border-left-color: #1764D8; background: rgba(23,100,216,.08); }
    .messages li.error { border-left-color: #c33; background: rgba(204,51,51,.08); }
    nav { margin-top: 2.5rem; font-size: 0.9rem; }
  </style>
  {% block tete %}{% endblock %}
</head>
<body class="{% block classe_corps %}{% endblock %}">
  <header>
    <h1>{% block entete %}Planning Assistantes{% endblock %}</h1>
    <p class="sous-titre">Espace K Dentaire</p>
  </header>
  <main>
    {% if messages %}
      <ul class="messages">
        {% for message in messages %}<li class="{{ message.tags }}">{{ message }}</li>{% endfor %}
      </ul>
    {% endif %}
    {% block contenu %}{% endblock %}
  </main>
  <nav>{% block navigation %}{% endblock %}</nav>
</body>
</html>
"""


def sans_jeton(html):
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken" value="X"', html)


# --- Accès ----------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/planning/", URL, f"/planning/{fabrique.MOIS}/copie/"])
def test_anonyme_redirige_vers_la_connexion(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 302
    assert reponse.url == f"/connexion/?next={url}"


@pytest.mark.parametrize("url", ["/planning/", URL, f"/planning/{fabrique.MOIS}/copie/"])
def test_salariee_refusee(client, salariee, connecter, url):
    connecter(client, salariee)
    assert client.get(url).status_code == 403


def test_racine_redirige_vers_le_mois_courant(client, principale, connecter):
    connecter(client, principale)
    reponse = client.get("/planning/")
    assert reponse.status_code == 302
    assert reponse.url == f"/planning/{timezone.localdate():%Y-%m}/"


def test_mois_invalide_introuvable(client, principale, connecter):
    connecter(client, principale)
    assert client.get("/planning/2026-13/").status_code == 404


# --- Sans import ------------------------------------------------------------------


def test_sans_import_ecran_dedie(client, cabinet, connecter):
    fabrique.personnes()
    connecter(client, cabinet)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert "Aucun import de présences réussi" in contenu
    assert "planning-data" not in contenu
    assert "/presences/importer/" in contenu       # rôle cabinet
    assert "sous-titre" in contenu                  # page ordinaire, blocs de base conservés


def test_sans_import_principale_sans_lien_d_import(client, principale, connecter):
    connecter(client, principale)
    contenu = client.get(URL).content.decode()
    assert "/presences/importer/" not in contenu
    assert f"/presences/{fabrique.MOIS}/" in contenu


# --- La page --------------------------------------------------------------------


def test_page_servie(client, principale, connecter, cabinet):
    fabrique.jeu_complet(cabinet)
    connecter(client, principale)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert '<html lang="fr" class="planning">' in contenu
    assert 'class="planning"' in contenu
    for bloc in ("planning-data", "planning-state", "planning-meta"):
        assert f'<script id="{bloc}" type="application/json">' in contenu
    assert "planning/moteur.js" in contenu and "planning/page.js" in contenu
    assert "planning/styles.css" in contenu
    # Blocs de base vidés : ni sous-titre, ni feuille de style de base.
    assert "sous-titre" not in contenu
    assert "max-width: 40rem" not in contenu
    assert "Espace K Dentaire" not in contenu
    # Navigation propre à la page.
    assert f"/presences/{fabrique.MOIS}/" in contenu and "/absences/" in contenu


def test_page_pose_le_cookie_csrftoken(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    reponse = client.get(URL)
    assert "csrftoken" in reponse.cookies
    assert 'name="csrfmiddlewaretoken"' in reponse.content.decode()


def test_meta_numero_zero_sans_version_puis_un(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    meta = client.get(URL).context["meta"]
    assert meta["numero"] == 0 and meta["autonome"] is False
    assert set(meta["urls"]) == {"versions", "erreurs", "copie"}
    assert meta["urls"]["versions"] == f"/api/planning/{fabrique.MOIS}/versions/"

    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    reponse = client.get(URL)
    assert reponse.context["meta"]["numero"] == 1
    assert reponse.context["state"] == fabrique.etat_propre()


def test_data_de_la_page_porte_le_libelle_du_type_pour_les_roles_admis(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    data = client.get(URL).context["data"]
    assert any(c["type"] == "Congé payé" for c in data["conges"])


# --- Accueil et non-régression ------------------------------------------------


def test_entree_planning_dans_l_accueil(client, cabinet, salariee, connecter):
    connecter(client, cabinet)
    assert 'href="/planning/"' in client.get("/").content.decode()
    client.logout()
    connecter(client, salariee)
    assert 'href="/planning/"' not in client.get("/").content.decode()


@pytest.mark.parametrize("url", ["/", "/mes-absences/"])
def test_base_inchangee_pour_les_autres_pages(client, salariee, connecter, settings, url):
    """Les blocs ajoutés à base.html rendent, vides, exactement l'ancien texte."""
    connecter(client, salariee)
    apres = sans_jeton(client.get(url).content.decode())

    settings.TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
                "loaders": [
                    ("django.template.loaders.locmem.Loader", {"socle/base.html": ANCIEN_BASE}),
                    "django.template.loaders.app_directories.Loader",
                ],
            },
        }
    ]
    avant = sans_jeton(client.get(url).content.decode())

    assert avant == apres
