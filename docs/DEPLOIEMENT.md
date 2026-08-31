# Déploiement sur Railway — briques 1a, 1b et 2

Recette pas-à-pas pour mettre en ligne le socle. Rien de ce qui suit n'est
exécuté par l'outillage : ce sont les gestes à faire dans l'interface Railway.

> ⚠️ **Le premier déploiement échouera, et c'est attendu.**
> Créer le projet Railway depuis le dépôt GitHub déclenche immédiatement un
> premier build, AVANT que les variables ne soient saisies. Ce premier
> déploiement échouera sur `ImproperlyConfigured: DJANGO_SECRET_KEY`.
> C'est normal : ajouter Postgres et les variables, puis générer le domaine,
> puis compléter `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` et `APP_URL`.
> Chaque changement de variable relance un déploiement.

## 1. Créer le projet

1. Railway → **New Project** → **Deploy from GitHub repo** → `LeYokhal/planning-assistantes`.
2. Laisser Railway lancer son premier build. Il échoue : passer à l'étape 2.

Railway détecte le `Dockerfile` grâce à `railway.json` (`"builder": "DOCKERFILE"`).

## 2. Ajouter la base de données

Dans le projet → **New** → **Database** → **Add PostgreSQL**.
Le service `Postgres` expose la variable `DATABASE_URL`, référencée à l'étape 3.

## 3. Saisir les variables du service applicatif

Service applicatif → onglet **Variables**.

| Variable | Valeur | Rôle |
|---|---|---|
| `DJANGO_SECRET_KEY` | une chaîne aléatoire de 50 caractères, propre à la production | Signe les sessions, les cookies **et les liens de connexion**. La changer invalide tous les liens en circulation. Ne jamais la réutiliser ailleurs, ne jamais la committer. |
| `DJANGO_DEBUG` | `0` | Absente ou `0` = production. Ne jamais mettre `1` en ligne. |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Référence au service Postgres. Saisir la syntaxe `${{...}}` telle quelle : Railway la résout. |
| `ALLOWED_HOSTS` | `<domaine-railway>,healthcheck.railway.app` | Hôtes acceptés. **`healthcheck.railway.app` est obligatoire** : sans lui, la sonde de santé reçoit un 400 et le déploiement est déclaré en échec. |
| `CSRF_TRUSTED_ORIGINS` | `https://<domaine-railway>` | Origines de confiance pour les formulaires (avec le schéma `https://`). |
| `APP_URL` | `https://<domaine-railway>` | Base des liens de connexion envoyés par mail. Sans elle, les liens pointeraient vers `localhost`. |
| `N8N_MAIL_WEBHOOK_URL` | URL de **production** du webhook n8n | Voir `docs/n8n/MAIL_SORTANT.md`. Absente = aucun mail envoyé (comportement fail-closed, sans erreur visible). |
| `N8N_WEBHOOK_SECRET` | une chaîne aléatoire | Envoyée dans l'en-tête `X-Mail-Secret`. Doit être **identique** à la valeur du credential Header Auth côté n8n. |
| `CABINET_EMAIL` | l'adresse du compte cabinet | Compte créé automatiquement au pré-déploiement. Absente = aucun compte créé, et le déploiement continue quand même. |
| `N8N_API_SECRET` | une chaîne aléatoire d'au moins 32 caractères, **neuve** | Secret de l'API entrante n8n (en-tête `X-Api-Secret`). Doit être identique à la credential Header Auth du workflow « Déclencher import ». Absente = API désactivée (`503`), sans exception. |
| `N8N_IMPORT_WEBHOOK_URL` | URL de **production** du webhook n8n « Import (réception) » | Voir `docs/n8n/IMPORT_PRESENCES.md`. Absente = aucune notification d'import (fail-closed). Le secret est `N8N_WEBHOOK_SECRET`, envoyé en `X-Webhook-Secret`. |
| `DOCTOLIB_PRESENCES_URL` | *(rien à saisir)* | ⚠️ **NE PAS POSER avant la brique 0.** Endpoint « présences » du serveur MCP Doctolib. Absente = chemin endpoint inactif, ce qui est le comportement attendu en 1b. |
| `DOCTOLIB_PRESENCES_SECRET` | *(rien à saisir)* | ⚠️ **NE PAS POSER avant la brique 0.** Envoyé en `X-Presences-Secret`. |
| `IMPORT_EN_ARRIERE_PLAN` | *(rien à saisir)* | Absente = tâche de fond (comportement normal). `0` fait tourner les lots en synchrone : réservé aux tests. |
| `PORT` | *(rien à saisir)* | Fournie par Railway ; lue par gunicorn dans le `Dockerfile`. |

> ⚠️ Après avoir ajouté une variable, vérifier qu'elle figure bien dans la
> liste du service et que le déploiement déclenché est vert. Leçon de la
> recette 1b : `N8N_IMPORT_WEBHOOK_URL` n'avait pas été posée ; l'application,
> fail-closed, l'a seulement signalé par une ligne « webhook import non
> configure » dans les logs, sans erreur visible.

## 4. Générer le domaine

Service applicatif → **Settings** → **Networking** → **Generate Domain**.
Reporter ensuite le domaine obtenu dans `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
et `APP_URL` (étape 3). Le déploiement se relance à chaque modification.

## 5. Ce que fait le déploiement

`railway.json` définit :

- **`preDeployCommand`** : `python manage.py pre_deploiement`.
  Railway n'exécute pas le pre-deploy dans un shell : une seule commande. Un
  `&&` n'y est jamais interprété — seule la première commande tournerait, ce qui
  s'est produit le 27/08 : les migrations ont tourné, pas la création du compte.
  `pre_deploiement` enchaîne donc elle-même `migrate` puis
  `assurer_compte_cabinet`. Un échec de migration fait échouer le déploiement ;
  `assurer_compte_cabinet`, idempotente, ne lève jamais d'exception : un échec
  de sa part ne doit jamais bloquer un déploiement futur.
- **`healthcheckPath`** : `/sante/`, avec un délai de 120 s. La page renvoie
  `200 {"statut":"ok","base":"ok","migrations_en_attente":0}` quand tout va bien,
  `503` sinon.
- **`restartPolicyType`** : `ON_FAILURE`, 5 tentatives.

## 6. Vérifications après mise en ligne

1. `https://<domaine>/sante/` → `200` et le JSON ci-dessus.
2. `https://<domaine>/` → redirection vers `/connexion/`.
3. Saisir l'adresse du compte cabinet sur `/connexion/` → message neutre, puis
   réception du lien par mail (valable 15 minutes, à usage unique).
4. `https://<domaine>/admin/` → accessible une fois connecté avec ce compte.
5. Dans l'administration, `Journal d'audit` : les événements `lien_demande` et
   `connexion` sont présents, et aucune adresse n'apparaît dans la colonne
   « détails ».
6. `https://<domaine>/presences/importer/` (compte cabinet) : déposer un export
   S7 du mois. L'import doit être « réussi », invariant OK.
7. `https://<domaine>/presences/<AAAA-MM>/` : le mois s'affiche en semaines
   complètes, un agenda par ligne. Recette détaillée de l'API et des deux
   workflows n8n : `docs/n8n/IMPORT_PRESENCES.md`.
8. `https://<domaine>/personnes/importer/` (compte cabinet) : déposer l'export
   de la fiche personnel. Le rapport donne les comptages, les lignes ignorées
   et les avertissements. Contrôle négatif : un export portant une colonne de
   plus doit être **refusé en bloc**, en citant le nom de la colonne fautive et
   rien d'autre.
9. `https://<domaine>/personnes/` : la liste s'affiche, et le bandeau de tête
   dit combien de noms de `regles.json` sont résolus. Recette détaillée des
   personnes, de l'appariement et des comptes : `docs/PERSONNES.md`.

> **Aucune variable d'environnement nouvelle en brique 2.** La table
> `socle_compteurdebit`, qui porte les compteurs de la limitation de débit,
> naît de la migration `socle.0001` — il n'y a rien à créer à la main, et aucun
> cache Django n'est utilisé.

## 7. Si n8n est indisponible

Un lien de secours peut être généré en ligne de commande :

```bash
python manage.py lien_connexion adresse@exemple.fr
```

Le lien s'affiche sur la sortie standard et n'est jamais journalisé. Son usage
sur la production demande un accord explicite préalable.

## 8. Rappels

- Aucun mot de passe n'existe dans l'application : la connexion se fait
  exclusivement par lien magique.
- `SECURE_SSL_REDIRECT` est volontairement à `False` : TLS est assuré par
  Railway, et le mettre à `True` provoque une boucle de redirection derrière
  son proxy. `SECURE_PROXY_SSL_HEADER` suffit à ce que Django sache que la
  requête d'origine était en HTTPS.
