# API n8n « import des présences » — contrats et recette

La brique 1b ouvre deux chemins entre n8n et l'application :

- **n8n → application** : une API entrante (santé, déclenchement d'un import),
  protégée par un secret d'en-tête ;
- **application → n8n** : un webhook sortant à la fin de chaque lot d'import
  (`import.termine` / `import.echec`), sur le modèle du webhook de mail.

> ⚠️ **Le chemin « endpoint » est inactif en 1b.** Il interroge le serveur MCP
> Doctolib, qui relève de la **brique 0**, non livrée. Tant que
> `DOCTOLIB_PRESENCES_URL` et `DOCTOLIB_PRESENCES_SECRET` sont absentes, un
> import déclenché par n8n est accepté (`202`), puis échoue immédiatement avec
> `endpoint inactif (brique 0 non livrée)`, et n8n reçoit `import.echec`.
> **C'est le comportement attendu**, et c'est ce que vérifie la recette.
> En 1b, la voie qui fonctionne est l'import **par fichier**, depuis
> `/presences/importer/`, avec le compte cabinet.

## 1. Contrat de l'API entrante (n8n → application)

Préfixe commun : `<APP_URL>/api/n8n/`.

| Élément | Valeur |
|---|---|
| En-tête | `X-Api-Secret: <N8N_API_SECRET>` |
| En-tête | `Content-Type: application/json` (sur les `POST`) |
| Format | JSON en entrée comme en sortie, y compris les erreurs |
| Session | aucune ; le contrôle CSRF ne s'applique pas |

**Le secret est vérifié avant la méthode.** Un `GET` sur une route en `POST`
sans secret reçoit `401`, pas `405` : rien ne doit permettre de deviner
l'existence d'une route.

| Cas | Réponse |
|---|---|
| `N8N_API_SECRET` absente côté application | `503` `{"verdict":"disabled"}` |
| En-tête absent **ou** secret faux | `401` `{"verdict":"unauthorized"}` |
| Bonne route, mauvaise méthode | `405` `{"erreur":"methode_non_autorisee"}` |

Les deux cas `401` renvoient **exactement** le même statut et le même corps.
Aucun refus n'écrit dans le journal d'audit — du trafic non authentifié ne doit
pas pouvoir faire grossir une table. Un `logger.warning` est émis, sans jamais
la valeur reçue.

### `GET /api/n8n/sante/`

```json
{"statut": "ok", "import_en_cours": false}
```

`import_en_cours` ignore un verrou périmé (plus de 15 minutes) : un
redéploiement survenu au milieu d'un import ne bloque pas la sonde
indéfiniment. L'appel requalifie au passage les lignes restées « en cours ».

### `POST /api/n8n/imports/`

Corps attendu :

```json
{"mois": "2026-10"}
```

Réponse `202` :

```json
{
  "accepte": true,
  "lot": "3f2b1c4e-....",
  "mois": "2026-10",
  "fenetres": [["2026-09-28", "2026-10-28"], ["2026-10-29", "2026-11-01"]]
}
```

L'application rend la main tout de suite : le lot s'exécute en tâche de fond, et
c'est le webhook qui annonce son issue.

| Cas | Réponse |
|---|---|
| Corps illisible ou qui n'est pas un objet JSON | `400` `{"accepte":false,"raison":"corps_invalide"}` |
| `mois` absent ou mal formé (`2026-13`, `202610`…) | `400` `{"accepte":false,"raison":"mois_invalide"}` |
| Un import est déjà en cours | `409` `{"accepte":false,"raison":"import_en_cours"}` |
| Lancement impossible | `500` `{"accepte":false,"raison":"lancement_impossible"}` |

Un mois se couvre en **semaines complètes** (lundi → dimanche), donc 28, 35 ou
42 jours, découpés en une ou deux fenêtres de 31 jours au plus — la limite de
`consulter_jours_travail`.

## 2. Contrat du webhook sortant (application → n8n)

Un webhook **par lot**, émis à la fin du lot — qu'il vienne d'un fichier ou de
l'endpoint.

| Élément | Valeur |
|---|---|
| Méthode | `POST` vers `N8N_IMPORT_WEBHOOK_URL` |
| En-tête | `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>` |
| En-tête | `Content-Type: application/json` |
| Délai d'attente | 10 secondes |

```json
{
  "evenement": "import.termine",
  "lot": "3f2b1c4e-....",
  "mois": "2026-10",
  "source": "fichier",
  "fenetres": [
    {
      "import_id": 12,
      "debut": "2026-09-28",
      "fin": "2026-10-28",
      "statut": "reussi",
      "invariant_ok": true,
      "nb_lignes": 248,
      "erreur": ""
    }
  ],
  "lien": "https://<domaine>/presences/2026-10/",
  "horodatage": "2026-10-01T09:12:33.120000+02:00"
}
```

`evenement` vaut `import.termine` si **toutes** les fenêtres du lot sont
réussies, `import.echec` sinon. `mois` est `null` pour un import par fichier (le
mois n'est pas une propriété du payload) ; `lien` pointe malgré tout vers le bon
écran, déduit de la fenêtre.

Le corps ne contient **aucun nom d'agenda, aucune donnée patient** : uniquement
des identifiants, des fenêtres et des comptages.

**Fail-closed** : si `N8N_IMPORT_WEBHOOK_URL` ou `N8N_WEBHOOK_SECRET` est
absent, rien n'est envoyé, un avertissement sans valeur est journalisé, et
l'import reste par ailleurs inchangé. Seul le **code de statut** est journalisé
côté application.

## 3. Workflow « Planning assistantes – Import (réception) »

Il reçoit les événements et prévient par mail.

### Nœud 1 — Webhook

| Réglage | Valeur |
|---|---|
| HTTP Method | `POST` |
| Path | `import-planning` |
| Authentication | `Header Auth` |
| Credential | Header Auth, **Name** `X-Webhook-Secret`, **Value** = la valeur de `N8N_WEBHOOK_SECRET` déjà en place |
| Respond | `When Last Node Finishes` |

> ⚠️ Le champ **Name** doit contenir un nom d'en-tête HTTP valide, et lui seul.
> Un nom invalide provoque `ERR_INVALID_HTTP_TOKEN` **côté n8n**, jamais côté
> application : celle-ci ne verra qu'un échec sans explication.

Aucun secret nouveau n'est à créer côté Railway pour ce workflow : il réutilise
`N8N_WEBHOOK_SECRET`, celui du mail sortant.

### Nœud 2 — Gmail → Send

| Champ | Expression |
|---|---|
| To | l'adresse de Yohan, **saisie dans n8n** (jamais dans ce dépôt) |
| Subject | `Planning assistantes — {{ $json.body.evenement }} (lot {{ $json.body.lot }})` |
| Email Type | `Text` |
| Message | `{{ JSON.stringify($json.body, null, 2) }}` |

### Réglages du workflow

- **Available in MCP : décoché.** Ce workflow ne doit jamais être appelable par
  un assistant.
- Activer le workflow, puis copier l'URL de **production** (elle contient
  `/webhook/`, pas `/webhook-test/`) et la reporter dans
  `N8N_IMPORT_WEBHOOK_URL` sur Railway.

## 4. Workflow « Planning assistantes – Déclencher import »

Il demande un import à l'application.

### Nœud 1 — Manual Trigger

Rien à régler. Un `Schedule Trigger` pourra le remplacer plus tard ; dans ce
cas, fixer le fuseau du workflow à `Europe/Paris`.

### Nœud 2 — HTTP Request

| Réglage | Valeur |
|---|---|
| Method | `POST` |
| URL | `<APP_URL>/api/n8n/imports/` |
| Authentication | `Generic Credential Type` → `Header Auth` |
| Credential | Header Auth, **Name** `X-Api-Secret`, **Value** = `N8N_API_SECRET` |
| Send Body | activé, `JSON`, `{"mois": "2026-10"}` |
| Timeout | `30000` ms |
| Options | `Never Error` **et** `Full Response` (pour lire `statusCode`) |

### Nœud 3 — IF puis Gmail d'alerte

Condition : `{{ $json.statusCode }}` **différent de** `202` → branche vraie vers
un nœud Gmail d'alerte (patron du canari du mail sortant). Une réponse `409`
signifie simplement qu'un import tourne déjà : ce n'est pas une panne.

- **Available in MCP : décoché.**

## 5. Vérification

À faire une fois les variables posées sur Railway et les deux workflows actifs.

1. **Import par fichier** — compte cabinet, `/presences/importer/`, déposer le
   premier puis le second fichier S7 du mois. Les deux lignes doivent être
   « réussi », invariant OK, et l'enveloppe affichée doit être celle lue à
   l'appel. Deux exécutions `import.termine` doivent apparaître dans le workflow
   de réception.
2. **Écran** — `/presences/2026-10/` : cinq semaines, aucun jour « non importé ».
3. **Fichier altéré** — reprendre une copie d'un fichier, y retirer une ligne de
   praticien : l'import doit échouer avec « écart enveloppe / recompte », et
   `import.echec` doit arriver dans n8n.
4. **Déclenchement** — exécuter « Déclencher import » à la main : le nœud HTTP
   doit afficher `202`, l'administration doit montrer une ligne `endpoint` en
   échec « endpoint inactif (brique 0 non livrée) », et le workflow de réception
   doit recevoir `import.echec`.
5. **Contrôles négatifs** — avec une credential volontairement fausse :
   - sur le déclencheur, le nœud HTTP doit afficher `401` ;
   - sur le récepteur, l'appel doit être refusé par le nœud Webhook (c'est un
     `403` que renvoie n8n en `Header Auth`, comme pour le mail sortant).

## 6. Rappels

- Le chemin endpoint reste inactif tant que `DOCTOLIB_PRESENCES_URL` et
  `DOCTOLIB_PRESENCES_SECRET` ne sont pas posées. **Ne pas les poser avant la
  livraison de la brique 0.**
- **Un seul tir endpoint à la fois** : un verrou en base l'assure, avec une
  péremption de 15 minutes qui permet de reprendre après un redéploiement.
- **Une ligne d'import n'est jamais modifiée ni supprimée.** Un import fautif
  est simplement dépassé par un import plus récent couvrant les mêmes jours ;
  la ligne fautive reste visible dans l'administration.
- L'import par fichier ne prend pas le verrou : il ne touche pas au réseau.
