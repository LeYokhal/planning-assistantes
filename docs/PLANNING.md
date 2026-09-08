# Planning — architecture des briques 4a et 4b

La page `/planning/<AAAA-MM>/` remplace le fichier HTML autonome du skill v1 :
les données (`DATA`) sont calculées par le serveur à chaque affichage, l'état
du planning (`STATE`) est enregistré en base sous forme de versions numérotées,
et la logique de proposition et de règles reste dans le navigateur (décision
C2.2). Le gabarit du skill a été **porté**, pas copié : `reference/skill-v1/`
reste la référence historique, non exécutée et exclue de l'image Docker.

État au 07/09/2026 : brique 4a mergée le 06/09 (`5072226`, PR #15) et brique
4b mergée le 07/09 (`0a53bdf`, PR #17), toutes deux déployées et recettées en
production. R4a-1 est acté (planning réel de septembre importé, une violation
`praticien_absent` expliquée et corrigée, version 4) ; il a révélé l'écart E1
(brique orpheline invisible), réglé en 4b par la ligne « hors présence »
(§ 11.4). Réserve R4b-1 : le 422 serveur à la publication est couvert par
`test_publication` mais n'a pas été vu en production, la page l'ayant refusé
avant l'appel. Brique **7a** mergée le 08/09/2026 (`95e6ba9`, PR #21) :
l'import d'un planning historique (§ 13), qui reprend les mois de 2026
antérieurs à l'application ; sa partie lecture (7b) n'est pas livrée.

## 1. Routes et rôles

| Route | Rôle | Ce qu'elle fait |
|---|---|---|
| `GET /planning/` | `cabinet`, `principale` | redirige vers le mois courant |
| `GET /planning/<AAAA-MM>/` | `cabinet`, `principale` | la page ; sans aucun import réussi sur la plage, un écran « aucun import » renvoie vers `/presences/importer/` |
| `GET /planning/<AAAA-MM>/copie/` | `cabinet`, `principale` | copie HTML autonome de la dernière version (404 s'il n'y en a aucune) |
| `POST /api/planning/<AAAA-MM>/versions/` | `cabinet`, `principale`, session + CSRF | enregistre une version : 201, 409 ou 422 |
| `POST /api/planning/<AAAA-MM>/versions/<n>/publier/` | `cabinet`, `principale`, session + CSRF | publie la version `<n>`, qui doit être la dernière : 200, 409 ou 422 (§ 11) |
| `POST /api/erreurs/` | plafond par IP, puis `cabinet`, `principale` | journalise une erreur JS de la page, sans rien stocker |
| `GET /mes-jours/` | `salariee`, `principale` | redirige vers le mois courant |
| `GET /mes-jours/<AAAA-MM>/` | `salariee`, `principale` | « Mes jours » : les jours de la personne connectée dans le planning publié (§ 11.3) ; `cabinet` reçoit 403 |
| `GET`/`POST /admin/planning/planningversion/importer-historique/` | `cabinet` + `is_staff`, session + CSRF | import d'un planning historique, en deux temps (§ 13) |

Le contrôle de rôle est `comptes.acces.role_requis` : un anonyme est redirigé
vers `/connexion/`, un autre rôle reçoit 403. `page.js` teste `redirected` et
le `Content-Type` d'une réponse d'API avant de la lire : une session expirée
donne un bandeau, pas un JSON cassé.

## 2. `DATA` : ce que le serveur calcule

`planning/donnees.py::construire(mois)` rend le dictionnaire que la page lit,
au contrat du gabarit du skill (`build_planning.py`, § 3 à 6), à partir des
tables de l'application. Les seules clés nouvelles sont `meta.non_couverts`,
`meta.alertes`, `meta.imports` (brique 4b) et `attentes` ; l'ancien code les
ignore.

| Clé | Source | Notes |
|---|---|---|
| `meta` | `presences.fenetres.plage_mois` (semaines complètes), règles, imports | `genere` en ISO, `source = "app"`, `heures` et `seuils` (du premier import couvert, sinon 4 h / 5 h et une alerte), `enveloppes` (messages des imports retenus), `imports` (`[{id, empreinte}]` de ces mêmes imports, triés par identifiant — brique 4b, recopié dans `verifications` à la publication), `non_couverts` (dates de la plage sans import réussi), `alertes` (textes destinés à l'écran) |
| `praticiens[]` | `Personne` praticien, planifié, actif | `id`, `label`, `nom`, `agenda` (agenda Doctolib apparié, ou `null` pour un planning fixe), `couleur` `[fond, encre]`, `fixes` (entiers, lundi = 0), `attendues`, `exclusif`, `binomes`, `a_part`, `etiquette` ; les praticiens à part passent en fin de liste |
| `salaries[]` | `Personne` assistante ou secrétaire, planifiée, active | mêmes identifiants et couleurs ; `role`, `heures`, `heures_fixes`, `gabarit`, `binomes`, `exclusif`, `admin`, `etudiante` (clé posée seulement sur les étudiantes) ; `heures_supposees` reste dans le contrat et vaut toujours `false` |
| `jours{iso}{pid}` | `presences.services.imports_par_date` + payload brut | `pr`, `v`, `c` (depuis `creneaux`, pas les effectifs), `fin`, `n`, `jc`, `min` ; lignes triviales omises |
| `conges[]` | `absences.services.absences_du_mois`, sans filtre de type | une entrée par jour : `s`, `date`, `type` (libellé, décision C4.1), `bloque = type.bloquant` |
| `cours{sid}` | absences effectives de type « Ecole » des étudiantes listées dans les règles | une absence « Ecole » d'une étudiante alimente `cours` et **pas** `conges` ; sur toute autre personne elle reste un congé bloquant |
| `attentes[]` | demandes `en_attente` sur la plage | `s`, `date` ; informatif, ne bloque rien |
| `feries{iso}` | `socle.feries.feries_entre` | calendrier français |

Règles de construction, toutes signalées dans `meta.alertes` quand elles
excluent quelqu'un :

- un praticien sans agenda apparié **et** sans jours fixes est exclu ; un
  agenda apparié qui n'apparaît dans aucun import de la plage est signalé ;
- une salariée dont les heures n'ont pas de gabarit, ou sans heures ni jours
  fixes, est exclue. Le skill supposait 39 h : l'application ne suppose rien ;
- une secrétaire sans heures à jours fixes suit la règle du skill (ses jours
  fixes font son contrat) ; une étudiante reçoit `gabarit_sans_cours` à la
  place de son gabarit horaire ;
- les noms de `regles.json` sont résolus en personnes par
  `regles.chargeur.resoudre` ; un nom non résolu donne une règle ignorée et une
  alerte ;
- `label` = prénom, ou prénom + initiale du nom en cas de doublon ;
- l'identifiant `id` est `Personne.code` ; s'il est nul (collision), le repli
  `code_pour(prenom, nom) + pk` est calculé à chaque rendu, jamais écrit en
  base, et une alerte demande de saisir le code dans l'administration ;
- les couleurs viennent de la section `palette` de `regles.json` (nom de
  couleur Notion vers couple hexadécimal, `default` obligatoire) ;
- les absences de personnes hors périmètre (non planifiées, inactives,
  praticiens) sont écartées **sans alerte** : rien ne doit dire quelque chose
  d'une personne absente de la page.

Sans aucun import réussi sur la plage (`donnees.mois_couvert`), la vue rend
`sans_import.html` et le moteur ne démarre pas.

## 3. `STATE` : quatre clés, rien d'autre

L'état enregistré ne porte que `affectations`, `feries`, `feries_off` et
`notes`. Les congés, les cours et les types d'absence n'y entrent jamais : ils
viennent de `DATA` à chaque rendu. `initialise` et `modifie`, drapeaux de
l'ancien gabarit, n'existent plus.

```
affectations : { "<AAAA-MM-JJ>": { "<slot>": [ {s, t, x, a}, … ] } }
feries       : { "<AAAA-MM-JJ>": "<libellé>" }        (jours fermés dans la page)
feries_off   : [ "<AAAA-MM-JJ>", … ]                   (fériés du calendrier rouverts)
notes        : { "<AAAA-MM-JJ>": [ "texte", … ] }
```

Une brique est `{s: <id salariée>, t: "J" | "C", x: <hors quota>, a: <posée
par le moteur>}` ; un slot est un identifiant de praticien ou `secretariat`,
`sureffectif`, `administratif`. Le nettoyage (`verification.nettoyer` côté
serveur, `nettoyer` côté moteur) réduit tout état reçu à ces quatre clés et
normalise `notes` en listes (l'ancien format en chaîne est accepté).

**La page propose si et seulement si le numéro de version servi vaut 0.**
Aucun drapeau de l'état ne porte cette décision : une version enregistrée aux
affectations vides reste vide au rechargement.

## 4. Moteur et page

Le `<script>` du gabarit est découpé en deux fichiers statiques.

**`planning/static/planning/moteur.js`** — tout ce qui ne touche pas au DOM.
Enveloppe UMD : `window.PlanningMoteur` dans le navigateur, `module.exports`
sous Node, aucune dépendance. La fabrique `PlanningMoteur.creer(DATA, state)`
rend un objet de fonctions fermées sur `DATA` et sur `state`, **muté en place
et jamais réassigné** (le moteur y pose les quatre clés et supprime les autres).
Il contient le calendrier (`WEEKS`, `SHOWN`), la réserve hebdomadaire
(`virtuels`, `consommer`, `quota`, `placed`, `reserve`, `heures`, `jauge`), la
proposition (`proposer`, `initialState`), les mutations (`place`, `unplace`,
`fermerJour`, `rouvrirJour`, `poserNotes`, `importer`, `snapshot`, `undo`,
`peutAnnuler`), les sérialisations (`exporter`, `charge`, `empreinte`), la
vérification stricte (`verifier`) et, depuis la 4b, `orphelins` (§ 11.4).

**Règle unique de mutation** : aucune fonction du moteur n'appelle `commit`,
`render`, `toast` ni `confirm`. Le moteur mute et rend des résultats
(`place` rend `{ok, code, cible, bascule}`) ; `page.js` enchaîne toujours
`M.x(); commit();`. Un test Node lit la source du moteur et refuse `document.`,
`toast(`, `confirm(`, `render(`, `commit(`, `alert(`, `localStorage`.

**`planning/static/planning/page.js`** — rendu, glisser-déposer, toasts,
boutons, raccourcis, appels d'API (enregistrer, publier — § 11.2),
`beforeunload` (si l'empreinte de l'état
diffère de la dernière version), rapport d'erreurs. `initialState()` n'y est
appelée que si `META.numero === 0`. Les messages des violations et des refus
sont composés à partir des codes.

**Ce que la page a perdu par rapport au gabarit** : le brouillon
`localStorage` et « Repartir du fichier », la pose et le déplacement manuels de
congés, le réglage `− N +` des cours. Une absence ou un jour d'école se corrige
sur `/absences/`, puis la page se recharge. Les absences s'affichent en lecture
seule ; une demande en attente apparaît en badge discret.

**Ce qu'elle a gagné** : « Enregistrer » avec numéro de version dans la barre,
bandeau 409 avec « Exporter JSON » et « Recharger », liste des violations 422
avec cases surlignées, jours « sans données Doctolib », « Enregistrer une
copie » désactivé tant que l'état diffère de la dernière version.

Trois blocs `json_script` alimentent la page : `planning-data`,
`planning-state`, `planning-meta` (`{mois, numero, autonome, publiee, urls}`,
`publiee` et `urls.publier` depuis la 4b — § 11.2). Django y
échappe `<`, `>`, `&` et les accents : un test qui lit le bloc le décode.
`page.html` porte un `{% csrf_token %}` explicite, car c'est ce rendu qui pose
le cookie `csrftoken` lu par `page.js` pour l'en-tête `X-CSRFToken`.

`socle/base.html` a reçu cinq blocs pour que la page impose sa mise en page :
`classe_html`, `style_base`, `en_tete_page`, `navigation_page`, `scripts`. Leur
contenu par défaut est l'existant : un test rend l'accueil et l'espace
salariée avec l'ancien `base.html` chargé en mémoire et compare les chaînes.

## 5. Vérification stricte : deux implémentations, un jeu de cas

`planning/verification.py::verifier(data, state)` et `verifier()` du moteur
appliquent les mêmes règles avec les mêmes codes. Une violation ne porte que
`code`, `date`, `slot`, `s` : **jamais de texte libre, jamais de type
d'absence**. Les deux sont éprouvées sur `planning/tests/cas_verification.json`
(`data_commune` = jeu fictif, plus une clé `data` facultative par cas) ; une
divergence est un test rouge des deux côtés, et le jeu doit émettre chaque code
au moins une fois.

| Code | Règle |
|---|---|
| `hors_plage` | date invalide ou hors `meta.debut → meta.fin` (briques, fériés, notes) |
| `salariee_inconnue` | `s` absent de `salaries[]` |
| `slot_inconnu` | slot ni praticien ni `secretariat` / `sureffectif` / `administratif` |
| `brique_invalide` | `t` hors {J, C}, objet malformé, tableau attendu |
| `doublon_jour` | deux briques d'une même personne le même jour |
| `jour_bloque` | congé bloquant, cours, ou **tout** férié effectif (samedi compris), fériés de la page compris et fériés rouverts exclus |
| `jour_non_affiche` | slot non praticien un jour hors des colonnes affichées (dimanche, jour sans présence ni jour fixe) |
| `sans_donnees` | slot praticien un jour de `meta.non_couverts` |
| `praticien_absent` | slot praticien un jour où il n'est pas présent (hors férié, qui relève de `jour_bloque`) |
| `capacite` | plus d'éléments dans la case du praticien que son `attendues` (éléments illisibles compris, comme le gabarit) |
| `exclusive_ailleurs` | assistante exclusive sur une case **praticien** autre que son binôme |
| `exclusif_intrus` | assistante non binôme chez un praticien exclusif |
| `quota_depasse` | briques hors `x` d'une semaine au-delà de la réserve (`reserve(s, week).over > 0`) ; c'est ici seulement que les fériés ne consomment une brique que du lundi au vendredi |

Décision notée : **l'exclusivité stricte ne porte que sur les cases
praticien**. Le moteur du skill pose le reliquat de toute assistante en
sureffectif, exclusives comprises (étape 5 de `proposer`) ; flaguer ce cas
rendait sa propre proposition inenregistrable. Le cas
`exclusive_en_sureffectif_admise` fige cette lecture.

`place()` applique les mêmes refus au dépôt manuel (plus `autre_semaine`, code
d'interface pour un déplacement entre semaines, et la bascule en sureffectif
quand le praticien est pourvu). Contrairement au gabarit, il refuse aussi une
brique un jour de cours et une exclusive hors de son binôme.

## 6. Versions

`planning.PlanningVersion` : `mois`, `numero`, `state`, `version_de_base`,
`auteur`, `cree_le`, `verifications`, `publiee`, `publie_le`, `publie_par`.
Contrainte unique `(mois, numero)`, jamais modifiée ni supprimée
(administration en lecture seule). Les champs de publication, créés en 4a,
sont vivants depuis la 4b : `services.publier` (§ 11.1) pose `publiee`,
`publie_le`, `publie_par` et `verifications` sur la ligne existante, jamais
sur une nouvelle. Plusieurs versions d'un même mois peuvent porter
`publiee=True` ; la version publiée du mois est la dernière par `numero`.
Aucune dépublication.

`verifications` vaut `[]` tant que la version n'est pas publiée (toute
violation refuse l'enregistrement, il n'y a rien à consigner). À la
publication, c'est le compte-rendu du contrôle réussi sur `DATA` recalculé :

```
{"verifie_le": "<ISO>", "imports": [{"id": <pk>, "empreinte": "<empreinte de l'import>"}, …], "nb_briques": <n>}
```

`imports` est recopié de `DATA.meta.imports` (§ 2) : l'identité des imports de
présences qui faisaient foi au moment de la publication. Ni nom, ni type
d'absence.

`version_de_base` est non nul depuis la migration `planning.0002` (brique 4b,
C4.10) : `PositiveIntegerField(default=0)`, 0 = aucune version affichée. La
migration remplit d'abord les `NULL` à 0 par `RunPython` (nécessaire avant
l'`AlterField` sur PostgreSQL, qui refuse un `NULL` restant), puis pose le
`NOT NULL` ; le service l'avait toujours posé, 0 ligne touchée en production.
Une écriture nulle est refusée (`test_version_de_base_jamais_nulle`).

`planning/services.py::enregistrer(mois, version_de_base, state, qui)` :

1. lit le dernier numéro ; s'il diffère de `version_de_base`, `Conflit` (409) ;
2. nettoie le `state`, calcule `DATA`, vérifie ; une violation, `Invalide`
   (422), rien n'est écrit ;
3. insère `numero + 1` dans `transaction.atomic()` ; l'`IntegrityError` de la
   contrainte unique (deux workers, même base) est attrapée **hors** du bloc,
   puis le dernier numéro est relu pour répondre 409. `select_for_update` est
   proscrit (SQLite en développement) ; c'est le patron de
   `presences/verrou.py` ;
4. journalise `planning_enregistre` avec `mois`, `numero`, `nb_briques`. Ni nom
   ni type d'absence, ici comme dans les logs.

Contrat de l'API : corps `{version_de_base, state}` ; 201 `{numero}` ; 409
`{derniere}` ; 422 `{violations: [{code, date, slot, s}]}` ; 400 sur un corps,
un mois ou une base illisibles ; 405 hors POST ; 413 au-delà d'un méga-octet.
Le test « deux enregistrements de même base → un 201, un 409, jamais 500 »
bouchonne la première lecture du numéro courant pour simuler le worker en
retard.

## 7. Copie autonome, export, import

**Copie** : `GET /planning/<mois>/copie/` rend `copie.html`, un document
complet avec `DATA` recalculé, le `state` de la **dernière version
enregistrée**, et les trois statiques inlinés. La vue les lit à la source par
`django.contrib.staticfiles.finders.find`, pas par l'URL hachée du manifeste,
et refuse un fichier qui contiendrait une séquence de fermeture de balise.
Réponse en `Content-Disposition: attachment`, nom
`planning-assistantes_<mois>_v<numero>.html`. En mode `autonome`, la page
masque les boutons d'API et désactive `beforeunload`.

**Export JSON** (`moteur.exporter`) : `mois`, `numero`, les quatre clés, et
`exporte`. Ni congé, ni cours, ni type d'absence : la structure est figée par
`planning/tests_js/export.test.js`.

**Import** (`moteur.importer`) : accepte un export JSON ou une copie HTML (bloc
`planning-state`), ne reprend que les quatre clés, jour par jour dans la plage,
et ignore en les comptant les briques d'une salariée inconnue ou d'un type
illisible. C'est le chemin de reprise du planning de référence en recette.
Depuis la 4b, il rend `{jours, ignorees, orphelines}` : `orphelines` compte,
sur les jours affichés, les briques reprises sur une case que la journée ne
dessine pas (praticien absent ce jour-là) — chargées quand même, et rendues
visibles par la ligne « hors présence » (§ 11.4).

## 8. `/api/erreurs/`

`window.onerror` et `unhandledrejection` de la page envoient `{nom, source,
ligne, mois}`, jamais `error.message` (un message peut embarquer un fragment de
donnée). Le serveur tronque à 80 caractères, journalise en `ERROR` et ne
stocke rien. Décorateurs dans l'ordre `limite_par_ip` puis `role_requis` : un
appelant qui martèle la route ne la fait pas travailler. Le plafond est la
constante `DEBIT_ERREURS_IP` de `settings.py`, pas une variable
d'environnement.

## 9. Confidentialité : amendement C4.1

Le type d'absence est une donnée de santé. Décision du 06/09/2026 (C4.1) :
`DATA.conges[].type` porte le libellé pour les rôles `cabinet` et
`principale`, **à l'écran et dans la copie HTML**, et nulle part ailleurs.
Toute la mise en forme passe par `donnees.libelle_conge()` : revenir à un code
neutre tient en une ligne. Le cadrage doit amender son § 1.2 en conséquence.

`planning/tests/test_confidentialite.py` couvre sept surfaces : le `state`
reçu nettoyé, `PlanningVersion.state`, l'export JSON (figé côté Node), le
journal d'audit, les logs des vues et du service, le corps de `/api/erreurs/`,
et les absences hors périmètre absentes de `DATA` ; plus les rôles (403 pour
une salariée, 302 pour un anonyme).

La brique 4b y ajoute trois tests : la publication (`verifications`, audit,
logs et webhook `planning.publie` sans nom ni type), « Mes jours » (la page ne
reçoit pas `DATA` : aucun type, aucune autre salariée) et le conflit (audit
`absence_conflit_publication`, webhook `absence.conflit`, logs : ni type, ni
précision, ni nom). Côté `absences/tests/test_confidentialite.py`,
`test_le_conflit_ne_journalise_ni_type_ni_precision` tient le même engagement
depuis le crochet.

## 10. Tests

- **Python** : `.venv/Scripts/python.exe -m pytest` — `planning/tests/` porte
  la fabrique du jeu fictif (`fabrique.py`, le même jeu que la fixture Node),
  et les recettes des données, de la vérification, des versions, des pages, de
  la copie, des erreurs, de la confidentialité et, depuis la 4b, de la
  publication (`test_publication.py`), du conflit (`test_conflits.py`) et de
  « Mes jours » (`test_mes_jours.py`) ; depuis la 7a, de l'import historique
  (`test_import_historique.py`, avec la fixture
  `tests/fixtures/import_historique_fictif.json`). `conftest.py` substitue les
  règles fictives aux règles du dépôt pour les tests de vue.
- **Node** : `node --test "planning/tests_js/**/*.test.js"` — module intégré
  `node:test`, aucun `package.json`, aucun `npm`. Le motif glob entre
  guillemets est développé par Node lui-même (v21 et plus).
- **Pont** : `planning/tests/test_node.py` lance la même commande par
  `subprocess` si `node` est sur le poste ; sinon le test est sauté avec le
  message « tests JS non exécutés : node absent ». Dans l'image Docker
  (`python:3.14-slim`, sans Node), les tests JS ne tournent donc pas.

Totaux au 08/09/2026 (post-squash `95e6ba9`) : **917 tests Python** (+43 en
7a) et **57 tests Node**, inchangés depuis la 4b (+2 alors : `orphelins`, et
l'import qui compte les briques orphelines sans les écarter, dans
`moteur.test.js`). La 7a ne touche pas au moteur.

### Fixture de référence

`planning/tests_js/fixtures/proposition_attendue.json` fige la proposition que
le **gabarit d'origine** calcule sur le jeu fictif ; le test
`initialState reproduit la proposition de référence` compare le nouveau moteur
à ce fichier. Sans lui, le test comparerait le moteur à lui-même. Le gabarit
d'origine ne tourne pas sous Node (il touche le DOM au chargement) : la
fixture a été produite une fois, à la main.

Procédure, si le jeu fictif change :

1. remplir le gabarit d'origine avec `data_fictif.json` à la place de
   `__PLANNING_DATA__` et l'état vide du générateur à la place de
   `__PLANNING_STATE__` (hors dépôt) ;
2. l'ouvrir **une seule fois** dans Chrome : la proposition se pose au
   chargement ; **ne rien déplacer** ; cliquer « Exporter JSON » ; fermer ;
3. ne pas le rouvrir (le brouillon `localStorage` reprendrait la main) ;
4. reprendre `affectations` de l'export dans la fixture, avec la provenance
   (date, navigateur) dans `_provenance`.

## 11. Publication (brique 4b)

Publier, c'est poser `publiee`, `publie_le`, `publie_par` et `verifications`
sur la **dernière version** du mois (C4.5). Pas de copie figée, pas de
nouvelle ligne, pas de dépublication : une correction est une nouvelle
version, publiée à son tour, qui supersède la précédente.
`services.version_publiee(mois)` rend la dernière `publiee=True` par
`numero`, ou `None`.

### 11.1 Route et service

`POST /api/planning/<AAAA-MM>/versions/<n>/publier/` — rôles `cabinet` et
`principale`, même session et même CSRF que l'enregistrement, corps ignoré,
numéro explicite dans l'URL. Réponses :

| Code | Corps | Quand |
|---|---|---|
| 200 | `{numero, publie_le}` | publiée |
| 200 | `{numero, deja_publiee: true}` | déjà publiée : rien n'est écrit, aucun audit |
| 409 | `{derniere}` | `<n>` n'est pas (ou plus) le dernier numéro du mois, ou le mois n'a aucune version |
| 422 | `{violations: [{code, date, slot, s}]}` | la revérification trouve une règle enfreinte ; rien n'est écrit |
| 400 | `{erreur: "mois_invalide"}` / `{erreur: "numero_invalide"}` | mois illisible ; `<n>` = 0 |
| 405 | `{erreur: "methode_non_autorisee"}` | hors POST |

`planning/services.py::publier(mois, numero, qui)`, dans cet ordre :

1. garde : `courant = numero_courant(mois)` ; si `courant == 0` ou
   `numero != courant`, `Conflit(courant)` (409) ;
2. `PlanningVersion.objects.get(mois=mois, numero=numero)` ; si `publiee`,
   `DejaPubliee` (200 `deja_publiee`) ;
3. revérification : `verifier(donnees.construire(mois), version.state)` sur
   `DATA` **recalculé** — une absence devenue effective ou un mouvement Doctolib
   depuis l'enregistrement est attrapé ici (C4.6) ; une violation, `Invalide`
   (422), rien n'est écrit. Le `state` en base est déjà nettoyé ;
4. écriture en **une seule instruction** `UPDATE … WHERE pk = … AND NOT publiee
   AND NOT EXISTS (version de numéro supérieur)` — en Django
   `filter(pk=…, publiee=False).exclude(Exists(plus_recente)).update(…)` :
   ni `select_for_update`, ni transaction, la condition SQL est le seul point
   de sérialisation, comme la contrainte unique de 4a. Zéro ligne touchée →
   relecture, puis `DejaPubliee` ou `Conflit(numero_courant)` ;
5. audit `planning_publie` avec `mois`, `numero`, `nb_briques` ; log
   « planning AAAA-MM : version N publiee (N briques) » ;
6. webhook `planning.publie` (§ 11.5), qui ne lève jamais.

### 11.2 Dans la page

Le bloc `planning-meta` porte `publiee` (numéro de la version publiée
courante, 0 sinon) et `urls.publier` (posée seulement s'il existe une version).
L'en-tête dit « Version N · publiée » quand la version affichée est la publiée,
« Version N · publiée : vP » sinon.

Le bouton **Publier** n'est actif que si la page affiche la dernière version
sans modification et qu'elle n'est pas déjà publiée (`META.publiee ===
META.numero`) ; en mode autonome il est désactivé comme les autres boutons
d'API. `publier()` demande confirmation, applique d'abord `M.verifier()` — une
violation locale donne « Publication refusée par la page » sans appel —, puis
`POST` sur `META.urls.publier`. Un 200 pose `META.publiee` et un toast
(« publiée » ou « déjà publiée ») ; un 409 donne le bandeau de conflit en
variante publication (« Recharger » seul, sans « Exporter JSON » : il n'y a
rien à sauver) ; un 422, « Publication refusée par le serveur » avec les cases
surlignées ; une réponse redirigée ou non JSON, le bandeau de session expirée.

Après un enregistrement réussi (201), `page.js` recalcule
`META.urls.publier = <urls.versions><numero>/publier/` : la route suit le
numéro, et sans rechargement le bouton doit viser la version que l'on vient
d'enregistrer (trou du plan, comblé au checkpoint diff).

### 11.3 « Mes jours »

`GET /mes-jours/` (mois courant) et `GET /mes-jours/<AAAA-MM>/`, rôles
`salariee` et `principale` (pour elle-même) ; `cabinet` reçoit 403 ; un compte
sans personne rattachée voit un message, jamais un 500. Gabarit
`planning/templates/planning/mes_jours.html`, minimal et non stylé (la version
adaptée au téléphone est en backlog).

`services.jours_publies(personne, mois)` lit le `state` des versions publiées
et les personnes, **jamais `DATA`** (qui porte les congés de toutes les
salariées). Sans version publiée du mois : `None`, et la page dit que le
planning n'est pas encore publié. Sinon (C4.8) :

- **la plage entière** de la version publiée du mois (semaines complètes), les
  jours d'un mois voisin en italique avec la mention du planning qui les porte ;
- **le mois calendaire est prioritaire** : pour une date que la version publiée
  du mois voisin porte aussi, celle du mois calendaire de la date fait foi
  (`source_numero` le dit) ;
- chaque ligne : `{date, t, x, slot, slot_libelle, hors_mois, source_numero}` ;
  `t` s'affiche « journée » ou « journée courte (fin 16h30) », `x` ajoute
  « (heures sup) » ;
- **libellés** : `Secrétariat`, `Sureffectif`, `Administratif` (`LIBELLES_MISC`,
  recopie du troisième élément de `MISC` du moteur), sinon le praticien du slot
  (`str(Personne)`, sans filtre `actif` : un praticien parti après la
  publication garde son libellé), sinon le slot brut.

Ni congé, ni note, ni férié, ni type d'absence. Le log ne porte que le mois et
un comptage (« mes jours AAAA-MM : N jour(s) »). L'accueil des rôles
`salariee` et `principale` a reçu le lien « Mes jours ».

### 11.4 Ligne « hors présence » (C4.9)

Écart E1 de R4a-1 : une brique posée sur un praticien absent ce jour-là (le
planning vécu, importé après un mouvement Doctolib) donnait une violation
`praticien_absent` que l'utilisatrice ne pouvait pas corriger, la case
n'étant pas dessinée.

`moteur.orphelins(iso)` rend les slots à briques que la journée ne dessine
pas : praticien absent ou jour fermé, slot inconnu — jamais une case `MISC`.
`page.js` dessine pour chacun une case `slot prat orphelin` (« hors présence ·
absent ce jour-là », « jour fermé » ou « inconnu ») : brique visible, retirable,
déplaçable, **jamais une cible de dépôt** (pas de `dropHandlers`). Aucun
nettoyage automatique. `importer` compte ces briques dans `orphelines`, sur
les jours affichés seulement, et le toast d'import les annonce ; un jour hors
colonnes portant une brique orpheline reste au chemin export JSON (backlog).

### 11.5 Webhook `planning.publie`

`planning/webhooks.py::notifier_publication(version, nb_briques)` poste sur
`N8N_PLANNING_WEBHOOK_URL`, en-tête `X-Webhook-Secret` (secret partagé
`N8N_WEBHOOK_SECRET`), par `socle.client_n8n`, fail-closed. Corps :

```
{evenement: "planning.publie", mois, numero, nb_briques, publie_par_id, lien, horodatage}
```

Ni nom, ni type d'absence, ni `state`. Le module n'importe pas `services`
(c'est `services` qui l'importe) : le comptage lui est passé. La variable
**n'est pas posée** sur Railway : le workflow n8n est la brique 5 ; d'ici là,
chaque publication journalise « webhook planning non configure », et un
webhook muet ou en échec n'empêche jamais une publication.

## 12. Conflit avec une absence (brique 4b)

Une absence n'entre dans le planning qu'une fois effective. Si la version
publiée d'un mois pose déjà une brique de la salariée sur un de ces jours, le
planning publié est faux ce jour-là. Deux ordres, deux gardes : une absence
devenue effective **avant** la publication est refusée à la publication (422,
§ 11.1, C4.6) ; **après**, elle est signalée (C4.7). Le conflit est calculé à
la demande, jamais stocké, et **ne bloque rien** : l'absence est écrite dans
tous les cas.

**`planning/conflits.py`** — deux fonctions pures et une lecture :

- `conflits_dans_state(state, sid, dates)` : les dates de `dates` où `state`
  pose une brique de `sid`, **tout slot** (praticien, secrétariat,
  sureffectif, administratif), hors quota compris — une brique est une
  journée due par la salariée ;
- `mois_candidats(date_debut, date_fin)` : les mois « AAAA-MM » dont la plage
  (semaines complètes) touche l'intervalle — les mois calendaires couverts et
  leurs voisins immédiats, filtrés par `plage_mois` ;
- `conflits(personne, date_debut, date_fin, versions=None)` : pour chaque mois
  candidat, lit `version_publiee(mois)` (cache facultatif `versions`, partagé
  par l'écran de décision pour ne lire chaque version publiée qu'une fois) et
  rend `[{mois, numero, dates}]`, un élément par mois publié en conflit.

**Le crochet `absences.services.signaler_conflits(absence, qui)`** — sur la
**transition** vers l'état effectif seulement, quel que soit le chemin :

| Chemin | Signale |
|---|---|
| `creer` — déclaration (type `declare`, effective immédiatement) | oui |
| `decider` — validation d'une demande | oui |
| `admin.save_model` — création en statut effectif, ou changement de `statut` vers un statut effectif | oui |
| refus, annulation, correction des jours comptés | non |
| modification des dates, du type ou de la précision d'une absence **déjà** effective | non (limite assumée, C4.7) |

Types **bloquants** seulement (`type.bloquant`). Le crochet vient **après**
`save()`, l'audit et le webhook de l'absence, et ne lève jamais. Pour chaque
conflit : audit `absence_conflit_publication` (`personne_id`, `mois`,
`numero`, `dates`) ; puis, s'il y en a au moins un, log « absence #N en
conflit avec N planning(s) publie(s) » et webhook `absence.conflit` sur l'URL
des absences (corps de l'absence + `conflits: [{mois, numero, dates}]`, voir
`docs/ABSENCES.md` § 7). Ni slot, ni nom, ni type.

**`/absences/`** recalcule les conflits au rendu (semaines complètes, comme le
planning — la paie seule est calendaire) sur les absences effectives de type
bloquant : bandeau « N absence(s) tombe(nt) sur un jour du planning publié » et
marqueur « conflit : AAAA-MM vN (dates) » sur la ligne, avec lien vers la page
du mois.

**Cycle d'import (C4.13)** : `planning.conflits` importe `services` et
`donnees`, donc `absences.services`. C'est `absences/` (`services`, `views`)
qui importe `planning.conflits` **dans la fonction**, jamais en tête de module
(patron `presences/verrou.py`). De même `planning/webhooks.py` n'importe
jamais `services`.

**Un onglet ouvert est un instantané** : le `DATA` d'une page rendue avant la
saisie d'une absence ne la voit pas ; la brique posée dessus est refusée par
le serveur (422) à l'enregistrement — troisième cas vu en recette, qui montre
que la double vérification n'est pas redondante. Règle d'usage : recharger le
planning après toute saisie d'absence, jusqu'à ce que la page se rafraîchisse
seule (backlog).

## 13. Import d'un planning historique (brique 7a)

### 13.1 Pourquoi

Décision **C7.1** : les plannings de janvier à août 2026 sont antérieurs à
l'application. Ils ont été reconstitués hors de l'application depuis les
entrées « Présence » de Notion, au format de l'export JSON de la page, et
entrés par un écran d'administration. Ces mois n'ont **aucune présence
Doctolib importée**, et n'en auront pas nécessairement : les présences sont
optionnelles ici. Conséquence directe de **C6.9** : aucun marqueur d'effectif
n'est calculable sur un mois historique tant que ses présences ne sont pas
importées — `verifications.imports` reste vide.

Les huit mois de janvier à août 2026 ont été importés en production le
08/09/2026.

### 13.2 Qui et où

`/admin/planning/planningversion/importer-historique/`, bouton **« Importer un
planning historique »** dans les outils de la liste des versions (bloc
`object-tools-items` de `admin/planning/planningversion/change_list.html`).

Rôle `cabinet` : dans `PlanningVersionAdmin.get_urls`,
`role_requis(Compte.Role.CABINET)` enveloppe `self.admin_site.admin_view(…)`
**par l'extérieur** — un autre rôle reçoit le 403 journalisé du projet
(`acces_refuse`, `{"vue": "vue_import_historique"}`), pas la redirection de
connexion de l'admin ; `admin_view` conserve la protection CSRF, `never_cache`
et l'exigence `is_staff`. Aucune garde `is_superuser`. La route est déclarée
**avant** `super().get_urls()`, sinon `<path:object_id>/` la capturerait.

Les trois `has_*_permission` restent à `False` : la liste des versions demeure
en lecture seule. Elle gagne seulement une colonne « historique », calculée par
`services.est_historique` — pas un champ, donc pas un filtre.

### 13.3 Le fichier

Format de l'export JSON de la page (`moteur.exporter`, § 7) : `mois`, `numero`,
`affectations`, `feries`, `feries_off`, `notes`, `exporte`. `numero` et
`exporte` sont **acceptés et ignorés** — le numéro est décidé par le serveur.
Une brique est `{a, s, t, x}` (§ 3), un slot un code de praticien ou
`secretariat` / `sureffectif` / `administratif`. Un fichier couvre les
**semaines complètes** du mois, la plage de `presences.fenetres.plage_mois` :
les jours de bord sont partagés avec le fichier du mois voisin, et c'est normal.

`planning/forms.py::FormulaireImportHistorique` ne juge que l'enveloppe :

| Contrôle | Message |
|---|---|
| taille, 1 Mo au plus | « Fichier trop volumineux (maximum 1 Mo). » |
| extension | « Le fichier doit porter l'extension .json. » |
| encodage, `utf-8-sig` (BOM toléré) | « Le fichier doit être encodé en UTF-8. » |
| JSON | « JSON illisible. » |

La **structure** est contrôlée par `historique.analyser`, dont les messages ne
citent que la date, la colonne et le rang de la brique, jamais une valeur :
« Champ « mois » absent ou illisible (attendu « AAAA-MM ») »,
« 2026-03-03 / « secretariat » / brique 2 : champ « t » hors J | C ».

**Colonnes sur fiches fermées (C7.4)** : la résolution des codes lit
`Personne.objects.exclude(code=None).exclude(code="")`, **sans aucun filtre
`actif` ni `planifiee`**. Une colonne portée par une fiche close, non
planifiée, sans agenda Doctolib est **conservée**, avec l'avertissement
« Colonne « … » : fiche close — colonne conservée (C7.4) ». C'est l'inverse de
`donnees.construire` (§ 2), qui filtre `planifiee=True, actif=True` : ces
praticiens n'apparaissent pas sur la page d'un mois courant, et doivent
apparaître dans un planning de 2026.

### 13.4 Les deux temps

**Analyser** — `historique.analyser(fichier)` rend une `Analyse` et **n'écrit
rien** : ni base, ni audit, ni log. Le rapport porte le mois et sa plage, le
nombre de jours porteurs et de briques, la table des **colonnes** (slot,
libellé, nature, briques, personnes, état de la fiche), celle des
**personnes** (code, libellé, jours, briques), les avertissements et les
refus. Verdicts : `creer` (« à importer »), `deja_presente` (« déjà présente »),
`refuse` (« refusé »).

| Bloquant | Non bloquant |
|---|---|
| code de personne inconnu, en colonne ou en brique | jour fermé ou férié porteur de briques |
| jour hors de la plage du mois | colonne sur fiche close ou non planifiée |
| même personne posée deux fois le même jour | |
| fichier sans aucune brique, ou de forme invalide | |

**Confirmer** — l'état vit en session (`import_planning_historique`), jamais
sur disque, avec l'empreinte et un horodatage ; il périme au bout de **15
minutes** (`IMPORT_SESSION_MINUTES` ; `_perime` et `_entier` sont recopiés de
`absences/admin.py`, décision D10). À la confirmation, **l'analyse est
rejouée** sur le fichier gardé en session, et l'écriture est refusée si le
verdict, l'empreinte ou le nombre de briques a bougé : « La base a changé
depuis l'analyse : relisez le rapport avant de confirmer. » Une version
enregistrée depuis un autre onglet entre les deux POST est ainsi attrapée.

### 13.5 Mois déjà versé (décision D1)

`analyser` lit **toutes** les versions du mois, pas seulement la dernière :

| État du mois | Verdict |
|---|---|
| une version **non historique**, quel que soit son rang | refus — « Ce mois porte déjà une version enregistrée dans l'application (vN) : l'import historique est refusé. » |
| que des versions historiques, la dernière de **même empreinte** | « déjà présente » : `executer` rend `None`, zéro écriture, zéro audit |
| que des versions historiques, état différent | `creer` : `numero` = numéro courant + 1, `version_de_base` = numéro courant |

**L'empreinte porte sur `(mois, state)` sérialisé canoniquement**
(`historique.empreinte_de`, `sort_keys`, séparateurs compacts), pas sur les
octets reçus : un ré-export du même planning change `exporte` mais reste
reconnu « déjà présente ». L'ordre des briques d'une journée, lui, est
significatif et conservé.

Une version historique **ne se supprime pas** — `PlanningVersion` est en
lecture seule. Elle se corrige par une version suivante, publiée à son tour,
qui supersède la précédente (§ 6).

### 13.6 Ce qui est écrit

`historique.executer(analyse, qui)` crée **une** ligne dans
`transaction.atomic()`, l'`IntegrityError` de la contrainte unique
`(mois, numero)` attrapée **hors** du bloc (patron d'`enregistrer`, § 6) :
`publiee=True`, `publie_le`, `publie_par`, `auteur`, `state` nettoyé par
`verification.nettoyer`, et

```
{"historique": true, "importe_le": "<ISO>", "empreinte": "<sha256>", "imports": [], "nb_briques": <n>, "nb_jours": <n>}
```

**Pas de clé `verifie_le`** (décision D2) : rien n'a été vérifié, et l'écrire
serait faux. `services.est_historique(version)` lit ce marqueur avec une garde
de type, `verifications` valant `[]` tant qu'une version n'est pas publiée.

Le chemin est **entièrement distinct de `services.publier`**, qui n'est pas
modifié :

- **aucune revérification des règles.** Sans import de présences, `DATA.jours`
  est vide (§ 2) et *toutes* les briques deviendraient `praticien_absent` ou
  `sans_donnees`. La règle n'est pas contournée : elle est sans objet, et
  l'écran le dit en toutes lettres ;
- **aucun webhook** (C7.6). Importer mars 2026 ne doit pas déclencher
  l'événement `planning.publie` (§ 11.5) quand la brique 5 existera. Cela
  s'obtient en ne passant pas par `publier`, pas en le modifiant.

**Audit** : un seul événement par import (décision D4),
`planning_historique_importe`, `{mois, numero, nb_briques, nb_jours,
empreinte}` — jamais un nom, jamais un code de personne, jamais le `state`. Le
log dit « planning historique AAAA-MM : version N importee (N briques, N
jours) ». Les codes de personnes n'apparaissent **qu'à l'écran d'analyse**,
pour le cabinet : ils sont nécessaires pour corriger un fichier.

### 13.7 Après l'import

- **« Mes jours » fonctionne tel quel**, sans une ligne de changement :
  `jours_publies` (§ 11.3) ne lit que le `state` publié et les personnes,
  jamais `DATA`, et interroge les praticiens **sans filtre `actif`** — le
  libellé d'un praticien dont la fiche est fermée est conservé.
- **La page `/planning/<AAAA-MM>/` d'un mois historique rend encore
  `sans_import.html`** : `planning_mois` teste `donnees.mois_couvert(plage)`,
  faux sans aucun import de présences, et ne sait rien des versions
  historiques. Elle ne pourrait pas servir non plus : sans `DATA.jours`, le
  moteur ne dessine aucune colonne de praticien (`SHOWN`, `moteur.js`) et
  toutes les briques passeraient en « hors présence » (§ 11.4).
- **À venir (brique 7b)** : une page de lecture dédiée
  `/planning/<AAAA-MM>/historique/` construite depuis le `state` seul, le lien
  qui y mène depuis `sans_import.html`, et `copie` → 404 sur un mois
  historique — aujourd'hui elle rendrait une copie au moteur vide.

### 13.8 Limites

- Un **jour ouvert exceptionnellement** un dimanche ou un férié est importé
  sans perte — l'analyse se contente d'avertir —, mais la page ne le
  dessinerait pas : `moteur.js` ne montre jamais le dimanche et tient un férié
  pour fermé du lundi au vendredi. À cadrer avec la 7b.
- **Aucun marqueur d'effectif** (C6.9) sur un mois historique :
  `verifications.imports` est vide, il n'y a pas de présences sur quoi les
  calculer. Un tableau de bord ne doit donc pas lire un tel mois comme
  « données Doctolib manquantes ».
- L'écran **n'a plus de source** une fois 2026 repris : le garder ou le retirer
  en v2 est au backlog, comme celui de la 3-quater.

**Procédure recommandée** : relire le fichier, puis faire un pilote sur un seul
mois — analyser, confirmer, puis rejouer le même fichier pour voir « déjà
présente » et zéro écriture — avant d'enchaîner les autres.
