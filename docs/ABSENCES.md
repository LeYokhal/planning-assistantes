# Absences — mode d'emploi

Briques 3 et 3-quater (§ 11). Deux publics : la salariée, qui déclare ou demande ses absences, et la
validatrice (`principale` ou `cabinet`), qui décide et corrige les jours comptés
pour la paie.

> ⚠️ **Donnée de santé.** Le type d'absence (« Maladie ») et la précision libre
> saisie par la salariée ne sortent **jamais** de la base : ni journal d'audit,
> ni logs applicatifs, ni webhook, ni endpoint de paie. Le garde-fou « @ »
> d'`audit/services.py` ne les reconnaîtrait pas — c'est tenu à la main, et
> prouvé par `absences/tests/test_confidentialite.py`. Toute évolution de la
> brique doit relancer ces tests.

## 1. Espace de la salariée

| Écran | Ce qu'on y fait |
|---|---|
| `/mes-absences/` | ses absences, l'état de ses demandes, l'annulation d'une demande en attente |
| `/mes-absences/nouvelle/` | saisie : motif, dates, précision facultative |
| `/mon-profil/` | changement de l'adresse de connexion |

Une salariée ne voit que **ses** absences : le filtre porte sur la personne liée
à son compte, jamais sur un identifiant venu de l'URL.

**Compte sans fiche du personnel.** `Compte.personne` est facultatif : un compte
non rattaché voit un message explicite et aucune saisie ne lui est proposée. Le
rattachement se fait dans l'administration, sur le compte.

## 2. Écran de décision

`/absences/` — réservé à `principale` et `cabinet`.

- **Demandes en attente** : valider ou refuser.
- **Absences du mois** : les jours comptés calculés, les jours retenus, et la
  correction manuelle.
- **Conflit avec un planning publié** (brique 4b) : un bandeau « N absence(s)
  tombe(nt) sur un jour du planning publié » et, sur la ligne de l'absence, le
  marqueur « conflit : AAAA-MM vN (dates) » avec lien vers la page du mois.
  Calculé au rendu sur les absences effectives de type bloquant, jamais
  stocké, jamais bloquant (§ 7 ; `docs/PLANNING.md` § 12).

**Règle d'auto-décision.** Une validatrice ne décide pas de sa propre absence :
seule le rôle `cabinet` la tranche. La règle est assise sur la **personne**
concernée, pas sur l'auteur de la saisie — un compte supprimé laisse l'auteur
nul, et une règle qui s'y appuierait deviendrait inévaluable.

## 3. Types d'absence

Treize types, posés par la migration `absences/0002_types_initiaux`, avec
l'orthographe du select Notion **reproduite telle quelle** (« Congé évenement
familial », « Décés », « Ecole ») : les corriger ferait diverger l'application de
la source que les salariées connaissent.

Deux catégories :

- **soumis à décision** (`demande`) : congé payé, congé sans solde ;
- **déclaration** (`declare`) : effectif immédiatement, sans décision.

Le drapeau `paie` dit si le type entre dans les données transmises pour la paie.
Le cabinet peut désactiver un type ou changer son ordre depuis l'administration ;
un rejeu de la migration ne défait pas son geste.

## 4. Jours comptés

### 4.1 Périodes d'ouverture

`regles/regles.json › periodes_ouverture` porte les jours d'ouverture du cabinet
par période datée. Deux périodes aujourd'hui : mardi→samedi à l'origine,
lundi→vendredi **à partir du lundi 5 octobre 2026**. La bascule est calée sur un
lundi pour qu'aucune semaine ne soit à cheval sur deux régimes.

Cette liste sert **uniquement au calcul de paie**. Le planning (brique 4)
affichera les jours d'après les présences Doctolib réelles ; un samedi ouvert
ponctuellement s'y verra normalement, et se rattrape en paie par correction
manuelle.

Le fichier se modifie **par PR uniquement**, et le chargeur refuse le démarrage
si la structure est invalide (première période non datée, dates non strictement
croissantes, jour inconnu ou en double).

### 4.2 La formule

Semaine par semaine (lundi → dimanche) :

```
jours_comptes = min(J, max(0, B − F))
```

- `J` : jours de l'absence tombant sur un jour d'ouverture de la période
  applicable, **fériés exclus** ;
- `B` : briques du gabarit du contrat — 39 h → 4, 35 h → 4, 27 h → 3 ;
- `F` : fériés de la semaine tombant **sur un jour d'ouverture** — eux seuls
  occupaient déjà une brique.

Une personne à **jours fixes** sans heures hebdomadaires suit sa propre règle :
ses jours fixes font son contrat, fériés exclus.

Un **contrat incomplet** — ni heures ni jours fixes, ou heures hors gabarit —
rend `0` et un signal explicite sur l'écran de décision. Rien n'est bloqué :
aucune donnée manquante n'est inventée, et la validatrice corrige à la main.

> Les jours fériés sont calculés par `socle/feries.py` (onze fériés du régime
> général métropolitain, Pâques par l'algorithme de Meeus/Jones/Butcher).

### 4.3 Deux valeurs, et les demi-journées

`jours_comptes_calcules` est ce que la formule a produit ; `jours_comptes` est ce
qui sera payé. La validatrice peut corriger le second — c'est ainsi qu'un samedi
ouvert ponctuellement se rattrape, et c'est la **seule** porte des
demi-journées : la saisie, elle, va par journées entières.

La correction va par pas de 0,5, ne peut pas être négative ni dépasser la durée
de l'absence. Une absence corrigée **n'est jamais écrasée** par la commande de
recalcul, et l'écart entre les deux valeurs reste lisible six mois plus tard.

> **Divergence assumée** : une absence corrigée à 0,5 reste un **jour bloqué** au
> planning de la brique 4, qui raisonne en briques entières. Le planning et la
> paie divergent volontairement sur ce point ; ce n'est pas un défaut à corriger.

### 4.4 Répartition entre deux mois de paie

La paie se compte sur le **mois calendaire** (`absences/paie.py:plage_calendaire`),
et non sur `presences.fenetres.plage_mois`, qui rend des semaines complètes :
c'est l'outil du planning, et deux mois consécutifs s'y recouvrent de sept jours.

Une absence à cheval sur deux mois est **répartie, chaque mois recevant sa
portion**. La répartition se lit sur `AbsenceSalariee.jours_retenus`, les dates
figées au moment du calcul :

| Cas | Répartition |
|---|---|
| absence non corrigée | un jour retenu = un jour facturé au mois où il tombe. Exact, sans arrondi |
| absence corrigée | prorata des jours retenus de chaque mois, arrondi au demi-jour inférieur ; le reste va au mois du **premier** jour retenu, pour que la somme retombe exactement sur la valeur corrigée |
| absence corrigée sans aucun jour retenu | tout au mois du premier jour, et un drapeau signale que la répartition n'a pas pu être calculée — visible dans le paragraphe |

Dans tous les cas, **la somme des portions vaut les jours comptés de l'absence**,
ni plus ni moins.

> ⚠️ **Pourquoi on ne recoupe pas l'absence pour relancer le calcul dessus.**
> Le plafond hebdomadaire s'appliquerait une fois par morceau et gonflerait le
> total. Contre-exemple : salariée à 27 h (B = 3), absente une semaine entière à
> cheval, régime mardi→samedi. Sur l'absence entière, J = 5, plafond 3, donc
> **3 jours**. Recoupée en 2 + 3 jours ouvrables, on obtiendrait
> min(2,3) + min(3,3) = **5**. Lire les dates retenues évite le piège par
> construction : le plafond a déjà été appliqué, une fois, au calcul.
> Le test `test_le_piege_du_recoupement` garde cette porte fermée.

`jours_retenus` est **figé** au calcul : un changement ultérieur de
`regles.json` ne redistribue pas rétroactivement une paie déjà envoyée. Seule la
commande `recalculer_jours_comptes`, invoquée explicitement, les rafraîchit.

## 5. Endpoint de paie

`GET /api/n8n/paie/<AAAA-MM>/`, sous le même contrôle que le reste de l'API n8n
(en-tête `X-Api-Secret`, ordre 429 → 503 → 401 → 405).

Réponse : les salariées ayant au moins une absence comptée **sur ce mois**, la
somme de leurs portions, le détail par absence, et un **paragraphe mis en forme
côté serveur** prêt à coller dans le mail de la comptable. Une salariée sans
absence comptée n'apparaît pas. Ni type d'absence, ni précision.

Le détail de chaque absence expose **la portion du mois et le total de
l'absence** (`jours_comptes`, `jours_comptes_absence`, `facture_partiellement`),
pour que la comptable comprenne un chiffre partiel sans avoir à le recalculer.

`facture_partiellement` dit que **la portion de ce mois diffère du total**, donc
que le reste est facturé ailleurs. Il ne dit pas que l'absence traverse une
frontière de mois : une absence à cheval dont la totalité est versée à un seul
mois — le cas du contrat incomplet corrigé à la main — le laisse à faux, et
c'est exact. C'est `repartition_calculee` qui porte l'alerte dans ce cas.

L'audit note le mois consulté et le nombre de salariées — **jamais le contenu**,
qui porte des noms.

**Décision C5.1 (cadrage v1.7).** Le mail de la brique 5 enverra à la comptable
les **dates** de chaque absence et sa **catégorie de paie**, pas un nombre de
jours : sur les bulletins de janvier à août 2026, les congés payés et les
maladies sont comptés en jours ouvrables, le sans-solde en jours réels.
`jours_comptes` (formule du § 4, C3.1) devient un **indicateur interne** de
l'écran de décision et du planning. L'endpoint décrit ici ne change pas tant
que la brique 5 n'est pas livrée : son contrat sera réaligné à ce moment-là.

## 6. Rétention

`RETENTION_ABSENCES_JOURS` (variable d'environnement, en jours depuis le dernier
jour de l'absence).

**Absente = rien ne se passe** : aucune échéance n'est posée, aucune purge n'a
lieu, et rien n'est perdu. Le jour où le cabinet fixe la durée, la première
exécution de `purger_absences` **rattrape le stock** : elle pose les échéances
manquantes des absences effectives, en comptant depuis leur date de fin — une
absence de l'an dernier ne gagne pas une nouvelle vie — puis purge ce qui est
échu.

```bash
python manage.py purger_absences --a-blanc   # montre sans rien écrire
python manage.py purger_absences
```

`recalculer_jours_comptes` rejoue le calcul après un changement de périodes
d'ouverture ou une correction de la formule. Il ne touche jamais une absence
corrigée à la main :

```bash
python manage.py recalculer_jours_comptes --mois 2026-10 --a-blanc
python manage.py recalculer_jours_comptes
```

## 7. Webhooks

Quatre événements vers `N8N_ABSENCE_WEBHOOK_URL`, en-tête `X-Webhook-Secret`
(secret partagé `N8N_WEBHOOK_SECRET`), délai 10 s, **fail-closed** :

| Événement | Quand |
|---|---|
| `absence.demandee` | création d'une demande soumise à décision |
| `absence.declaree` | création d'une déclaration, immédiatement effective |
| `absence.decidee` | passage en validée ou refusée |
| `absence.conflit` | brique 4b : une absence bloquante devient effective alors que le planning publié pose déjà une brique de la salariée sur un de ses jours |

L'annulation est **auditée sans webhook** : elle ne demande d'action à personne.

Corps : identifiants, dates, statut, lien vers l'écran de décision. **Ni type, ni
précision, ni nom.** `absence.conflit` porte le même corps, plus
`conflits: [{mois, numero, dates}]` — le mois, le numéro de la version publiée
et les dates touchées ; ni slot, ni nom. Les quatre événements passent par le
même `_envoyer` d'`absences/webhooks.py`, donc par `socle.client_n8n`, avec la
même journalisation.

**Quand le conflit est signalé.** Le crochet `services.signaler_conflits` vient
après l'écriture, l'audit et le webhook de l'absence, sur la **transition** vers
l'état effectif, et seulement pour un type bloquant :

- `creer` : une déclaration (effective immédiatement) ;
- `decider` : une validation ;
- `admin.save_model` : une création en statut effectif, ou un changement de
  `statut` vers un statut effectif (la ressaisie de l'existant Notion, § 9).

Ne signalent **pas** : un refus, une annulation, une correction des jours
comptés, et la modification des dates, du type ou de la précision d'une absence
**déjà** effective (limite assumée, C4.7). Le conflit n'est jamais stocké et ne
bloque rien : l'absence est écrite dans tous les cas. Il est journalisé
(`absence_conflit_publication` : `personne_id`, `mois`, `numero`, `dates`) et
affiché sur `/absences/` (§ 2). Le calcul est dans `planning/conflits.py`
(`docs/PLANNING.md` § 12).

L'export du workflow n8n de réception, « Planning assistantes – Absences
(réception) » (Webhook `/webhook/absence-planning` en Header Auth → Gmail, lit
`evenement` dynamiquement : un seul chemin pour les quatre événements), est
dans [`docs/n8n/n8n_planning_absences_reception.json`](n8n/n8n_planning_absences_reception.json) :
à importer tel quel, puis credential Header Auth et champ **To** à renseigner
dans n8n, jamais dans ce dépôt.

## 8. Changement d'adresse de connexion

La salariée saisit sa nouvelle adresse sur `/mon-profil/` ; un lien de
confirmation part **à la nouvelle adresse**, valable une heure. Rien ne change
tant que le lien n'est pas ouvert.

Le jeton est un jeton signé `django.core.signing` portant l'identifiant du compte
et l'adresse demandée. Son usage unique tient au champ `Compte.email_en_attente`,
vidé à la confirmation.

Si l'adresse est déjà prise par un autre compte, la page répond **exactement la
même chose** et aucun mail ne part : le formulaire ne doit pas devenir un oracle
d'existence de comptes, par cohérence avec la doctrine de `/connexion/`.

À l'effet du changement, `Personne.email_contact` suit — sinon la prochaine
invitation repartirait sur l'ancienne — et tous les liens magiques en circulation
sont invalidés (`SESAME_INVALIDATE_ON_EMAIL_CHANGE`).

## 9. Reprise de l'existant Notion

Notion est une **archive en lecture seule**. L'existant 2026 a été repris
**une fois**, par l'écran d'import de la brique 3-quater (§ 11, décision C3.9
du cadrage v1.7, qui amende C3.8 sans la contredire sur le fond : la saisie
courante passe par l'application, § 1 et § 2). Il n'y a pas de connecteur
Notion dans l'application.

L'administration (`/admin/absences/absencesalariee/`) reste le canal des
corrections à la main : elle accepte la création et la modification et
journalise chaque écriture. Une absence saisie directement en « validée » ou
« déclarée » repart avec ses jours comptés calculés. Depuis la brique 4b, une
absence bloquante qui devient effective par ce canal est confrontée au planning
publié (§ 7) : le conflit est signalé, jamais bloquant.

## 10. Variables d'environnement

| Nom | Absente |
|---|---|
| `RETENTION_ABSENCES_JOURS` | aucune purge, aucune échéance posée, rattrapable |
| `N8N_ABSENCE_WEBHOOK_URL` | aucune notification (fail-closed), `absence.conflit` compris |

Les deux se posent à la main sur Railway ; rien ne casse tant qu'elles sont
absentes.

## 11. Import exceptionnel de l'existant (3-quater)

Décision **C3.9** (cadrage v1.7) : reprise **unique** de l'existant Notion 2026
depuis un fichier, par un écran d'administration — sans migration, sans
connecteur Notion, sans webhook. Recette en production : 201 absences
importées, ré-import idempotent (toutes « déjà présente », zéro création), tir
de paie d'août contrôlé sur les bulletins.

### 11.1 Le fichier

JSON UTF-8, 1 Mo au plus, produit hors de l'application. Un objet portant une
liste `absences` ; chaque élément a `nom`, `prenom`, `type`, `debut`, `fin`
(chaînes), un `ref` facultatif (identifiants Notion, opaques) et une
`precision` **ignorée** — les titres Notion ne sont pas repris. Exemple, tiré
de la fixture fictive `absences/tests/import_fictif.json` :

```json
{
  "source": "jeu-fictif-de-test",
  "absences": [
    {"ref": "notion:aaa1", "nom": "DUPONT", "prenom": "Alice", "type": "Congé payé",
     "debut": "2026-05-26", "fin": "2026-05-30", "precision": ""},
    {"ref": "notion:bbb2,bbb3", "nom": "MARTIN", "prenom": "Bob", "type": "Maladie",
     "debut": "2026-06-02", "fin": "2026-06-03", "precision": ""}
  ]
}
```

Le formulaire (`absences/forms.py:FormulaireImport`) ne juge que la **forme** :
taille, extension `.json`, UTF-8, JSON, clés présentes et chaînes ; ses messages
ne citent que des noms de champs et des numéros de ligne. Les valeurs sont
l'affaire du rapport. Le statut n'est pas dans le fichier : il découle de la
catégorie du type — `validee` si soumis à décision, `declaree` sinon.

### 11.2 L'écran, en deux temps

`/admin/absences/absencesalariee/importer/`, bouton « Importer un fichier »
dans la liste des absences. Rôle `cabinet` par `role_requis`, posé **à
l'extérieur** d'`admin_view` : un autre rôle reçoit le 403 journalisé du
projet, pas la redirection de connexion de l'admin. La route est déclarée
**avant** `super().get_urls()`, sinon `<path:object_id>/` la capturerait.

1. **Analyse.** Le fichier est lu, chaque ligne reçoit un verdict, rien n'est
   écrit. Le fichier normalisé va en session (clé `import_absences` : empreinte
   SHA-256 des octets reçus, horodatage, lignes), jamais sur disque.
2. **Confirmation.** Le bouton n'apparaît que sans erreur et avec au moins une
   ligne à créer ; il porte l'empreinte et les compteurs en champs cachés. La
   vue vérifie l'empreinte et la fraîcheur (15 minutes), **rejoue l'analyse** —
   la base a pu changer entre les deux POST —, refuse avec un nouveau rapport si
   une erreur est apparue ou si les compteurs diffèrent, puis écrit **tout ou
   rien** dans une transaction. GET repart du formulaire vide et efface
   l'analyse en cours.

### 11.3 Les verdicts

| Verdict | Quand |
|---|---|
| `creer` | personne salariée connue, type actif, dates lisibles, aucun chevauchement |
| `deja_presente` | une absence **effective** de même personne, même type, mêmes dates existe déjà : ignorée, comptée. Rejouer le fichier est sûr |
| `erreur` | personne inconnue (`(nom, prenom)` strippés, casse exacte) ou non salariée ; type vide, inconnu ou inactif (libellé exact, fautes Notion comprises) ; date illisible ou inversée ; chevauchement d'une absence effective non identique ; chevauchement d'une **demande en attente** (un doublon naîtrait à la validation) ; deux lignes du fichier qui se chevauchent pour une même personne (les deux) |

Les absences refusées et annulées ne comptent pas. Une ligne peut cumuler
plusieurs motifs. Le rapport donne aussi les jours comptés calculés
(`calcul.jours_comptes`, sans instance), le signal de contrat incomplet et,
pour les lignes à créer de type bloquant, le conflit avec un planning publié
(`planning.conflits`, un seul cache de versions pour tout le rapport) —
information seulement, le crochet `signaler_conflits` n'est pas appelé.

### 11.4 L'écriture et le journal

`services.importer` construit l'absence effective, applique le même calcul et
la même échéance de rétention que `creer`, puis **un seul `save()`** ; `auteur`
et, pour une `validee`, `decide_par` / `decide_le` sont le compte qui confirme.
Ni webhook ni crochet de conflit. `services.executer_import` refuse s'il reste
une erreur, écrit les lignes `creer` dans une transaction et journalise une
fois.

Journal d'audit, muet comme le reste de la brique :

| Action | `details` |
|---|---|
| `absence_importee` (une par absence) | `personne_id`, `statut`, `jours_comptes` (chaîne, comme `absence_decidee`), `ref` |
| `import_absences` (une par confirmation) | `nb_creees`, `nb_ignorees`, `empreinte` |

Logs : « import absences : analyse, N ligne(s), N erreur(s) », « absence #N
importee (statut …, N jour(s) de plage) », « import absences : N creee(s),
N ignoree(s) ». Jamais de nom, de type ni de titre. Prouvé par
`absences/tests/test_import.py` (47 tests) et les deux tests 3-quater de
`absences/tests/test_confidentialite.py`.
