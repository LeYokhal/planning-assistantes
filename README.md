# Planning Assistantes — Espace K Dentaire

Application Django pour le planning des assistantes du cabinet. Ce dépôt en est
au **socle (brique 1a)** : comptes, connexion sans mot de passe, journal
d'audit, page de santé et fichiers de déploiement.

## Périmètre de la brique 1a

| Livré | Pas encore |
|---|---|
| Projet Django 5.2 LTS + PostgreSQL (SQLite en local) | Import des exports S7 |
| Modèles `Personne`, `Compte`, `EvenementAudit` | Écran « présences du mois » |
| Connexion par lien magique (django-sesame), 15 min, usage unique | Génération du planning |
| Journal d'audit consultable, non modifiable | |
| Page de santé `/sante/` pour la sonde Railway | |
| Envoi de mails délégué à un webhook n8n → Gmail | |

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
| `PORT` | — | Fournie par Railway, lue par gunicorn. |

## Déploiement

Hébergement Railway, image Docker, sonde de santé sur `/sante/`, migrations et
création du compte cabinet au pré-déploiement par `python manage.py pre_deploiement`.
Railway n'exécute pas le pre-deploy dans un shell : une seule commande.

- Recette complète : [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)
- Contrat et montage du webhook de mail : [`docs/n8n/MAIL_SORTANT.md`](docs/n8n/MAIL_SORTANT.md)
- Règles de contribution et interdits : [`CLAUDE.md`](CLAUDE.md)

## Structure

```
config/      réglages, URLs, WSGI/ASGI
comptes/     Personne, Compte, connexion par lien, mails, admin, commandes
audit/       EvenementAudit et service de journalisation
socle/       page de santé, accueil, gabarits communs
docs/        déploiement et webhook n8n
reference/   version 1 du skill de planning, à titre de référence (non exécutée)
```
