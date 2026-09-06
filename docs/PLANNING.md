# Planning — architecture de la brique 4a

La page `/planning/<AAAA-MM>/` remplace le fichier HTML autonome du skill v1 :
les données (`DATA`) sont calculées par le serveur à chaque affichage, l'état
du planning (`STATE`) est enregistré en base sous forme de versions numérotées,
et la logique de proposition et de règles reste dans le navigateur (décision
C2.2). Le gabarit du skill a été **porté**, pas copié : `reference/skill-v1/`
reste la référence historique, non exécutée et exclue de l'image Docker.

État au 06/09/2026 : brique 4a mergée (`5072226`), déployée et recettée
(imports, trois versions successives, un 409 obtenu en production, refus par la
page d'une brique sur un praticien absent). Critère différé R4a-1 : import du
planning réel de septembre, en attente du fichier enregistré au cabinet.

## 1. Routes et rôles

| Route | Rôle | Ce qu'elle fait |
|---|---|---|
| `GET /planning/` | `cabinet`, `principale` | redirige vers le mois courant |
| `GET /planning/<AAAA-MM>/` | `cabinet`, `principale` | la page ; sans aucun import réussi sur la plage, un écran « aucun import » renvoie vers `/presences/importer/` |
| `GET /planning/<AAAA-MM>/copie/` | `cabinet`, `principale` | copie HTML autonome de la dernière version (404 s'il n'y en a aucune) |
| `POST /api/planning/<AAAA-MM>/versions/` | `cabinet`, `principale`, session + CSRF | enregistre une version : 201, 409 ou 422 |
| `POST /api/erreurs/` | plafond par IP, puis `cabinet`, `principale` | journalise une erreur JS de la page, sans rien stocker |

Le contrôle de rôle est `comptes.acces.role_requis` : un anonyme est redirigé
vers `/connexion/`, un autre rôle reçoit 403. `page.js` teste `redirected` et
le `Content-Type` d'une réponse d'API avant de la lire : une session expirée
donne un bandeau, pas un JSON cassé.

## 2. `DATA` : ce que le serveur calcule

`planning/donnees.py::construire(mois)` rend le dictionnaire que la page lit,
au contrat du gabarit du skill (`build_planning.py`, § 3 à 6), à partir des
tables de l'application. Les seules clés nouvelles sont `meta.non_couverts`,
`meta.alertes` et `attentes` ; l'ancien code les ignore.

| Clé | Source | Notes |
|---|---|---|
| `meta` | `presences.fenetres.plage_mois` (semaines complètes), règles, imports | `genere` en ISO, `source = "app"`, `heures` et `seuils` (du premier import couvert, sinon 4 h / 5 h et une alerte), `enveloppes` (messages des imports retenus), `non_couverts` (dates de la plage sans import réussi), `alertes` (textes destinés à l'écran) |
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
`peutAnnuler`), les sérialisations (`exporter`, `charge`, `empreinte`) et la
vérification stricte (`verifier`).

**Règle unique de mutation** : aucune fonction du moteur n'appelle `commit`,
`render`, `toast` ni `confirm`. Le moteur mute et rend des résultats
(`place` rend `{ok, code, cible, bascule}`) ; `page.js` enchaîne toujours
`M.x(); commit();`. Un test Node lit la source du moteur et refuse `document.`,
`toast(`, `confirm(`, `render(`, `commit(`, `alert(`, `localStorage`.

**`planning/static/planning/page.js`** — rendu, glisser-déposer, toasts,
boutons, raccourcis, appels d'API, `beforeunload` (si l'empreinte de l'état
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
`planning-state`, `planning-meta` (`{mois, numero, autonome, urls}`). Django y
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
(administration en lecture seule). Les champs de publication sont créés en 4a
et restent inertes jusqu'en 4b ; `verifications` est toujours vide en 4a et
servira à la revérification à la publication.

Hygiène à faire : `version_de_base` est nullable dans le modèle mais toujours
posé par le service (0 = aucune version) ; le rendre non nul est une migration
de forme, sans changement de comportement.

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

## 10. Tests

- **Python** : `.venv/Scripts/python.exe -m pytest` — `planning/tests/` porte
  la fabrique du jeu fictif (`fabrique.py`, le même jeu que la fixture Node),
  et les recettes des données, de la vérification, des versions, des pages, de
  la copie, des erreurs, de la confidentialité. `conftest.py` substitue les
  règles fictives aux règles du dépôt pour les tests de vue.
- **Node** : `node --test "planning/tests_js/**/*.test.js"` — module intégré
  `node:test`, aucun `package.json`, aucun `npm`. Le motif glob entre
  guillemets est développé par Node lui-même (v21 et plus).
- **Pont** : `planning/tests/test_node.py` lance la même commande par
  `subprocess` si `node` est sur le poste ; sinon le test est sauté avec le
  message « tests JS non exécutés : node absent ». Dans l'image Docker
  (`python:3.14-slim`, sans Node), les tests JS ne tournent donc pas.

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

## 11. Ce que la brique 4b ajoute

Publication d'une version (`publiee`, `publie_le`, `publie_par`, revérification
et remplissage de `verifications`), événement n8n de publication, crochet de
conflit absence ↔ planning publié dans `absences/services`, vue « mes jours
publiés » pour le rôle `salariee`, re-test sur le planning réel. La « version
publiée du mois » sera la dernière `publiee=True` par `numero`.
