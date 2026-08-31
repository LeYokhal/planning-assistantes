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
  Les tests utilisent exclusivement le domaine `example.org`, des noms fictifs
  (« DUPONT Alice », « MARTIN Bob »…) et des IP de documentation (RFC 5737,
  `192.0.2.x`). Seule exception assumée par le cadrage : `regles/regles.json`,
  copie conforme de `reference/skill-v1/regles.json`, porte les noms de la
  fiche — déjà versionnés dans ce dépôt.
- ⚠️ **Aucune installation hors du `.venv` du projet.** Pas de `pip install`
  global, pas de `winget`, pas de `npm`.
- ⚠️ Les exports S7 vivent **hors du dépôt** (`_entrees/`, ignoré par git). Ils
  ne sont jamais copiés dans le dépôt, ni affichés, ni ouverts. **Le jeu S7 réel
  ne sert qu'à la recette manuelle depuis le navigateur** : les tests n'utilisent
  que des payloads fictifs, fabriqués par `presences/tests/fabrique.py`.
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
- **Contrôle de rôle** : un seul mécanisme, le décorateur
  `comptes.acces.role_requis(*roles)`. Il redirige un anonyme vers `/connexion/`
  et refuse un rôle absent par un `403` journalisé (`acces_refuse`).
  `is_superuser` ne contourne pas le rôle. Ne pas en écrire un second.
- **Imports de présences** : une ligne `ImportPresences` n'est **jamais modifiée
  après sa fin, ni supprimée** — c'est la preuve de ce qui est entré dans
  l'application. Un import fautif est dépassé par un import plus récent couvrant
  les mêmes jours ; tout recalcul repart du payload brut conservé sur la ligne.
- **Journal d'audit** : passer par `audit.services.journaliser()`. Le champ
  `details` ne contient jamais d'adresse, de jeton ni de secret — l'identité
  est portée par la clé étrangère `qui`. Un garde-fou masque toute valeur
  contenant un `@`.
- **Réponses neutres** : la page `/connexion/` renvoie exactement la même chose
  que l'adresse existe ou non — y compris quand le plafond de débit par adresse
  se déclenche. Ne jamais introduire de différence observable. Seul le plafond
  par IP répond différemment (`429`) : il ne dit rien d'un compte en particulier.
- **Fiche personnel** : elle n'entre que par le JSON à **cinq colonnes**
  (`Name`, `Department`, `Planning`, `Heures hebdomadaire`, `Jours de travail`).
  L'application **refuse le fichier entier** dès qu'une autre colonne apparaît,
  et son message ne cite que des noms de colonnes, jamais une valeur. Un import
  n'écrit que ces colonnes : `email_contact`, `agenda_doctolib`, `couleur`,
  `code` et `actif` ne sont jamais écrasés.
- **`regles/regles.json` est la source des règles** du planning, chargée et
  validée au démarrage (un fichier invalide empêche le démarrage). Elle se
  modifie par PR uniquement. `reference/skill-v1/` en est la référence
  historique et **reste non exécutée**.
- **Limitation de débit** : compteur en base (`socle.CompteurDebit` +
  `socle/debit.py`), jamais le cache Django. `DatabaseCache.incr` hérite de
  `BaseCache.incr`, qui lit puis écrit sans verrou — les incréments se perdent
  sous les deux workers gunicorn — et repousse la durée de vie à chaque appel,
  ce qui transforme une fenêtre fixe en blocage glissant. Ne pas y revenir.
  IP cliente = `X-Real-IP`, réécrit par Railway — prouvé par sonde le
  31/08/2026 (valeurs illisibles injectées dans X-Real-IP et X-Forwarded-For,
  ressorties « publique ») ; `X-Forwarded-For` = [client, edge], son dernier
  élément est un nœud partagé. Le relevé « topologie proxy » (une ligne par
  processus, sans valeur) reste en place : toute dérive s'y lira. Ne pas changer
  d'en-tête sans re-mesurer (recette : 60 × 401 puis 429 au 61e, avec et sans
  en-têtes injectés).
- **Comptes et personnes** : pour un départ, désactiver (`is_active`, `actif`),
  ne pas supprimer ; une suppression est journalisée mais efface l'auteur des
  événements du compte (`qui` en SET_NULL).
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

### Leçons de la brique 1b

- **pytest-django importe les réglages avant d'exécuter le `conftest.py`
  racine** : un bloc `os.environ` dans ce conftest n'atteint jamais `settings`.
  Les réglages sensibles sont forcés par la fixture autouse
  `reglages_fail_closed` ; un test qui a besoin d'une valeur la pose lui-même
  via la fixture `settings`.
- **Deux `patch` imbriqués sur `x.requests.post` et `y.requests.post` visent le
  même module** : un seul bouchon, qui aiguille sur l'URL (voir
  `presences/tests/test_endpoint.py`).
- **`makemigrations --skip-checks`** tant que les `urls.py` d'une nouvelle app
  n'existent pas, puis `--check --dry-run` sans option.
- **Les accents qui comptent pour un motif** (`presences/lecture.py`) sont en
  échappements `\u00e9` et le texte lu est normalisé NFC ; vérifier à l'octet
  près qu'un outil d'édition ne les a pas décodés.

### Leçons de la brique 2

- **Sur l'infrastructure d'un tiers, mesurer avant d'écrire** : les réponses
  officielles Railway sur `X-Forwarded-For` étaient fausses deux fois pour notre
  trafic ; seul le relevé de topologie (classes sans valeur) et la sonde à
  en-têtes illisibles ont établi que `X-Real-IP` est réécrit par Railway. Toute
  rafale de validation : 60 × 401 puis 429 au 61e, avec ET sans en-têtes
  injectés, calée juste après un début de minute (fenêtres fixes alignées sur
  l'horloge).
- **Les commandes `git commit -m` s'écrivent sur une seule ligne** : le shell
  d'exécution est bash, un here-string PowerShell y produit un sujet « @ »
  (incident 2, rattrapé par `--amend` avant push).

## Périmètre

La brique **1a** livre le socle : projet Django, modèles `Personne` / `Compte` /
`EvenementAudit`, connexion par lien magique, journal d'audit, page de santé,
fichiers de déploiement.

La brique **1b** (livrée le 31/08/2026) livre les présences : lecture d'un payload
`consulter_jours_travail` avec invariant de recompte (`presences/lecture.py`),
import par fichier depuis `/presences/importer/` (rôle cabinet), écran
« présences du mois », verrou d'import, API entrante n8n (`n8n/`) et webhooks
sortants `import.termine` / `import.echec`.

Le **chemin endpoint** (`presences/client_doctolib.py`) est câblé mais
**inactif** : il interroge le serveur MCP Doctolib, qui relève de la brique
**0**, non livrée. Tant que `DOCTOLIB_PRESENCES_URL` et
`DOCTOLIB_PRESENCES_SECRET` sont absentes, un tir demandé par n8n échoue
« endpoint inactif » sans aucun appel réseau — c'est voulu. Son contrat sera
réaligné sur celui de la brique 0 le jour où elle existera.

La brique **2** livre les personnes et les règles : import de la fiche
personnel Notion (`personnes/lecture_fiche.py`, `personnes/services.py`),
`regles/regles.json` et son chargeur validant (`regles/chargeur.py`),
appariement des agendas Doctolib aux praticiens avec rapport
(`personnes/appariement.py`, écran `/personnes/appariement/`), création des
comptes des salariées en masse (action d'admin sur `Personne`) et limitation de
débit sur `/connexion/` et sur l'API n8n (`socle/debit.py`).

La paie, la génération du planning et la purge relèvent des briques **3 à 5**
et ne sont pas ici.

`reference/skill-v1/` contient la version 1 du skill de planning, décompressée
telle quelle à titre de référence. Elle n'est **pas** exécutée par
l'application.
