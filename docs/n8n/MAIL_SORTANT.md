# Webhook n8n « mail sortant » — contrat et recette

L'application n'envoie aucun mail elle-même : elle appelle un webhook n8n qui
relaie vers Gmail. Ce document décrit le contrat attendu et la construction du
workflow.

## 1. Contrat d'appel

L'application émet une requête `POST` vers `N8N_MAIL_WEBHOOK_URL` :

| Élément | Valeur |
|---|---|
| Méthode | `POST` |
| En-tête | `X-Mail-Secret: <N8N_WEBHOOK_SECRET>` |
| En-tête | `Content-Type: application/json` |
| Délai d'attente | 10 secondes |

Corps :

```json
{
  "destinataire": "adresse@exemple.fr",
  "objet": "Votre lien de connexion — Planning Assistantes",
  "texte": "Bonjour, voici votre lien de connexion ..."
}
```

Réponse attendue : n'importe quel code `2xx` ou `3xx`. Un code `>= 400` est
compté comme un échec ; seul le **code de statut** est journalisé côté
application — jamais l'adresse, jamais le corps, jamais le lien.

**Fail-closed** : si `N8N_MAIL_WEBHOOK_URL` ou `N8N_WEBHOOK_SECRET` est absent,
l'application n'appelle rien du tout, journalise un avertissement sans aucune
valeur, et l'utilisateur voit malgré tout le message neutre habituel.

## 2. Recette du workflow n8n

### Nœud 1 — Webhook

| Réglage | Valeur |
|---|---|
| HTTP Method | `POST` |
| Path | `mail-sortant-planning` |
| Authentication | `Header Auth` |
| Credential | une credential **Header Auth** neuve (voir ci-dessous) |
| Respond | `When Last Node Finishes` |

Credential Header Auth à créer :

| Champ | Valeur |
|---|---|
| Name | `X-Mail-Secret` |
| Value | la même chaîne que `N8N_WEBHOOK_SECRET` côté Railway |

> ⚠️ Le champ **Name** doit contenir un nom d'en-tête HTTP valide, et lui seul.
> Un nom invalide (espace, deux-points, accent…) provoque une erreur
> `ERR_INVALID_HTTP_TOKEN` **côté n8n**, jamais côté application : l'application
> ne verra qu'un échec d'envoi sans explication. C'est le premier endroit à
> vérifier si les mails ne partent pas.

### Nœud 2 — Gmail → Send

| Champ | Expression |
|---|---|
| To | `{{ $json.body.destinataire }}` |
| Subject | `{{ $json.body.objet }}` |
| Email Type | `Text` |
| Message | `{{ $json.body.texte }}` |

Les valeurs arrivent sous `body` : le nœud Webhook range le corps JSON de la
requête dans `$json.body`.

### Activation

1. **Activer** le workflow (interrupteur en haut à droite).
2. Copier l'URL de **production** : elle contient `/webhook/`, pas
   `/webhook-test/`. L'URL de test ne fonctionne que pendant l'écoute manuelle
   d'un seul appel.
3. Reporter cette URL dans `N8N_MAIL_WEBHOOK_URL` sur Railway.

## 3. Mails émis par la brique 1a

**Lien de connexion** — objet : `Votre lien de connexion — Planning Assistantes`

```
Bonjour, voici votre lien de connexion à Planning Assistantes
(valable 15 minutes, usage unique) :
<lien>
Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.
```

**Invitation** — objet : `Votre accès à Planning Assistantes`.
Ce mail ne contient **aucun jeton** : il renvoie simplement vers la page de
connexion, où la personne saisira son adresse.

```
Un compte vient d'être créé pour vous sur Planning Assistantes
(Espace K Dentaire). Pour vous connecter : <APP_URL>/connexion/ —
saisissez cette adresse, vous recevrez un lien.
```

## 4. Vérification

Depuis la page `/connexion/` de l'application, saisir une adresse ayant un
compte actif. Dans n8n, l'exécution doit apparaître avec un statut « Success ».
Si elle apparaît en erreur `401`, le secret ne concorde pas entre Railway et la
credential Header Auth.
