# Planning Assistantes — consignes de travail

Application Django + PostgreSQL pour le planning des assistantes du cabinet
**Espace K Dentaire**. Ce fichier fixe les règles qui valent pour toute
intervention sur ce dépôt.

## Interdits stricts

- ⚠️ **Aucun `git commit`, aucun `git push`** sans un « go » explicite de Yohan.
  Aucune PR, aucun merge : ils sont faits à la main sur GitHub.
- ⚠️ **Aucune commande `railway`** autre que `railway --version` / `railway whoami`.
  Aucune commande sur une base de production.
- ⚠️ **Aucune suppression de fichier** sans demander d'abord.
- ⚠️ **Aucun secret, aucune adresse e-mail réelle, aucune donnée patient** dans
  le code, les tests, les fixtures, les gabarits, les commentaires ou les logs.
  Les tests utilisent exclusivement le domaine `example.org`.
- ⚠️ **Aucune installation hors du `.venv` du projet.** Pas de `pip install`
  global, pas de `winget`, pas de `npm`.
- ⚠️ Les exports S7 vivent **hors du dépôt** (`_entrees/`, ignoré par git). Ils
  ne sont jamais copiés dans le dépôt, ni affichés, ni ouverts.
- ⚠️ Si une vérification préalable échoue : s'arrêter et le dire. Ne pas
  improviser de contournement.

## Commandes

```bash
python -m venv .venv                      # une seule fois
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

| But | Commande |
|---|---|
| Tests | `.venv/Scripts/python.exe -m pytest` |
| Contrôles Django | `.venv/Scripts/python.exe manage.py check` puis `check --deploy` |
| Migrations | `manage.py makemigrations <app>` puis `manage.py migrate` |
| Serveur local | `.venv/Scripts/python.exe manage.py runserver` |

> **gunicorn ne démarre pas sous Windows** (il dépend du module `fcntl`). Il
> n'est utilisé qu'en production, dans l'image Docker. En local, toujours
> `python manage.py runserver`.

## Conventions

- **Nommage en français** pour tout ce qui nous appartient : modèles, champs,
  vues, commandes de gestion, gabarits, tests, fonctions. On garde les noms
  imposés par Django (`is_active`, `is_staff`, `is_superuser`, `last_login`,
  `save_model`, `handle`…).
- **Aucune fonctionnalité propre à PostgreSQL.** Le développement et les tests
  tournent sur SQLite, la production sur Postgres : pas d'`ArrayField`, pas de
  `JSONField` de `django.contrib.postgres`, pas de `select_for_update`, pas de
  recherche plein texte Postgres. Le `JSONField` utilisé est celui de
  `django.db.models`, portable.
- **Pas de mot de passe.** La connexion se fait exclusivement par lien magique
  (django-sesame). `set_unusable_password()` est systématique, et
  `AUTHENTICATION_BACKENDS` ne contient que `sesame.backends.ModelBackend`.
- **Django 5.2 LTS, pas 6.x.** django-sesame 3.2.3 déclare Django 4.2 → 5.2
  seulement ; 5.2 LTS supporte Python 3.14 et reste maintenue jusqu'en avril 2028.
- **Journal d'audit** : passer par `audit.services.journaliser()`. Le champ
  `details` ne contient jamais d'adresse, de jeton ni de secret — l'identité
  est portée par la clé étrangère `qui`. Un garde-fou masque toute valeur
  contenant un `@`.
- **Réponses neutres** : la page `/connexion/` renvoie exactement la même chose
  que l'adresse existe ou non. Ne jamais introduire de différence observable.
- **Pré-déploiement** : une seule commande, `python manage.py pre_deploiement`.
  Voir « Leçons de déploiement Railway » ci-dessous.

## Leçons de déploiement Railway (brique 1a)

Constats de la mise en ligne du 27/08/2026. À relire avant toute intervention
sur le déploiement.

- **Railway n'exécute PAS le `preDeployCommand` dans un shell** : une seule
  commande, jamais de `&&`. Un `&&` n'y est pas interprété — seule la première
  commande tourne, la suivante est perdue en silence, sans erreur dans les logs.
  La commande `socle/pre_deploiement` enchaîne donc `migrate` puis
  `assurer_compte_cabinet` depuis Python.
- **Le builder affiché « RAILPACK » dans le dashboard est ignoré** :
  `railway.json` impose `DOCKERFILE`, et c'est bien le `Dockerfile` qui est
  construit (vérifié dans les logs de build). Ne pas se fier à l'affichage.
- **`ALLOWED_HOSTS` doit contenir `healthcheck.railway.app`** : sans lui, la
  sonde de santé reçoit un `400` et le déploiement est déclaré en échec, alors
  que l'application tourne.
- **gunicorn ne démarre pas sous Windows** : en local, `runserver` uniquement.
  gunicorn ne sert qu'en production, dans l'image Docker.

## Périmètre

La brique **1a** livre le socle : projet Django, modèles `Personne` / `Compte` /
`EvenementAudit`, connexion par lien magique, journal d'audit, page de santé,
fichiers de déploiement. L'import S7 et l'écran « présences du mois » relèvent
de la brique **1b** et ne sont pas ici.

`reference/skill-v1/` contient la version 1 du skill de planning, décompressée
telle quelle à titre de référence. Elle n'est **pas** exécutée par
l'application.
