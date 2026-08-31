# Personnes, règles et comptes — mode d'emploi

La brique 2 fait entrer la fiche personnel dans l'application, apparie les
agendas Doctolib aux praticiens, et crée les comptes de connexion des
salariées. Ce document décrit les gestes dans l'ordre où on les fait.

Tout est réservé au rôle **cabinet**, sauf la consultation de la liste, ouverte
aussi à l'**assistante principale**.

## 1. Produire le fichier de la fiche

L'import attend un export JSON de la fiche personnel Notion avec **exactement
ces cinq colonnes** :

| Colonne | Contenu |
|---|---|
| `Name` | `NOM Prénom` — le nom en majuscules, le prénom en dernier |
| `Department` | `Assistante`, `Praticien` ou `Secrétariat` |
| `Planning` | la case à cocher (`__YES__` / `__NO__`) |
| `Heures hebdomadaire` | un entier, ou vide |
| `Jours de travail` | une liste de jours, ou vide |

> ⚠️ **Un export au `SELECT *` est refusé par l'application**, fichier entier, sans
> rien importer. La fiche Notion porte aussi le numéro de sécurité sociale, la
> date de naissance, le téléphone et l'IBAN : ces colonnes n'ont rien à faire
> ici, et le refus est délibéré. Le message d'erreur ne cite que des **noms** de
> colonnes, jamais une valeur — il peut donc être recopié sans risque.

La requête Notion doit donc sélectionner ces cinq propriétés et elles seules.
Le résultat se colle tel quel dans un fichier `.json`, sous la forme
`{"results": [...]}` ou sous forme de liste.

## 2. Importer

`/personnes/importer/` → déposer le fichier → **Importer**.

L'import est **rejouable** : le même fichier passé deux fois ne crée rien la
seconde fois. Le rapport affiché donne :

- **les comptages** : lignes exploitables, créées, mises à jour, inchangées ;
- **les lignes ignorées**, avec leur numéro et le motif. La ligne modèle de
  Notion (« New team member ») y figure normalement à chaque import : elle
  n'est pas au format `NOM Prénom`. C'est attendu, pas une erreur ;
- **les avertissements**, à lire à chaque fois :
  - *heures N hors gabarits* — le contrat n'a pas de gabarit dans
    `regles.json`, le planning ne saura pas la poser ;
  - *code en collision, à saisir dans l'admin* — deux personnes de même prénom
    dont les noms commencent pareil ; le code de la seconde reste vide, à
    saisir à la main dans l'administration ;
  - *ni heures hebdomadaires ni jours fixes* — une salariée planifiée sans
    contrat exploitable ;
  - *présente en base, absente du fichier* — un départ, ou une personne
    décochée dans Notion. Rien n'est supprimé : c'est à vous de décider.

Un import n'écrit que les quatre colonnes qui viennent de la fiche
(`Department`, `Planning`, heures, jours). L'adresse de contact, l'agenda
Doctolib, la couleur et le code **ne sont jamais écrasés**.

## 3. Appariement Doctolib

`/personnes/appariement/`.

L'écran confronte les agendas du **dernier lot d'import de présences réussi**
aux praticiens cochés « Planning ». Il ne propose rien tant qu'aucun import de
présences n'a réussi.

Quatre modes :

| Mode | Sens |
|---|---|
| `exact` | le nom de l'agenda correspond au praticien, une fois casse, accents, titre (« Dr ») et suffixe (« (Villecresnes) ») mis de côté |
| `approche` | un seul agenda a le bon prénom et un nom qui commence pareil ; à vérifier des yeux |
| `planning_fixe` | aucun agenda, mais des jours fixes : le praticien se planifie sans Doctolib |
| `aucun` | ni agenda ni jours fixes — il manque quelque chose |

Le tableau **orphelins** liste les agendas que personne ne réclame. Quand un
orphelin porte le nom d'un praticien connu mais non planifié, l'écran le dit :
c'est presque toujours une case « Planning » oubliée dans Notion.

**Rien n'est écrit tant que vous n'avez pas cliqué « Appliquer »**. Le bouton
n'écrit que les modes `exact` et `approche`, et ne touche que la colonne
« agenda Doctolib ».

## 4. Comptes et invitations

Dans l'ordre, et pas autrement :

1. **Administration → Personnes** : saisir `email_contact` sur chaque salariée
   qui doit avoir un accès. C'est l'adresse d'invitation, distincte de tout le
   reste.
2. Sélectionner ces personnes → action **« Créer les comptes de connexion »**.
   Elle crée un compte de rôle `salariee`, sans accès à l'administration, sans
   mot de passe (la connexion se fait par lien). Elle **ignore** en silence les
   personnes sans adresse, celles qui ont déjà un compte, et celles dont
   l'adresse est déjà prise par un autre compte — le message final donne les
   deux comptages. Elle est rejouable sans risque.
3. **Aucune invitation n'est envoyée à cette étape.** L'envoi est un geste
   séparé : Administration → Comptes → action **« Envoyer une invitation »**.

> ⚠️ **Faire un tir de test vers le compte cabinet d'abord.** Une invitation
> part vers une vraie personne : on vérifie le contenu du mail sur soi avant
> d'écrire à l'équipe.

Le mail d'invitation ne contient **aucun jeton** : il renvoie vers
`/connexion/`, où la personne saisit son adresse et reçoit un lien.

Un départ se traite par désactivation, jamais par suppression.

## 5. Rôle « assistante principale »

Le rôle `principale` voit la liste des personnes et les présences, en lecture
seule. Il n'a ni l'import, ni l'appariement, ni l'administration. Il se pose à
la main sur le compte, dans l'administration.

## 6. Limitation de débit

Les points d'entrée publics sont plafonnés par fenêtres fixes :

| Portée | Plafond | Fenêtre | Réponse au-delà |
|---|---|---|---|
| `/connexion/` par adresse IP | 10 POST | 15 min | `429` + « Trop de demandes » |
| `/connexion/` par adresse e-mail | 5 POST | 1 h | **page neutre habituelle** |
| API n8n par adresse IP | 60 appels | 1 min | `429` `{"verdict": "too_many"}` |

Le plafond par adresse e-mail renvoie **exactement la même page** qu'une
demande normale : rien ne doit permettre de deviner qu'un compte existe. Seul
le journal d'audit en garde trace (`lien_refuse`, motif `debit`).

`/sante/` n'est jamais plafonnée : Railway la sonde en continu.

Les compteurs vivent dans la table `socle_compteurdebit`, une ligne par fenêtre
et par empreinte, purgée d'elle-même. L'adresse n'y est stockée que sous forme
d'empreinte tronquée, et n'apparaît jamais dans les logs.

L'adresse IP est lue dans `X-Real-IP`, imposé par Railway.

## 7. `regles/regles.json`

Ce fichier porte les binômes, les praticiens exclusifs, les gabarits horaires,
les couleurs, les créneaux administratifs et les alternantes. Il est **la
source des règles du planning**.

Il se modifie **par pull request uniquement** — jamais depuis l'application, qui
n'offre aucun écran pour cela. Il est chargé et validé **au démarrage** : un
fichier invalide empêche l'application de démarrer, plutôt que de la laisser
planifier sur des règles fausses.

Le bandeau en tête de `/personnes/` confronte les noms du fichier aux personnes
en base et liste les **non résolus** : un nom qui y figure signale un fichier de
règles en retard sur la fiche (départ, mariage, faute de frappe).

`reference/skill-v1/` reste la référence historique et **n'est pas exécutée**
par l'application ; `regles/regles.json` en est la copie conforme.
