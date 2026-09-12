# Planning Assistantes — Espace K Dentaire

Application Django pour le planning des assistantes du cabinet. Ce dépôt porte
le **socle (brique 1a)** — comptes, connexion sans mot de passe, journal
d'audit, page de santé, déploiement —, l'**import des présences (brique 1b)** :
lecture des exports Doctolib, écran « présences du mois », API n8n, les
**personnes et règles (brique 2)** : import de la fiche personnel, `regles.json`,
appariement des agendas Doctolib, comptes des salariées, les **absences
(brique 3)** : espace de la salariée, décision, jours comptés pour la paie, et
le **planning (brique 4a)** : page servie par l'application, moteur de
proposition dans le navigateur, versions enregistrées, copie autonome, et sa
**publication (brique 4b)** : version publiée, conflit absence ↔ planning
publié, « Mes jours » pour chaque salariée, la **reprise de l'existant 2026
(brique 3-quater)** : import exceptionnel des absences Notion par un écran
d'administration, et la **coquille de l'interface (brique 6a)** : barre et menu
par rôle, tableau de bord sur `/`, connexion à quatre états, pages d'état,
administration habillée, et l'**enveloppe de la page planning (brique 6d)** :
barre commune sur la page, en-tête sur une ligne, barre d'outils réduite et
menu « Plus », et la **grille du planning (briques 8 et 8-bis)** : en-tête
allégé, onglets qui suivent le mois, filtre à plusieurs noms, pictogrammes et
repli des lignes, repli des semaines, sommaire, jour actuel, briques pleines,
cases jour délimitées.

## État

- **Brique 1a livrée le 27/08/2026** : socle Django 5.2 (Python 3.14), connexion
  par lien magique (django-sesame, 15 minutes, usage unique), rôles `cabinet` /
  `principale` / `salariee`, journal d'audit, page `/sante/`, envoi de mail via
  webhook n8n. Déployée sur Railway (projet dédié, PostgreSQL dédié).
- **Brique 1b livrée le 31/08/2026** (`24ed48f`) : import des présences par
  fichier depuis l'application (compte cabinet), invariant de recompte, écran
  « présences du mois », API entrante n8n (santé, déclenchement d'import) et
  webhooks `import.termine` / `import.echec`. Le chemin « endpoint » vers le
  serveur MCP Doctolib est câblé mais **inactif** : il dépend de la brique 0,
  non livrée.
- **Brique 2 livrée le 31/08/2026** (`7ba2a27`, puis 2-bis `488a3f1`, 2-ter
  `b07464b`, 2-quater `951a764`) : la fiche personnel vit dans l'application
  (import rejouable à cinq colonnes), `regles.json` chargé et validé au
  démarrage, appariement Doctolib avec rapport, comptes des salariées créés en
  masse (invitations à la main du cabinet), limitation de débit sur
  `/connexion/` et l'API — IP cliente `X-Real-IP`, établie par mesure.
- **Brique 3 livrée le 03/09/2026** (`e2c751d`, puis 3-bis `d6860a9`, 3-ter
  `b243f10`) : absences des salariées (`/mes-absences/`), écran de décision
  (`/absences/`), jours comptés pour la paie, endpoint
  `GET /api/n8n/paie/<AAAA-MM>/`, webhooks `absence.*`, rétention
  configurable, changement de l'adresse de connexion. Le type d'absence ne
  sort jamais de la base : ni audit, ni logs, ni webhook, ni paie.
- **Brique 4a mergée le 06/09/2026** (`5072226`) : la page planning est servie
  par l'application (`/planning/<AAAA-MM>/`, rôles `cabinet` et `principale`),
  `DATA` calculé côté serveur à partir des présences, des personnes, des règles
  et des absences, moteur JS isolé et testé sous Node, règles strictes
  vérifiées à la fois dans la page et par le serveur, versions numérotées
  (409 si quelqu'un a enregistré entre-temps, 422 si une règle est enfreinte),
  copie HTML autonome, export et import JSON. Recettée le 06/09/2026 ;
  R4a-1 (planning réel de septembre) acté le soir même, en version 4.
- **Brique 4b mergée le 07/09/2026** (`0a53bdf`, PR #17) : publication d'une
  version (`POST /api/planning/<AAAA-MM>/versions/<n>/publier/`,
  revérification par le serveur sur `DATA` recalculé, 409 / 422, audit
  `planning_publie`, webhook `planning.publie`), conflit absence ↔ planning
  publié signalé à l'entrée en état effectif (audit, webhook `absence.conflit`,
  bandeau sur `/absences/`, jamais bloquant), « Mes jours » (`/mes-jours/`,
  rôles `salariee` et `principale`), ligne « hors présence » dans la page,
  `version_de_base` non nul (migration `planning.0002`). Recettée le 07/09/2026
  en production ; réserve R4b-1 : le 422 serveur à la publication n'a été vu
  qu'en test, la page l'ayant refusé avant l'appel.
- **Brique 3-quater mergée le 07/09/2026** (`6de17f1`, PR #19) : reprise
  exceptionnelle de l'existant Notion 2026 (décision C3.9) par un écran
  d'administration en deux temps — rapport d'analyse, puis confirmation avec
  analyse rejouée et écriture tout ou rien —, sans migration ni webhook, audit
  `absence_importee` / `import_absences`. Recettée en production : 201 absences
  importées, ré-import idempotent (toutes « déjà présente »), tir de paie
  d'août contrôlé sur les bulletins.
- **Brique 7a mergée le 08/09/2026** (`95e6ba9`, PR #21) : import d'un
  **planning historique** (décision C7.1) par un écran d'administration en deux
  temps, sur le modèle de la 3-quater. Un fichier au format de l'export JSON de
  la page donne une version **publiée et marquée historique**, écrite sans
  revérification des règles et sans webhook — ces mois n'ont aucune présence
  Doctolib. Les colonnes portées par une fiche de praticien fermée sont
  conservées (C7.4). Les huit mois de janvier à août 2026 ont été importés en
  production le 08/09/2026 ; « Mes jours » les sert sans changement.
- **Brique 7b mergée le 09/09/2026** (`fdfc912`, PR #23) : **lecture** d'un mois
  historique sur `/planning/<AAAA-MM>/historique/` (rôles `cabinet` et
  `principale`) — une page serveur bâtie sur la version publiée, sans `DATA` ni
  moteur, où une journée fait une ligne si le cabinet ouvre ce jour-là ou si elle
  porte une brique. L'écran « aucun import » y renvoie ; la copie autonome d'un
  mois historique répond 404. Recettée en production le 09/09/2026.
- **Brique 6a mergée le 10/09/2026** (`2e30150`, PR #26) : la **coquille** de
  l'interface. `socle/base.html` porte la barre haute et le menu avatar par
  rôle (`user.role`, jamais `is_staff`), les onglets bas de la salariée, une
  déconnexion unique en `POST` et les messages stylés ; `/` devient le tableau
  de bord de `principale` et `cabinet` (versions par horizon, demandes à
  décider, présences et personnes) et redirige la salariée vers « Mes jours » ;
  connexion à quatre états (lien périmé → `/connexion/?expire=1`), pages
  403 / 404 / 500, administration habillée (`admin/base_site.html`, index en
  cinq blocs), favicon. La page planning ne reçoit rien de la coquille (test
  d'isolement). Recettée en production le 10/09/2026.
- **Brique 6d mergée le 11/09/2026** (`a39c3d5`, PR #29) : l'**enveloppe** de la page
  planning. La barre commune arrive sur la page par `barre.css` seule (autonome), sans
  `commun.css` ; en-tête sur une ligne (‹ › vers les mois voisins, pastilles de version
  et de données), Annuler · Enregistrer · Publier et menu « Plus » ; toast sur un 422 de
  publication ; bandeau « écran large » sous 768 px ; `page.js` au vouvoiement ; alertes
  « à signaler au cabinet » pour la principale ; plus de navigation de bas de page.
  `moteur.js` et le contrat `DATA` / `STATE` intouchés, aucune migration. Recettée en
  production le 12/09/2026 (poste de référence 1 536 × 864).
- **Briques 8 et 8-bis mergées le 12/09/2026** (`2522e97`, PR #31 ; `89885de`, PR #32) : la
  **grille** du planning. En-tête allégé (date des données au sous-titre, pastille de version
  masquée sur « Publiée (vN) », sélecteur retiré) ; onglets de gestion sur le mois de la page
  (`nav_urls`) ; filtre à plusieurs noms ; pictogrammes et repli des lignes de rôle (mémorisé
  par le navigateur) ; repli des semaines, sommaire, bandes collantes, jour actuel, flèches
  ← →, glisser assisté ; briques pleines et tailles +1 px ; 8-bis : toutes les briques
  pleines, cases jour bordées et arrondies. `moteur.js` et les contrats intouchés, aucune
  migration. Recettée en production le 12/09/2026 (émulation 1 536 × 864 ; jugement de la
  principale sur son poste à suivre).
  1 039 tests Python, 57 tests Node.
- **Prochaine étape** : la suite de la brique 6 — 6a-bis
  (aménagement à grande largeur), 6b (espace salariée sur téléphone) et 6c (écrans
  absences, présences et personnes) —, puis brique 5 (mail comptable — dates et catégorie de paie
  de chaque absence, décision C5.1 du cadrage v1.7 —, et workflow n8n de
  `planning.publie` avec la variable `N8N_PLANNING_WEBHOOK_URL`) ou brique 0
  (endpoint présences, projet VoiceDoctolib). Le périmètre v1 de l'application
  est complet, et l'existant 2026 est repris.

## Périmètre

| Livré | Pas encore |
|---|---|
| Projet Django 5.2 LTS + PostgreSQL (SQLite en local) | Mail comptable et workflow n8n de publication (brique 5) |
| Modèles `Personne`, `Compte`, `EvenementAudit`, `CompteurDebit` | Appel direct de Doctolib (brique 0) |
| Connexion par lien magique (django-sesame), 15 min, usage unique | |
| Journal d'audit consultable, non modifiable | |
| Page de santé `/sante/` pour la sonde Railway | |
| Envoi de mails délégué à un webhook n8n → Gmail | |
| Import des présences S7 par fichier, avec invariant de recompte | |
| Écran « présences du mois », rôles `cabinet` et `principale` | |
| API n8n `/api/n8n/` et webhooks `import.*` | |
| Import de la fiche personnel, `regles.json`, appariement Doctolib | |
| Comptes des salariées en masse, limitation de débit | |
| Absences des salariées, décision, jours comptés, endpoint de paie, webhooks `absence.*` | |
| Planning servi par l'application, moteur JS testé sous Node, versions (409 / 422), copie autonome | |
| Publication d'une version, conflit absence ↔ planning publié, « Mes jours » pour les salariées | |
| Import exceptionnel de l'existant Notion 2026 : écran d'admin, rapport puis confirmation, tout ou rien | |
| Import d'un planning historique 2026 : écran d'admin, version publiée marquée historique | |
| Lecture d'un mois historique : page dédiée, sans `DATA` ni moteur | |
| Coquille de l'interface : barre et menu par rôle, tableau de bord sur `/`, connexion, pages d'état, admin habillé (6a) ; enveloppe de la page planning : barre commune, en-tête sur une ligne, menu « Plus » (6d) ; grille du planning : filtre à plusieurs noms, repli des lignes et des semaines, sommaire, briques pleines, cases jour (8, 8-bis) | Aménagement à grande largeur (6a-bis) ; espace salariée, écrans absences / présences & personnes (6b, 6c) |

Il n'y a **aucun mot de passe** : on saisit son adresse sur `/connexion/`, on
reçoit un lien, on clique. Un lien périmé ou déjà utilisé ramène sur
`/connexion/?expire=1`. Une fois connecté, `/` mène au tableau de bord
(`principale`, `cabinet`) ou à « Mes jours » (`salariee`). L'administration
Django (`/admin/`) passe par la même porte.

## Démarrage local

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Copier `.env.example` en `.env`, puis y placer une clé de développement jetable :

```bash
.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Puis :

```bash
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py runserver
```

Sans `N8N_MAIL_WEBHOOK_URL`, aucun mail n'est envoyé (comportement voulu). Pour
obtenir quand même un lien de connexion en local :

```bash
.venv/Scripts/python.exe manage.py lien_connexion adresse@example.org
```

Tests :

```bash
.venv/Scripts/python.exe -m pytest
```

> `gunicorn` ne démarre pas sous Windows : il ne sert qu'en production, dans
> l'image Docker. En local, utiliser `manage.py runserver`.

## Variables d'environnement

| Variable | Obligatoire | Rôle |
|---|---|---|
| `DJANGO_SECRET_KEY` | oui | Clé secrète. Son absence empêche le démarrage. Signe aussi les liens de connexion. |
| `DJANGO_DEBUG` | non | `1` en local, absente ou `0` en production. |
| `DATABASE_URL` | non | Vide = SQLite local. En production : `${{Postgres.DATABASE_URL}}`. |
| `ALLOWED_HOSTS` | en production | Doit inclure `healthcheck.railway.app`. |
| `CSRF_TRUSTED_ORIGINS` | en production | Avec le schéma, par ex. `https://exemple.up.railway.app`. |
| `APP_URL` | en production | Base des liens de connexion envoyés par mail. |
| `N8N_MAIL_WEBHOOK_URL` | non | Webhook d'envoi des mails. Absent = aucun envoi. |
| `N8N_WEBHOOK_SECRET` | non | Envoyé dans l'en-tête `X-Mail-Secret`. |
| `CABINET_EMAIL` | non | Compte cabinet créé au pré-déploiement. |
| `N8N_API_SECRET` | non | Secret de l'API entrante n8n, en-tête `X-Api-Secret`. Absent = API désactivée (`503`). |
| `N8N_IMPORT_WEBHOOK_URL` | non | Webhook des événements `import.*`. Absent = aucune notification. |
| `DOCTOLIB_PRESENCES_URL` | non | ⚠️ Brique 0 non livrée : **laisser vide**. |
| `DOCTOLIB_PRESENCES_SECRET` | non | ⚠️ Brique 0 non livrée : **laisser vide**. |
| `IMPORT_EN_ARRIERE_PLAN` | non | Absente = tâche de fond. `0` = synchrone, réservé aux tests. |
| `N8N_ABSENCE_WEBHOOK_URL` | non | Webhook des événements `absence.*`. Absent = aucune notification. |
| `RETENTION_ABSENCES_JOURS` | non | Rétention des absences en jours depuis leur dernier jour. Absente = aucune purge, rien n'est perdu. |
| `N8N_PLANNING_WEBHOOK_URL` | non | Webhook de l'événement `planning.publie` (brique 4b). **Brique 5** : à poser avec le workflow n8n. Absente = aucune notification, une ligne « webhook planning non configure » à chaque publication. |
| `PORT` | — | Fournie par Railway, lue par gunicorn. |

La brique 4a n'ajoute **aucune variable d'environnement** : le plafond de
`/api/erreurs/` est une constante de `config/settings.py` (`DEBIT_ERREURS_IP`).
La brique 4b n'en ajoute qu'une, `N8N_PLANNING_WEBHOOK_URL`, qui reste absente
jusqu'à la brique 5.

## Déploiement

Hébergement Railway, image Docker, sonde de santé sur `/sante/`, migrations et
création du compte cabinet au pré-déploiement par `python manage.py pre_deploiement`.
Railway n'exécute pas le pre-deploy dans un shell : une seule commande.

- Cadrage de l'application (v1.12 — 11/09/2026 : périmètre, décisions C2 → C7, journal des briques) : [`docs/PLANNING_ASSISTANTES_CADRAGE.md`](docs/PLANNING_ASSISTANTES_CADRAGE.md)
- Recette complète : [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)
- Personnes, règles, appariement et comptes : [`docs/PERSONNES.md`](docs/PERSONNES.md)
- Absences, jours comptés, paie, rétention et import exceptionnel de l'existant : [`docs/ABSENCES.md`](docs/ABSENCES.md)
- Planning : contrat `DATA`, moteur, vérification, versions, publication, « Mes jours », conflit, import historique, tests Node, grille (briques 8 et 8-bis) : [`docs/PLANNING.md`](docs/PLANNING.md)
- Interface (brique 6) : coquille `base.html`, tableau de bord, connexion, pages d'état, administration habillée, statiques, enveloppe de la page planning (`barre.css`) : [`docs/INTERFACE.md`](docs/INTERFACE.md)
- Contrat et montage du webhook de mail : [`docs/n8n/MAIL_SORTANT.md`](docs/n8n/MAIL_SORTANT.md)
- API n8n et webhooks d'import : [`docs/n8n/IMPORT_PRESENCES.md`](docs/n8n/IMPORT_PRESENCES.md)
- JSON des trois workflows n8n (à importer tels quels, puis credentials et
  adresse à renseigner) :
  [`docs/n8n/n8n_planning_import_reception.json`](docs/n8n/n8n_planning_import_reception.json),
  [`docs/n8n/n8n_planning_declencher_import.json`](docs/n8n/n8n_planning_declencher_import.json),
  [`docs/n8n/n8n_planning_absences_reception.json`](docs/n8n/n8n_planning_absences_reception.json)
  (réception des événements `absence.*`, `absence.conflit` compris)
- Règles de contribution et interdits : [`CLAUDE.md`](CLAUDE.md)

## Structure

```
config/      réglages, URLs, WSGI/ASGI
comptes/     Personne, Compte, connexion par lien, mails, normalisation des noms, admin
audit/       EvenementAudit et service de journalisation
socle/       page de santé, page d'arrivée `/` (tableau de bord), coquille base.html et gabarits d'état, admin habillé, statiques communs (static/socle/), limitation de débit, fériés, client n8n
presences/   import S7, invariant, verrou, écran du mois, webhooks sortants
personnes/   import de la fiche personnel, appariement Doctolib, écrans (sans modèle)
regles/      regles.json et son chargeur validant (sans modèle)
absences/    TypeAbsence, AbsenceSalariee, jours comptés, espace salariée, décision, import exceptionnel (admin)
planning/    PlanningVersion, DATA côté serveur, vérification stricte, page, copie, publication, conflits, « Mes jours », import historique (admin) ; moteur.js et page.js dans static/, tests Node dans tests_js/
n8n/         API entrante appelée par n8n (sans modèle)
docs/        cadrage, déploiement, personnes, absences, planning, interface, webhooks n8n
reference/   version 1 du skill de planning, à titre de référence (non exécutée, hors image Docker)
```

## Importer des présences

Avec le compte **cabinet**, sur `/presences/importer/`, déposer le résultat de
`consulter_jours_travail` en mode « tous », tel qu'il a été enregistré (wrapper
de l'interface ou payload direct). Un mois s'affiche en semaines complètes, ce
qui demande **une ou deux fenêtres** d'appel de 31 jours au plus — donc un ou
deux fichiers.

L'enveloppe annoncée dans le message (`… ouvert(s), … atypique(s), …`) est
**recomptée sur le détail** : un fichier tronqué ou altéré est refusé en bloc,
et rien n'entre dans l'écran. Une ligne d'import n'est jamais modifiée ni
supprimée ; un import plus récent l'emporte simplement sur un plus ancien pour
les jours qu'ils partagent.

Le mois se consulte sur `/presences/<AAAA-MM>/`, ouvert aux rôles `cabinet` et
`principale`.

## Personnes

Avec le compte **cabinet**, sur `/personnes/importer/`, déposer l'export JSON de
la fiche personnel Notion. Il doit porter **exactement cinq colonnes** :
`Name`, `Department`, `Planning`, `Heures hebdomadaire`, `Jours de travail`.
Toute autre colonne fait **refuser le fichier entier** — la fiche Notion porte
aussi des données qui n'ont pas à entrer ici.

L'import est rejouable et n'écrit que ces colonnes : l'adresse de contact,
l'agenda Doctolib, la couleur et le code ne sont jamais écrasés.

`/personnes/appariement/` propose un agenda Doctolib par praticien planifié, à
partir du dernier lot d'import de présences réussi, et **n'écrit rien** tant que
« Appliquer » n'est pas cliqué.

La liste `/personnes/` est ouverte aux rôles `cabinet` et `principale`.

Le détail des gestes — production du fichier, lecture du rapport, appariement,
création des comptes et invitations, seuils de débit — est dans
[`docs/PERSONNES.md`](docs/PERSONNES.md).

## Absences

`/mes-absences/` pour la salariée, `/absences/` pour la décision (rôles
`cabinet` et `principale`), jours comptés pour la paie servis par
`GET /api/n8n/paie/<AAAA-MM>/`. **Décision C5.1** (cadrage v1.7) : le mail de
la brique 5 enverra à la comptable les dates et la catégorie de paie de chaque
absence ; `jours_comptes` reste un indicateur interne.

**Reprise de l'existant (3-quater).** Avec le compte **cabinet**, sur
`/admin/absences/absencesalariee/importer/` (bouton « Importer un fichier »
dans la liste des absences), déposer le fichier JSON de reprise : un rapport
d'analyse d'abord (à créer / déjà présente / erreur, jours comptés, conflit
avec un planning publié), l'écriture sur confirmation seulement, tout ou rien,
et rien n'est écrit tant qu'il reste une erreur. Rejouer le fichier ne crée
rien. Notion reste une archive en lecture seule. Détail dans
[`docs/ABSENCES.md`](docs/ABSENCES.md) § 11.

## Planning

`/planning/<AAAA-MM>/`, rôles `cabinet` et `principale`. La page calcule ses
données à chaque affichage à partir des présences importées, des personnes
planifiées, de `regles.json` et des absences effectives ; sans aucun import
réussi sur le mois, elle renvoie vers l'import des présences.

À la première ouverture d'un mois, la page pose une proposition (binômes,
exclusives, créneau administratif, reliquat en sureffectif) que l'on ajuste
par glisser-déposer. **Enregistrer** écrit une version numérotée après
vérification des règles strictes, dans la page puis par le serveur : une règle
enfreinte donne un refus détaillé (422), un enregistrement fait entre-temps par
quelqu'un d'autre un refus explicite (409) avec « Exporter JSON » et
« Recharger ». **Enregistrer une copie** télécharge un HTML autonome de la
dernière version ; **Exporter JSON** / **Importer** reprennent les affectations
d'un mois à l'autre. Les absences se corrigent sur `/absences/`, jamais dans le
planning.

**Publier** publie la dernière version enregistrée, après une revérification
des règles par le serveur sur les données du moment (une absence devenue
effective entre-temps donne un refus 422) ; chaque salariée voit alors ses
jours sur `/mes-jours/` (dates, journée, avec qui — rien d'autre). Une
correction est une nouvelle version, publiée à son tour ; il n'y a pas de
dépublication. Une absence bloquante qui devient effective après la publication
est signalée (journal, webhook `absence.conflit`, bandeau sur `/absences/`),
jamais bloquée : la principale corrige le planning et republie. Une brique
posée sur un praticien absent ce jour-là apparaît sur une ligne « hors
présence », à déplacer ou à retirer.

**Règle d'usage : recharger le planning après toute saisie d'absence.** Un
onglet ouvert est un instantané : la page ne voit pas une absence saisie après
son affichage, et le serveur refuse la brique posée dessus (422).

**Planning historique (7a).** Avec le compte **cabinet**, sur
`/admin/planning/planningversion/importer-historique/` (bouton « Importer un
planning historique » dans la liste des versions), déposer un fichier au format
de l'export JSON de la page : un rapport d'analyse d'abord — jours, briques,
colonnes, codes inconnus, doublons —, l'écriture sur confirmation seulement,
avec l'analyse rejouée. La version créée est **publiée et marquée historique** :
ni revérification des règles, ni notification, puisque ces mois n'ont aucune
présence Doctolib. Rejouer le même fichier ne crée rien (« déjà présente »).
Un mois ainsi repris se **lit** sur `/planning/<AAAA-MM>/historique/` : l'écran
« aucun import » y renvoie par un lien, chaque salariée retrouve ses jours sur
`/mes-jours/`, et la copie autonome d'un tel mois répond 404.
Détail dans [`docs/PLANNING.md`](docs/PLANNING.md) § 13.

Architecture, contrat `DATA`, codes de violation, versions, import historique
et tests Node : [`docs/PLANNING.md`](docs/PLANNING.md).
