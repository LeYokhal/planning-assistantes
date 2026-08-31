# Planning Assistantes — Espace K Dentaire

Application Django pour le planning des assistantes du cabinet. Ce dépôt porte
le **socle (brique 1a)** — comptes, connexion sans mot de passe, journal
d'audit, page de santé, déploiement —, l'**import des présences (brique 1b)** :
lecture des exports Doctolib, écran « présences du mois », API n8n, et les
**personnes et règles (brique 2)** : import de la fiche personnel, `regles.json`,
appariement des agendas Doctolib, comptes des salariées.

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
- **Prochaine étape** : brique 3 — absences des salariées, ou brique 0
  (endpoint présences, projet VoiceDoctolib).

## Périmètre

| Livré | Pas encore |
|---|---|
| Projet Django 5.2 LTS + PostgreSQL (SQLite en local) | Absences des salariées (brique 3) |
| Modèles `Personne`, `Compte`, `EvenementAudit`, `CompteurDebit` | Génération du planning (brique 4) |
| Connexion par lien magique (django-sesame), 15 min, usage unique | Publication et purge (briques 4 et 5) |
| Journal d'audit consultable, non modifiable | Appel direct de Doctolib (brique 0) |
| Page de santé `/sante/` pour la sonde Railway | |
| Envoi de mails délégué à un webhook n8n → Gmail | |
| Import des présences S7 par fichier, avec invariant de recompte | |
| Écran « présences du mois », rôles `cabinet` et `principale` | |
| API n8n `/api/n8n/` et webhooks `import.*` | |
| Import de la fiche personnel, `regles.json`, appariement Doctolib | |
| Comptes des salariées en masse, limitation de débit | |

Il n'y a **aucun mot de passe** : on saisit son adresse sur `/connexion/`, on
reçoit un lien, on clique. L'administration Django (`/admin/`) passe par la même
porte.

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
| `PORT` | — | Fournie par Railway, lue par gunicorn. |

## Déploiement

Hébergement Railway, image Docker, sonde de santé sur `/sante/`, migrations et
création du compte cabinet au pré-déploiement par `python manage.py pre_deploiement`.
Railway n'exécute pas le pre-deploy dans un shell : une seule commande.

- Recette complète : [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)
- Personnes, règles, appariement et comptes : [`docs/PERSONNES.md`](docs/PERSONNES.md)
- Contrat et montage du webhook de mail : [`docs/n8n/MAIL_SORTANT.md`](docs/n8n/MAIL_SORTANT.md)
- API n8n et webhooks d'import : [`docs/n8n/IMPORT_PRESENCES.md`](docs/n8n/IMPORT_PRESENCES.md)
- JSON des deux workflows n8n d'import (à importer tels quels, puis credentials
  et adresse à renseigner) :
  [`docs/n8n/n8n_planning_import_reception.json`](docs/n8n/n8n_planning_import_reception.json),
  [`docs/n8n/n8n_planning_declencher_import.json`](docs/n8n/n8n_planning_declencher_import.json)
- Règles de contribution et interdits : [`CLAUDE.md`](CLAUDE.md)

## Structure

```
config/      réglages, URLs, WSGI/ASGI
comptes/     Personne, Compte, connexion par lien, mails, normalisation des noms, admin
audit/       EvenementAudit et service de journalisation
socle/       page de santé, accueil, gabarits communs, limitation de débit
presences/   import S7, invariant, verrou, écran du mois, webhooks sortants
personnes/   import de la fiche personnel, appariement Doctolib, écrans (sans modèle)
regles/      regles.json et son chargeur validant (sans modèle)
n8n/         API entrante appelée par n8n (sans modèle)
docs/        déploiement, personnes, webhooks n8n
reference/   version 1 du skill de planning, à titre de référence (non exécutée)
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
