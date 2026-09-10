# Interface — la coquille (brique 6a)

La brique 6 rhabille l'application par rôle sans toucher à la grille du
planning, au moteur, aux contrats `DATA` / `STATE`, aux règles ni aux droits
(décision C6.2 du cadrage). Elle est découpée en quatre sous-briques ; ce
document décrit la première, **6a « coquille »**, mergée le 10/09/2026
(`2e30150`, PR #26) et recettée en production le même jour. Les décisions
d'interface (C6.1 → C6.12) sont dans `docs/PLANNING_ASSISTANTES_CADRAGE.md` ;
le dossier de conception et les diff plans de la brique vivent hors dépôt.

## 1. Périmètre

| Sous-brique | Contenu | État |
|---|---|---|
| **6a — coquille** | `socle/base.html` (barre haute, menu avatar, onglets bas, messages), feuille de style commune, tableau de bord sur `/`, connexion à quatre états, pages 403 / 404 / 500, administration habillée, favicon | **livrée** (PR #26) |
| 6b — espace salariée | « Mes jours » en grille avec ses absences et les marqueurs d'effectif (C6.8, C6.9), « Mes absences », « Nouvelle absence », « Mon profil », premières règles de largeur (téléphone) | à venir |
| 6c — absences, présences & personnes | écran de décision, présences du mois et import, liste des personnes, mois en français dans les liens | à venir |
| 6d — enveloppe du planning | barre haute au-dessus de la barre d'outils, en-tête d'état, menu « Plus », bandeau « écran large » — `page.js` et la grille inchangés | à venir |

Ordre de livraison : 6d, puis 6b, 6c (cadrage).

Invariants de toute la brique 6 : `comptes.acces.role_requis` reste la seule
garde de rôle, les sept surfaces de `planning/tests/test_confidentialite.py`
restent vertes, aucune migration.

## 2. La coquille : `socle/templates/socle/base.html`

`base.html` est la racine de tous les gabarits d'app (la copie autonome du
planning, `planning/copie.html`, ne l'étend pas). Ses blocs, dans l'ordre :
`classe_html`, `titre`, `style_base`, `tete`, `classe_corps`, `en_tete_page`
(qui contient `entete`, le `h1` de la page), `contenu`, `navigation_page` (qui
contient `navigation`), `scripts`. Aucun bloc n'a été renommé en 6a.

**Règle d'isolement.** `planning/templates/planning/page.html` **vide**
`style_base` et `en_tete_page` pour imposer sa propre mise en page. Tout
balisage de coquille vit donc **dans l'un de ces deux blocs** — la feuille de
style dans `style_base`, la barre, les onglets, le menu et le `h1` dans
`en_tete_page` — et la page planning n'en reçoit rien. La seule exception
voulue est le favicon, posé dans `<head>` hors bloc, donc présent sur toutes les
pages. `socle/tests/test_navigation.py::test_page_planning_sans_coquille`
vérifie qu'un `/planning/<AAAA-MM>/` servi avec le jeu complet ne contient ni
`class="barre"`, ni `<details class="avatar"`, ni `socle/commun.css`, ni
`socle/polices.css`, et contient `socle/favicon.png` ;
`test_contexte.py::test_cout_page_planning` fige son nombre de requêtes (§ 3).

Ce que rend `en_tete_page` :

- **Barre haute** (`<header class="barre">`) : la marque « Espace K Dentaire
  · Planning » (lien vers `/`), puis, pour un compte connecté dont le rôle n'est
  pas `salariee`, les trois onglets **Planning** (`planning:courant`),
  **Absences** (`absences:decider`), **Présences & personnes**
  (`presences:courant`), l'onglet courant portant `aria-current="page"`.
  Toutes les conditions sont sur `user.role` ; `is_staff` n'apparaît nulle part
  dans le gabarit (il ne garde que l'administration).
- **Menu avatar** : un `<details class="avatar">` sans script, dont le
  `<summary>` porte les initiales. Le titre du menu est « Bonjour Prénom » si le
  compte est rattaché à une personne, sinon le libellé du rôle (« Cabinet »,
  « Assistante principale »). Entrées : « Mes jours » et « Mes absences » pour
  `principale` ; « Mon profil » pour tout rôle sauf `cabinet` ;
  « Administration » (`admin:index`) pour `cabinet` ; puis **la** déconnexion :
  un formulaire `POST` sur `comptes:deconnexion` (`/deconnexion/`), libellé
  « Déconnexion ». C'est le seul formulaire de déconnexion des pages de la 6a.
- **Sous-onglets** « Présences | Personnes » (`presences:courant`,
  `personnes:liste`), rendus seulement quand la page courante est une page de
  présences ou de personnes ; le sous-onglet courant est celui de l'app résolue.
- **Onglets bas** « Mes jours | Mes absences » pour le rôle `salariee`, sur
  toutes ses pages, quel que soit l'écran (règle par rôle, sans `@media`).
- **Titre de page** : `<div class="titre-page"><h1>{% block entete %}…</h1></div>`,
  rempli par chaque gabarit comme avant.

`<main>` rend les messages Django dans `<ul class="messages">` avec la classe
du niveau (`success`, `info`, `warning`, `error`, `debug` traité comme `info`),
stylés par `commun.css` ; puis `contenu`. Le `<nav>` de bas de page
(`navigation_page`) est inchangé : les gabarits qui n'ont pas encore été
rhabillés y écrivent toujours leurs liens (§ 10).

## 3. Processeur de contexte `socle.contexte.coquille`

Déclaré dans `config/settings.py` (`context_processors`), il fournit trois
variables à `base.html` :

- `nav_courante` — l'entrée à marquer courante, déduite de
  `request.resolver_match` (`app_name`, `url_name`) : `planning`, `mes_jours`
  (`planning:mes_jours*`), `absences`, `mes_absences` (`absences:mes_absences`,
  `nouvelle`, `annuler`), `donnees` (apps `presences` et `personnes`), `profil`,
  `tableau_de_bord` (`accueil`), ou `""` — y compris quand `resolver_match` est
  `None` (URL inconnue, page 404).
- `initiales` — « PN » pour Prénom Nom, sinon la première lettre du libellé du
  rôle.
- `prenom` — le prénom de la personne rattachée, sinon `""`.

**Garde** : sans attribut `user` (`RequestFactory`) ou pour un anonyme (page de
connexion, 403 / 404 anonymes), les deux dernières valent `""` et rien n'est
lu en base. **Paresse** : pour un compte connecté, `initiales` et `prenom` sont
des `SimpleLazyObject` — `user.personne` n'est interrogé que si un gabarit les
rend, et une seule fois (Django met la relation en cache). La page planning et
l'administration, qui ne rendent pas la barre, ne paient donc aucune requête ;
une page qui la rend en paie **une** de plus, et seulement pour un compte
rattaché (un `personne_id` nul ne déclenche rien).

Coûts figés par `socle/tests/test_contexte.py`, identiques à ceux d'avant la
brique : `/planning/2026-10/` avec le jeu complet **9** requêtes, sans import
**4**, `/admin/` **3**, `/connexion/` et un 404 anonyme **0**.

## 4. Page d'arrivée `/`

`socle/views.py::accueil` (`login_required`) : le rôle `salariee` est
redirigé vers `planning:mes_jours_courant` (`/mes-jours/`, C6.5) ; `principale`
et `cabinet` reçoivent `socle/tableau_de_bord.html`, dont le contexte est
assemblé par `socle/tableau_de_bord.py::construire(utilisateur, aujourd_hui=None)`
— une fonction pure, la date étant injectable pour figer l'horizon dans les
tests. Le `h1` est « Tableau de bord » ; la salutation ne vit que dans le menu.
Rien de nouveau n'est calculé : versions par `planning.services`, couverture
Doctolib par `presences.services.imports_par_date` (la sélection jour par jour
de `planning.donnees`), demandes par la requête de `/absences/`.

**Carte Planning** — « Présences Doctolib importées jusqu'au <date> », date =
`Max("fin")` des imports réussis, ou « Aucun import de présences réussi ».
Puis trois rubriques : **À venir** (mois postérieurs au mois courant ayant au
moins une version), **En cours** (le mois courant, toujours présent), **Passés**
(mois antérieurs ayant une version, repliés dans un `<details>`
« Passés (N mois) ») ; une rubrique vide n'est pas rendue. Chaque ligne porte
le mois en toutes lettres, une pastille d'état et « Ouvrir » :

| État | Pastille |
|---|---|
| aucune version | « Aucune version enregistrée » |
| version N, aucune publiée | « Version N · non publiée » |
| dernière version = version publiée | « Publiée (vN) » |
| version N postérieure à la publiée vM | « Version N — publiée : vM » |

« **Données Doctolib manquantes** » s'ajoute dès qu'**un jour** de la plage du
mois (semaines complètes, comme la page planning) n'est couvert par aucun import
réussi — **sauf** si la version publiée du mois est historique (C7.10) : ces
mois n'ont pas de présences Doctolib et n'en auront pas, et « Ouvrir » y mène à
`/planning/<AAAA-MM>/historique/` au lieu de la page normale. Le bouton
« Préparer un mois » ouvre le premier mois après le mois courant qui n'a aucune
version (sans import, la page planning affiche l'écran « aucun import »).

**Carte Demandes à décider** — la requête de `/absences/` (statut
`en_attente`, par date de début), tranchée aux **cinq** premières, avec la
pastille « N demande(s) » et « Voir tout » vers `/absences/` ; chaque ligne :
« Prénom Nom », type et dates ; « Décision réservée au cabinet » quand
`absences.services.peut_decider` refuse (règle K : la principale ne tranche pas
sa propre demande) ; vide : « Aucune demande en attente. ». Le type d'absence
y figure : seuls `principale` et `cabinet` atteignent cette page (C2.3b, C4.1).

**Carte Présences & personnes** — « Présences : dernier import #N le jj/mm
(début → fin) » (le dernier import réussi par date d'import), lien vers
`/presences/` ; « Personnes planifiées : N » (`planifiee` et `actif`, le filtre
de la page planning), lien vers `/personnes/` ; pour `cabinet`, le bouton
« Importer un fichier » vers `/presences/importer/`.

## 5. Connexion

`comptes/connexion.html` a quatre états : vide ; **envoyé** (réponse neutre,
inchangée) ; **bloqué** (429 par IP : le bandeau seul, sans formulaire) ;
**expiré** (`GET /connexion/?expire=1` : bandeau « Ce lien a expiré ou a déjà
été utilisé. Demandez-en un nouveau ci-dessous. » au-dessus du formulaire). Le
bouton s'appelle « Recevoir mon lien de connexion ».

Un lien magique refusé — absent, périmé, déjà utilisé, ou invalidé par un
changement d'adresse — ne donne plus un 403 : `VueConnexionLien.login_failed`
(`comptes/views.py`) journalise `connexion_refusee` comme avant, puis **redirige**
vers `/connexion/?expire=1`. La redirection est la même quel que soit l'échec,
et un `POST` sur `/connexion/?expire=1` rend exactement la même réponse qu'un
`POST` sur `/connexion/` : rien ne trahit un compte.

## 6. Pages d'état

`socle/templates/403.html` (« Vous n'avez pas accès à cette page ») et
`404.html` (« Cette page n'existe pas ») étendent `base.html` — Django rend ces
deux gestionnaires avec la requête, donc la barre s'affiche selon le rôle — et
terminent par le partiel `socle/_lien_arrivee.html` : « Aller à mes jours »
(`/mes-jours/`) pour `salariee`, « Aller à mon tableau de bord » (`/`) pour les
autres comptes, « Se connecter » (`/connexion/`) pour un anonyme. Jamais `/`
en dur.

`socle/templates/500.html` est **autonome** : `django.views.defaults.server_error`
le rend **sans requête ni contexte**, et une erreur dans ce gabarit ferait
échouer le gestionnaire lui-même. Il n'étend rien, n'utilise ni `{% url %}`, ni
`{% static %}`, ni `{% csrf_token %}`, ni `user` ; sa feuille de style est
inline. Texte : « Une erreur est survenue », « Réessayez dans un instant. »,
« Revenir à l'application » (lien `/`).

## 7. Administration

`socle/admin.py` n'enregistre aucun modèle ; il pose `admin.site.site_header`
(« Espace K Dentaire · Administration »), `site_title`
(« Administration · Espace K Dentaire »), `index_title` (« Administration ») et
`enable_nav_sidebar = False` — la barre latérale native (sa feuille et son
script) disparaît, l'index en blocs la remplace.

Deux gabarits de `socle/templates/admin/` portent le même nom que ceux de
Django et ne sont trouvés que parce que **`socle` précède `django.contrib.admin`
dans `INSTALLED_APPS`** (`config/settings.py`) : le chargeur de gabarits par
app suit cet ordre. Ne pas réordonner.

- `admin/base_site.html` : `<title>` sur `site_title` ; bloc `dark-mode-vars`
  vidé (plus de `dark_mode.css` ni de `theme.js` : thème clair seul, comme le
  reste de l'application) ; `extrastyle` ajoute `polices.css` et
  `administration.css` ; `extrahead` ajoute le favicon ; `branding` affiche
  `site_header` ; `userlinks` ne garde que « ← Retour à l'app » (`site_url`,
  soit `/`) et la déconnexion en `POST` sur `admin:logout` (capturée avant
  l'admin par `VueDeconnexionAdmin`, comme avant) ; `nav-global` vidé.
- `admin/index.html` **étend l'index natif du même nom** (Django saute le
  gabarit courant grâce à l'historique de `{% extends %}`) et ne redéfinit que
  `content` : cinq inclusions de `socle/_bloc_admin.html`, dans l'ordre
  `comptes`, `absences`, `planning`, `presences`, `audit`. La colonne « Actions
  récentes » et tout le reste viennent de Django.
- `socle/_bloc_admin.html` : un bloc par app de `app_list` — titre
  = `verbose_name` de l'app (« Comptes et personnes », « Absences », « Planning »,
  « Présences », « Journal d'audit »), une ligne par modèle (« lecture seule »
  pour les modèles non modifiables, « Ajouter » quand l'ajout est permis), et
  sous « Absences » le lien « Importer un fichier » vers l'écran de la
  3-quater. `auth` (Groupes) n'est pas listé mais reste servi
  (`/admin/auth/group/`).

Les gabarits d'admin déjà surchargés par `absences/` et `planning/` (écrans
d'import, boutons de liste) sont inchangés : ils héritent du nouveau
`base_site.html`. Aucune vue d'administration n'est réécrite (C6.4).

## 8. Statiques

`socle/static/socle/` :

| Fichier | Rôle |
|---|---|
| `polices.css` | les quatre `@font-face` Satoshi, **copiés** de `planning/static/planning/styles.css` (duplication assumée : `styles.css` est un fichier de la 6d ; l'option de faire pointer `page.html` sur `polices.css` reste ouverte) |
| `commun.css` | la coquille : variables de la charte dans `:root` (mêmes valeurs que `styles.css`) et `color-scheme: light` ; barre, avatar et menu ; sous-onglets et onglets bas ; corps de page — la largeur de lecture est portée par `main` (`body.large` l'élargit, comme avant sur `body`) ; formulaires et boutons — la pilule bleue est la classe `.bouton` (`.bouton.contour` pour le contour), un `button` nu ne reçoit que la police et le curseur ; messages Django et bandeaux ; cartes et pastilles du tableau de bord. Aucune règle de largeur (`@media`) : elles arrivent avec la 6b ; une seule `@media print` |
| `administration.css` | les variables de `admin/css/base.css` avec les valeurs de la charte, l'en-tête de 52 px, l'index en blocs |
| `favicon.png` | 256 × 256 : la dent blanche du logo du cabinet sur un carré arrondi bleu (`--accent`, #1764D8), seuls les coins sont transparents ; référencé par `base.html` (`icon` et `apple-touch-icon`) et `base_site.html` |

Les quatre fichiers sont collectés et hachés par `collectstatic`
(`CompressedManifestStaticFilesStorage`, WhiteNoise) au build de l'image ; en
test, la fixture `stockage_statique_simple` de `conftest.py` remplace le
stockage par `django.contrib.staticfiles.storage.StaticFilesStorage` (aucun
manifeste n'existe alors). `page.html`
charge toujours `planning/styles.css`, `moteur.js` et `page.js` seuls.

## 9. Tests

Cinq fichiers dans `socle/tests/` (74 tests, tous nouveaux en 6a) :

| Fichier | Ce qu'il couvre |
|---|---|
| `test_contexte.py` | garde sans `user` / anonyme / compte sans personne / compte rattaché ; chaque valeur de `nav_courante` ; `resolver_match` absent ; paresse (0 requête tant que rien n'est rendu, 1 ensuite) ; coûts figés de `/planning/<mois>/` (9 / 4), `/admin/` (3), `/connexion/` et 404 anonyme (0) |
| `test_navigation.py` | pour chaque rôle, une page par app : chaque entrée présente chez son rôle et absente chez les autres, « Administration » sur le rôle `cabinet` seulement, titre du menu, onglets bas de la salariée, `aria-current` ; **`test_page_planning_sans_coquille`** ; l'écran « aucun import » reçoit la coquille ; une seule déconnexion sur `/` |
| `test_tableau_de_bord.py` | redirections de `/` ; horizon à date fixée (À venir / En cours / Passés, « Préparer un mois ») ; les quatre pastilles ; mois historique sans marqueur (C7.10) ; « manquantes » dès un jour non couvert ; `Max("fin")` ; demandes, règle K, cinq au plus ; rendu HTML des deux rôles |
| `test_erreurs.py` | 403 et 404 connectés et anonyme (lien par rôle) ; 500 rendu par `server_error` seul et par le gestionnaire ; lien périmé → `/connexion/?expire=1` ; bandeau ; neutralité du `POST` ; 429 sans formulaire |
| `test_admin_habillage.py` | index (titres, ordre des cinq blocs, « Importer un fichier », « Actions récentes », plus de barre latérale, de bascule de thème ni de Groupes listé), liste habillée, `/admin/auth/group/` servi |

Assertions réécrites en 6a, parce qu'elles lisaient l'accueil ou le 403 d'un
lien magique : `absences/tests/test_pages.py`, `personnes/tests/test_pages.py`,
`planning/tests/test_mes_jours.py`, `planning/tests/test_pages.py` (le test
« base inchangée » de la 4a, qui comparait `base.html` à son texte d'origine,
est supprimé au profit du test d'isolement ; « sous-titre » → `class="barre"`),
`comptes/tests/test_connexion.py`, `comptes/tests/test_profil.py`. Total au
merge : 1 011 tests Python, 57 tests Node.

## 10. Limites et transition

- Les gabarits des sous-briques 6b, 6c et 6d gardent leur bloc `navigation`
  (liens « Accueil — … », bouton « Se déconnecter » en bas de page) : jusqu'à
  leur rhabillage, ces pages proposent **deux** déconnexions et la coquille
  s'ajoute à leur mise en page d'origine. Voulu, pour ne toucher qu'aux
  fichiers de la 6a.
- Les boutons nus de ces mêmes gabarits ne sont pas stylés (la pilule est
  réservée à `.bouton`).
- Le menu avatar (`<details>`) reste ouvert tant qu'on ne le referme pas ;
  aucun script n'a été ajouté.
- Aucune règle de largeur avant la 6b : la barre haute de la principale ne se
  replie pas sur un téléphone, et les onglets bas dépendent du rôle, pas de la
  largeur.
- Le mois en cours sans version ni import porte à la fois « Aucune version
  enregistrée » et « Données Doctolib manquantes ».
- `apple-touch-icon` est le même PNG ; iOS applique son propre masque aux coins.
