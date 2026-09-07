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
  repris de `reference/skill-v1/regles.json` et augmenté des sections
  `periodes_ouverture` (brique 3) et `palette` (brique 4a), porte les noms de
  la fiche — déjà versionnés dans ce dépôt.
- ⚠️ **Aucune installation hors du `.venv` du projet.** Pas de `pip install`
  global, pas de `winget`, pas de `npm`. Les tests du moteur JS tournent avec
  le module intégré `node:test` (`node --test`), sans `package.json`.
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
| Tests | `.venv/Scripts/python.exe -m pytest` (lance aussi les tests Node par `planning/tests/test_node.py`) |
| Tests du moteur JS seuls | `node --test "planning/tests_js/**/*.test.js"` |
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
  modifie par PR uniquement. Le fichier reprend `reference/skill-v1/regles.json`
  augmenté de `periodes_ouverture` (brique 3) et de `palette` (brique 4a).
  `reference/skill-v1/` est la référence historique du skill : **non exécutée**,
  et **hors de l'image Docker** (`.dockerignore`). Ses pièces utiles ont été
  portées dans l'application (`comptes/noms.py`, `socle/feries.py`,
  `presences/fenetres.py`, `presences/lecture.py`, `personnes/appariement.py`,
  `planning/`) ; on ne l'importe jamais.
- **Planning (brique 4a)** : `DATA` est calculé côté serveur
  (`planning/donnees.py`), le `STATE` enregistré n'a que quatre clés
  (`affectations`, `feries`, `feries_off`, `notes`), et la proposition ne
  dépend que du numéro de version servi (`numero === 0`), jamais d'un drapeau
  de l'état. Le moteur `planning/static/planning/moteur.js` ne touche pas au
  DOM : fabrique `creer(DATA, state)`, état muté en place, **aucune fonction du
  moteur n'appelle `commit`, `render`, `toast` ni `confirm`** ; `page.js`
  enchaîne `M.x(); commit();`. Les règles strictes existent en double
  (`planning/verification.py` et `verifier()` du moteur), avec les mêmes codes,
  sur le même jeu de cas `planning/tests/cas_verification.json` : un code
  nouveau s'ajoute des deux côtés et dans le jeu. Une violation ne porte que
  `code`, `date`, `slot`, `s`. Le numéro de version est attribué par la
  contrainte unique `(mois, numero)`, l'`IntegrityError` attrapée **hors** du
  `with transaction.atomic()`. **4b** : la publication pose les champs de
  publication sur la dernière version par un seul `UPDATE … WHERE NOT publiee
  AND NOT EXISTS (numéro supérieur)`, après revérification sur `DATA`
  recalculé — ni `select_for_update`, ni transaction ; la version publiée du
  mois est la dernière `publiee=True` par `numero`, sans dépublication ;
  « Mes jours » lit le `state` publié et les personnes, **jamais `DATA`** ; le
  conflit absence ↔ planning publié est calculé à la demande, signalé, jamais
  stocké ni bloquant, sur la transition vers l'état effectif seulement. Voir
  `docs/PLANNING.md` (§ 11 et § 12).
- **Cycle d'import `absences` ↔ `planning` (brique 4b)** : `planning.donnees`
  importe `absences.services`, donc `absences/` (`services.signaler_conflits`,
  `views.absences_a_decider`) importe `planning.conflits` **dans la fonction**,
  jamais en tête de module (patron `presences/verrou.py`) ; et
  `planning/webhooks.py` n'importe jamais `planning.services` (c'est `services`
  qui l'importe, le comptage lui est passé). Un cycle réintroduit se voit au
  premier `import` : ne pas le « corriger » en remontant l'import en tête.
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
- **Absences : donnée de santé.** Le TYPE d'absence (« Maladie ») et la
  PRÉCISION saisie par la salariée ne sortent jamais de la base : ni dans
  `details` d'audit, ni dans les logs, ni dans un webhook, ni dans l'endpoint de
  paie. Le garde-fou « @ » ne les reconnaît pas — c'est tenu à la main, et prouvé
  par `absences/tests/test_confidentialite.py`. Relancer ces tests après toute
  évolution de la brique. Exception décidée en brique 4a (amendement C4.1) :
  `DATA.conges[].type` porte le libellé pour les rôles `cabinet` et
  `principale`, à l'écran et dans la copie HTML, et nulle part ailleurs — ni
  `state`, ni version, ni export JSON, ni audit, ni logs ; toute la mise en
  forme passe par `planning.donnees.libelle_conge()`. Prouvé par
  `planning/tests/test_confidentialite.py` (sept surfaces). **4b** : l'audit
  `absence_conflit_publication` et le webhook `absence.conflit` ne portent que
  `personne_id`, `mois`, `numero`, `dates` ; « Mes jours » ne reçoit pas
  `DATA`. Prouvé par `test_conflits`, `test_mes_jours` et les trois tests 4b
  de `planning/tests/test_confidentialite.py`. **3-quater** : `absence_importee`
  et `import_absences` ne portent que `personne_id`, `statut`, `jours_comptes`
  (chaîne), `ref` (identifiants Notion opaques), compteurs et empreinte ; prouvé
  par les deux tests 3-quater de `absences/tests/test_confidentialite.py`.
- **Jours comptés** : `min(J, max(0, B − F))` par semaine, où `J` exclut les
  fériés et `F` ne compte que les fériés tombant un jour d'OUVERTURE. Un férié
  un jour fermé (lundi de Pentecôte sous le régime mardi→samedi) ne retire
  aucune brique : la revue de Phase 2 a rattrapé l'erreur inverse, qui coûtait un
  jour de paie à la salariée. Les périodes d'ouverture sont datées dans
  `regles.json`, la bascule est calée sur un lundi.
- **Client n8n sortant** : un seul, `socle/client_n8n.py`. ⚠️ `comptes/mails.py`
  et `presences/webhooks.py` **conservent leur `import requests`** bien qu'ils ne
  l'utilisent plus directement : douze tests patchent `<module>.requests.post` et
  tomberaient en `AttributeError` sans lui. Le patch reste efficace parce que les
  trois modules partagent le module `requests`.
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

### Leçons de la brique 4a

- **`pytest -q` cache le résumé** : `pytest.ini` porte déjà `-q`, un second
  `-q` donne `-qq` et la ligne « N passed » disparaît. Lancer `pytest` nu pour
  lire le compte.
- **`json_script` échappe les accents** (`Congé`) : un test qui cherche
  un libellé dans une page doit décoder le bloc JSON, pas chercher la chaîne
  en clair.
- **Le gabarit d'origine ne tourne pas sous Node** : la proposition de
  référence du moteur est figée depuis un navigateur, une fois, sans rien
  déplacer (procédure dans `docs/PLANNING.md`). Un moteur comparé à lui-même
  ne prouve rien.
- **Deux implémentations d'une même règle divergent en silence** : elles ne
  restent alignées que par un jeu de cas commun lu tel quel des deux côtés,
  qui exige de plus que chaque code soit émis au moins une fois.

### Leçons de la brique 4b

- **Une revue technique par version de plan, contre le code réel, jusqu'à ce
  qu'elle ne trouve plus rien.** La v2 du diff plan corrigeait le cycle
  `donnees` / `services` et en réintroduisait un autre (`services ↔
  webhooks`) ; seule la seconde revue l'a vu. La revue n'est pas une étape
  unique entre v1 et v2 : elle se rejoue à chaque version.
- **Un essai ORM tranche mieux qu'une phrase de plan** : la forme de l'`Exists`
  acceptée par Django 5.2 a coûté trois lignes sur SQLite en mémoire et a
  sorti le point de la Phase 3.
- **Deux ordres, deux gardes.** Une absence saisie avant la publication est
  refusée à la publication (422) ; après, elle est signalée. Et une page rendue
  avant la saisie laisse poser une brique que le serveur refuse : la double
  vérification n'est pas redondante. Recharger le planning après toute saisie
  d'absence.
- **Le planning vécu se sauve à la première occasion** : R4a-1 exercé avant la
  4b a donné une violation réelle, un écart de page réel (E1, la brique
  orpheline) et la version 4 — ce qu'aucun jeu fictif ne donnait.

### Leçons de la brique 3-quater

- **Une fusion de jours se prouve contre les jours réels** : le fichier de
  reprise fusionne les pages Notion consécutives d'une même personne et d'un
  même type, et c'est le total de jours par personne, pas le nombre de lignes,
  qui dit si la fusion est juste.
- **La fiche de paie est l'étalon** : le tir de paie d'août confronté aux
  bulletins a fixé C5.1 — la comptable compte les congés payés et les maladies
  en jours ouvrables, le sans-solde en jours réels ; le mail de la brique 5
  enverra dates et catégorie de paie, `jours_comptes` reste un indicateur
  interne.
- **« Déjà présente » partout est la preuve d'un import** : rejouer le fichier
  doit rendre toutes les lignes `deja_presente` et zéro création. Fait en
  production après les 201 absences.

## Périmètre

Le cadrage complet (périmètre v1, décisions C2 → C5, journal de livraison des
briques) est `docs/PLANNING_ASSISTANTES_CADRAGE.md` (v1.7) : il fait foi sur
le périmètre, ce fichier sur les règles de travail.

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

La brique **3** livre les absences : modèles `TypeAbsence` et `AbsenceSalariee`
(`absences/`), espace de la salariée (`/mes-absences/`), écran de décision
(`/absences/`, rôles `principale` et `cabinet`), calcul des jours comptés pour la
paie (`absences/calcul.py`, fériés dans `socle/feries.py`), endpoint
`GET /api/n8n/paie/<AAAA-MM>/`, webhooks `absence.demandee` / `absence.declaree`
/ `absence.decidee` (et `absence.conflit` depuis la 4b), rétention configurable, et changement de l'adresse de
connexion par la salariée. Le client HTTP n8n sortant est factorisé dans
`socle/client_n8n.py`. L'existant Notion 2026 a été repris une fois par
l'écran d'import de la 3-quater (C3.9) ; Notion est une archive en lecture
seule. Voir `docs/ABSENCES.md`.

La brique **4a** (mergée le 06/09/2026, `5072226`) livre le planning servi par
l'application : app `planning/`, `DATA` calculé côté serveur
(`planning/donnees.py`), moteur JS isolé et testé sous Node
(`planning/static/planning/moteur.js`, `planning/tests_js/`), vérification
stricte en double (`planning/verification.py`), versions numérotées
(`PlanningVersion`, `POST /api/planning/<AAAA-MM>/versions/`, 409 / 422), copie
HTML autonome, export et import JSON, `POST /api/erreurs/`, section `palette`
de `regles.json`, blocs de `socle/base.html`. Voir `docs/PLANNING.md`.

La brique **4b** (mergée le 07/09/2026, `0a53bdf`, PR #17) livre la
publication : `POST /api/planning/<AAAA-MM>/versions/<n>/publier/`
(`services.publier`, revérification, audit `planning_publie`, webhook
`planning.publie` par `planning/webhooks.py` sur `N8N_PLANNING_WEBHOOK_URL`),
le conflit absence ↔ planning publié (`planning/conflits.py`, crochet
`absences.services.signaler_conflits`, audit `absence_conflit_publication`,
webhook `absence.conflit`, bandeau sur `/absences/`), « Mes jours »
(`/mes-jours/`, `services.jours_publies`, gabarit `mes_jours.html`), la ligne
« hors présence » (`moteur.orphelins`), `meta.imports` dans `DATA` et la
migration `planning.0002` (`version_de_base` non nul). Le périmètre v1 de
l'application est complet. Voir `docs/PLANNING.md` § 11 et § 12.

La brique **3-quater** (mergée le 07/09/2026, `6de17f1`, PR #19) reprend
l'existant Notion 2026 **une fois** (C3.9) : écran d'administration
`/admin/absences/absencesalariee/importer/` (`AbsenceSalarieeAdmin.get_urls`,
`vue_import`, gabarits `admin/absences/absencesalariee/`), formulaire
`FormulaireImport`, services `importer` / `analyser_import` /
`executer_import`, actions d'audit `absence_importee` et `import_absences`.
Deux temps (rapport, puis confirmation avec analyse rejouée), session
`import_absences` à empreinte et horodatage, écriture tout ou rien, ni webhook
ni crochet de conflit, sans migration de schéma. Voir `docs/ABSENCES.md` § 11.

Le mail comptable et le workflow n8n de `planning.publie` (variable
`N8N_PLANNING_WEBHOOK_URL`, absente jusque-là) relèvent de la brique **5** ;
l'endpoint présences, de la brique **0** (VoiceDoctolib). Ils ne sont pas ici.

`reference/skill-v1/` contient la version 1 du skill de planning, décompressée
telle quelle à titre de référence. Elle n'est **pas** exécutée par
l'application et n'entre pas dans l'image Docker.
