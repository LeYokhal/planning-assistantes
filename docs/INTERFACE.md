# Interface — la coquille (brique 6a) et l'enveloppe du planning (brique 6d)

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
| **6a-bis — aménagement (réduite, C6.21)** | « Ajouter » en pilule dans l'index d'admin, menu avatar fermé au clic extérieur et à Échap, tableau de bord à coût constant | **livrée** (PR #35) |
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
(qui contient `titre_page`, lui-même contenant `entete`, le `h1` de la page),
`contenu`, `navigation_page` (qui contient `navigation`), `scripts`. Aucun bloc
n'a été renommé en 6a ; la 6d a ajouté, à l'intérieur d'`en_tete_page`, le bloc
imbriqué `titre_page` (le titre de page, § ci-dessous).

**Règle d'isolement (révisée en 6d).** `planning/templates/planning/page.html`
**redéfinit** `style_base` (`barre.css` seule) et **vide**, dans `en_tete_page`, le
seul bloc imbriqué `titre_page` : la page planning reçoit donc la barre haute, les
onglets et le menu avatar, mais **aucune feuille de la coquille** — ni `commun.css`
ni `polices.css` ne s'y chargent. La barre s'y affiche grâce à `barre.css` seule
(§ 8), qui est **autonome** : elle ne dépend d'aucune règle générale de
`commun.css`. Le favicon reste posé dans `<head>` hors bloc, présent sur toutes
les pages. Conséquence pour toute brique à venir : un style de barre va dans
`barre.css` ; un balisage de coquille hors barre va dans `style_base` ou
`titre_page`, jamais ailleurs dans `en_tete_page`.
Un **script de la barre** vit avec la barre (6a-bis) : inline dans `base.html`,
juste après le `</details>` du menu avatar (`<details class="avatar">`), hors du
bloc `scripts` (que `page.html` redéfinit sans `block.super`) — garde de source
`test_base_html_un_seul_script_apres_details`.
`socle/tests/test_navigation.py::test_page_planning_avec_barre_sans_commun`
vérifie qu'un `/planning/<AAAA-MM>/` servi avec le jeu complet contient
`planning-data`, `class="barre"`, `<details class="avatar"`, `socle/barre.css`,
`socle/favicon.png`, `id="script-avatar"` (6a-bis : six `<script` au total, le
script de la barre en tête) et l'onglet Planning courant
(`href="/planning/" aria-current="page"`), et ne contient ni `socle/commun.css`,
ni `socle/polices.css`, ni `class="titre-page"` ;
`test_contexte.py::test_cout_page_planning` fige son nombre de requêtes (§ 3).

Ce que rend `en_tete_page` :

- **Barre haute** (`<header class="barre">`) : la marque « Espace K Dentaire
  · Planning » (lien vers `/`), puis, pour un compte connecté dont le rôle n'est
  pas `salariee`, les trois onglets **Planning**, **Absences**, **Présences &
  personnes**, dont les URL viennent de `nav_urls.planning`, `.absences`,
  `.presences` (§ 3, brique 8) — le mois de la page quand elle en porte un,
  sinon `planning:courant`, `absences:decider`, `presences:courant` —,
  l'onglet courant portant `aria-current="page"`.
  Toutes les conditions sont sur `user.role` ; `is_staff` n'apparaît nulle part
  dans le gabarit (il ne garde que l'administration).
- **Menu avatar** : un `<details class="avatar">` fermé au clic extérieur et à
  Échap par son script inline (`id="script-avatar"`, 6a-bis), dont le
  `<summary>` porte les initiales. Le titre du menu est « Bonjour Prénom » si le
  compte est rattaché à une personne, sinon le libellé du rôle (« Cabinet »,
  « Assistante principale »). Entrées : « Mes jours » et « Mes absences » pour
  `principale` ; « Mon profil » pour tout rôle sauf `cabinet` ;
  « Administration » (`admin:index`) pour `cabinet` ; puis **la** déconnexion :
  un formulaire `POST` sur `comptes:deconnexion` (`/deconnexion/`), libellé
  « Déconnexion ». C'est le seul formulaire de déconnexion des pages de la 6a.
- **Sous-onglets** « Présences | Personnes » (`nav_urls.presences`, qui suit de
  même le mois de la page, et `personnes:liste`), rendus seulement quand la page courante est une page de
  présences ou de personnes ; le sous-onglet courant est celui de l'app résolue.
- **Onglets bas** « Mes jours | Mes absences » pour le rôle `salariee`, sur
  toutes ses pages, quel que soit l'écran (règle par rôle, sans `@media`).
- **Titre de page** : le bloc imbriqué `titre_page` (6d) enveloppe
  `<div class="titre-page"><h1>{% block entete %}…</h1></div>`, rempli par chaque
  gabarit comme avant ; la page planning vide `titre_page` et porte son propre
  en-tête.

`<main>` rend les messages Django dans `<ul class="messages">` avec la classe
du niveau (`success`, `info`, `warning`, `error`, `debug` traité comme `info`),
stylés par `commun.css` ; puis `contenu`. Le `<nav>` de bas de page
(`navigation_page`) est inchangé pour les gabarits qui n'ont pas encore été
rhabillés (§ 10) ; la page planning n'en a plus depuis la 6d, les mois voisins
étant dans son en-tête (‹ ›, URL calculées par la vue).

## 3. Processeur de contexte `socle.contexte.coquille`

Déclaré dans `config/settings.py` (`context_processors`), il fournit quatre
variables à `base.html` :

- `nav_courante` — l'entrée à marquer courante, déduite de
  `request.resolver_match` (`app_name`, `url_name`) : `planning`, `mes_jours`
  (`planning:mes_jours*`), `absences`, `mes_absences` (`absences:mes_absences`,
  `nouvelle`, `annuler`), `donnees` (apps `presences` et `personnes`), `profil`,
  `tableau_de_bord` (`accueil`), ou `""` — y compris quand `resolver_match` est
  `None` (URL inconnue, page 404).
- `nav_urls` — brique 8 (D8.5) : les trois URL des onglets de gestion, sur le
  mois de la page s'il y en a un (`resolver_match.kwargs["mois"]` de
  `/planning/<mois>/` et `/presences/<mois>/`, ou `?mois=` de `/absences/`,
  validé « AAAA-MM »), sinon les URL courantes ; calculé par `reverse`, sans
  requête, présent même pour un anonyme.
- `initiales` — « PN » pour Prénom Nom, sinon la première lettre du libellé du
  rôle.
- `prenom` — le prénom de la personne rattachée, sinon `""`.

**Garde** : sans attribut `user` (`RequestFactory`) ou pour un anonyme (page de
connexion, 403 / 404 anonymes), les deux dernières valent `""` et rien n'est
lu en base. **Paresse** : pour un compte connecté, `initiales` et `prenom` sont
des `SimpleLazyObject` — `user.personne` n'est interrogé que si un gabarit les
rend, et une seule fois (Django met la relation en cache). L'administration,
qui ne rend pas la barre, ne paie aucune requête ; la page planning la rend
depuis la 6d : 10 requêtes, 11 pour une principale rattachée (coûts figés dans
`test_contexte.py`). Une page qui rend la barre en paie **une** de plus, et
seulement pour un compte rattaché (un `personne_id` nul ne déclenche rien).

Coûts figés par `socle/tests/test_contexte.py` : `/planning/2026-10/` avec le
jeu complet **10** requêtes (9 avant la 6d, plus la date du dernier import
retenu ; **11** pour une principale rattachée, la barre lisant sa personne),
sans import **4**, `/admin/` **3**, `/connexion/` et un 404 anonyme **0** ;
`/` **8** (cabinet) / **9** (principale rattachée), indépendant du nombre de
mois versionnés (`test_cout_accueil`, 6a-bis).

## 4. Page d'arrivée `/`

`socle/views.py::accueil` (`login_required`) : le rôle `salariee` est
redirigé vers `planning:mes_jours_courant` (`/mes-jours/`, C6.5) ; `principale`
et `cabinet` reçoivent `socle/tableau_de_bord.html`, dont le contexte est
assemblé par `socle/tableau_de_bord.py::construire(utilisateur, aujourd_hui=None)`
— une fonction pure, la date étant injectable pour figer l'horizon dans les
tests. Le `h1` est « Tableau de bord » ; la salutation ne vit que dans le menu.
Rien de nouveau n'est calculé : une requête sur toutes les versions regroupée
par mois (6a-bis : `order_by("mois", "-numero")`, `defer("state")`, `_ligne`
sans requête) ; couverture Doctolib par les plages `debut → fin` des imports
réussis (un import réussi couvre toute sa plage, `presences/lecture.py` ;
`imports_par_date` reste celui de `/presences/` et du planning) ; demandes par
la requête de `/absences/`. Coût figé 8 / 9 (`test_cout_accueil`, § 3).

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
| `barre.css` | **la barre haute, autonome** (6d) : barre, onglets, sous-onglets, menu avatar et les règles générales dont ils dépendent (police, liens, `button` nu), extraites de `commun.css` pour que la barre s'affiche sur la page planning, qui ne charge pas `commun.css` ; chargée par `base.html` sur toutes les pages dans le bloc `style_base`, et par `page.html` seule dans son propre `style_base` |
| `commun.css` | la coquille : variables de la charte dans `:root` (mêmes valeurs que `styles.css`) et `color-scheme: light` (barre, onglets, sous-onglets et avatar sont dans `barre.css` depuis la 6d) ; onglets bas ; corps de page — la largeur de lecture est portée par `main` (`body.large` l'élargit, comme avant sur `body`) ; formulaires et boutons — la pilule bleue est la classe `.bouton` (`.bouton.contour` pour le contour), un `button` nu ne reçoit que la police et le curseur ; messages Django et bandeaux ; cartes et pastilles du tableau de bord. Aucune règle de largeur (`@media`) : elles arrivent avec la 6b ; une seule `@media print` |
| `administration.css` | les variables de `admin/css/base.css` avec les valeurs de la charte, l'en-tête de 52 px, l'index en blocs, la pilule « Ajouter » (`a.ajout`, 6a-bis) |
| `favicon.png` | 256 × 256 : la dent blanche du logo du cabinet sur un carré arrondi bleu (`--accent`, #1764D8), seuls les coins sont transparents ; référencé par `base.html` (`icon` et `apple-touch-icon`) et `base_site.html` |

Les cinq fichiers sont collectés et hachés par `collectstatic`
(`CompressedManifestStaticFilesStorage`, WhiteNoise) au build de l'image ; en
test, la fixture `stockage_statique_simple` de `conftest.py` remplace le
stockage par `django.contrib.staticfiles.storage.StaticFilesStorage` (aucun
manifeste n'existe alors). `page.html` charge `planning/styles.css`,
`moteur.js` et `page.js` ; la seule feuille du socle qui l'atteint est
`barre.css`, qu'il charge lui-même dans son bloc `style_base`.

## 9. Tests

Cinq fichiers dans `socle/tests/` (74 tests, tous nouveaux en 6a) :

| Fichier | Ce qu'il couvre |
|---|---|
| `test_contexte.py` | garde sans `user` / anonyme / compte sans personne / compte rattaché ; chaque valeur de `nav_courante` ; `resolver_match` absent ; paresse (0 requête tant que rien n'est rendu, 1 ensuite) ; coûts figés de `/planning/<mois>/` (10, 11 pour une principale rattachée ; 4 sans import), `/admin/` (3), `/` (8 pour N = 0, 1, 6 mois versionnés ; 9 pour une principale rattachée — 6a-bis), `/connexion/` et 404 anonyme (0) ; `_mois_de` et `nav_urls` (brique 8) |
| `test_navigation.py` | pour chaque rôle, une page par app : chaque entrée présente chez son rôle et absente chez les autres, « Administration » sur le rôle `cabinet` seulement, titre du menu, onglets bas de la salariée, `aria-current` ; **`test_page_planning_avec_barre_sans_commun`** ; l'écran « aucun import » reçoit la coquille ; une seule déconnexion sur `/` ; les onglets suivent le mois (`test_onglets_suivent_le_mois`, brique 8) ; le script du menu avatar une fois par page authentifiée, jamais pour un anonyme, et la garde de source `test_base_html_un_seul_script_apres_details` (6a-bis) |
| `test_tableau_de_bord.py` | redirections de `/` ; horizon à date fixée (À venir / En cours / Passés, « Préparer un mois ») ; les quatre pastilles ; mois historique sans marqueur (C7.10) ; « manquantes » dès un jour non couvert ; `Max("fin")` ; demandes, règle K, cinq au plus ; rendu HTML des deux rôles |
| `test_erreurs.py` | 403 et 404 connectés et anonyme (lien par rôle) ; 500 rendu par `server_error` seul et par le gestionnaire ; lien périmé → `/connexion/?expire=1` ; bandeau ; neutralité du `POST` ; 429 sans formulaire |
| `test_admin_habillage.py` | index (titres, ordre des cinq blocs, « Importer un fichier », quatre pilules « Ajouter » et huit rangées (6a-bis), « Actions récentes », plus de barre latérale, de bascule de thème ni de Groupes listé), liste habillée, `/admin/auth/group/` servi |

Assertions réécrites en 6a, parce qu'elles lisaient l'accueil ou le 403 d'un
lien magique : `absences/tests/test_pages.py`, `personnes/tests/test_pages.py`,
`planning/tests/test_mes_jours.py`, `planning/tests/test_pages.py` (le test
« base inchangée » de la 4a, qui comparait `base.html` à son texte d'origine,
est supprimé au profit du test d'isolement ; « sous-titre » → `class="barre"`),
`comptes/tests/test_connexion.py`, `comptes/tests/test_profil.py`. Total au
12/09/2026 (brique 6a-bis mergée) : 1 045 tests Python, 57 tests Node.

## 10. Limites et transition

- Les gabarits des sous-briques 6b et 6c gardent leur bloc `navigation`
  (liens « Accueil — … », bouton « Se déconnecter » en bas de page) : jusqu'à
  leur rhabillage, ces pages proposent **deux** déconnexions et la coquille
  s'ajoute à leur mise en page d'origine. Voulu, pour ne toucher qu'aux
  fichiers de la 6a.
- Les boutons nus de ces mêmes gabarits ne sont pas stylés (la pilule est
  réservée à `.bouton`).
- Le menu avatar (`<details>`) se ferme au clic extérieur et à Échap depuis la
  6a-bis (script inline avec la barre, § 2) ; sur la page planning, Échap ferme
  aussi le filtre si les deux sont actifs (écart assumé, C6.21).
- Aucune règle de largeur avant la 6b : la barre haute de la principale ne se
  replie pas sur un téléphone, et les onglets bas dépendent du rôle, pas de la
  largeur.
- Le mois en cours sans version ni import porte à la fois « Aucune version
  enregistrée » et « Données Doctolib manquantes ».
- `apple-touch-icon` est le même PNG ; iOS applique son propre masque aux coins.
- **6d (mergée le 11/09/2026, `a39c3d5`, PR #29 ; recettée le 12/09)** : la page
  planning porte la barre commune par `barre.css` seule, un en-tête sur une ligne
  (‹ › vers les mois voisins, pastilles de version et de données), Annuler · Enregistrer
  · Publier et un menu « Plus » (Proposer, Exporter (JSON), Importer, Télécharger une
  copie, Imprimer, Refaire la proposition), le toast « rien n'a été publié » sur un 422,
  le bandeau « écran large » sous 768 px, `page.js` au vouvoiement, les alertes « à
  signaler au cabinet » pour la principale ; plus de navigation de bas de page.
  Les neuf `id` de boutons restent dans le DOM. Retour de recette : pastilles et
  sélecteur « Planning individuel » jugés redondants, retirés en **brique 8** (C6.20),
  qui porte aussi le filtre à plusieurs noms et les onglets qui suivent le mois.
  Poste de recette de référence : 1 536 × 864 (Chromebook 15,6" à 125 %) ; à 1 366 px la
  barre d'outils passe sur deux lignes, hors critère, résorption attendue par la 8.
- **8 (mergée le 12/09/2026, `2522e97`, PR #31) et 8-bis (`89885de`, PR #32)** : la pastille
  « Données Doctolib du … » et le sélecteur « Planning individuel » sont retirés (la date
  passe au sous-titre, le filtre vit dans le panneau) ; la pastille de version se masque
  dans l'état stable « Publiée (vN) » ; les onglets de gestion suivent le mois de la page
  (`nav_urls`, § 3). La grille elle-même — filtre à plusieurs noms, pictogrammes et repli des
  lignes, repli des semaines, sommaire, bandes collantes, jour actuel, flèches, briques
  pleines, cases jour — est décrite dans `docs/PLANNING.md` § 14.
- **6a-bis — 12/09/2026 — PR #35 `4b1dd6f`** (réduite, C6.21) : « Ajouter » en pilule dans
  l'index d'admin (`div.rangee`, `a.ajout`, `administration.css` seule), menu avatar fermé au
  clic extérieur et à Échap (script inline `id="script-avatar"` avec la barre), tableau de
  bord à coût constant (une requête sur les versions, couverture par les plages des imports
  réussis ; `/` figé à 8 / 9). Sept fichiers, aucune migration ; 1 045 tests Python, 57 Node.
