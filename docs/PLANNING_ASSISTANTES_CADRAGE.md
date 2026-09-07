# Planning Assistantes — Cadrage de l'application

> **Version 1.7 — 07/09/2026 (soir).** Complète `PLANNING_ASSISTANTES_BRIEF.md` (référence du contrat MCP Doctolib, § 3.2 et § 9.6) et `WORKING_HABITS.md` (régime de travail, applicable tel quel).
> Statut : **périmètre et décisions produit figés** (C2.1 → C2.12, C3.1 → C3.9, C4.1 → C4.13, C5.1). **Briques 1a, 1b, 2, 3, 3-quater, 4a et 4b livrées** (§ 8, § 14) : le périmètre v1 de l'app est complet et **l'existant 2026 est repris** ; restent la brique 5 (n8n) et la brique 0 (VoiceDoctolib). Reste un point de rétention (§ 10, C2.6) ; l'étalon de paie est **acté** (§ 11).
> Convention : tout ce qui est marqué *(proposition)* est à confirmer au diff plan de la brique concernée. Aucun chiffre n'est estimé.
>
> **Changements v1.6 → v1.7** : brique 3-quater livrée le 07/09/2026 (§ 8, journal § 14) — reprise exceptionnelle de l'existant Notion 2026 par un écran d'import dans l'admin ; **C3.9** amende C3.8 ; **C5.1** : la paie envoie dates + type de paie, la comptable décompte — `jours_comptes` devient un indicateur interne (amende C3.1 en statut, § 1.2 et § 5.2 en portée) ; § 11 : étalon de paie acté sur les bulletins de janvier → août ; § 3.2 flux 4 ; § 6.3 écran d'import ; § 7 : ce que la formule C3.1 ne modélise pas ; § 12 : backlog ; § 15 : leçons « reprise ».
> **Changements v1.5 → v1.6** : brique 4b livrée le 07/09/2026 (§ 8, journal § 14) ; R4a-1 acté avec l'écart E1 (§ 11, § 14) ; décisions C4.5 → C4.13 (§ 2) ; C2.7 et C2.8 tranchées ; § 1.1 / § 1.3 : publication, « Mes jours » ; § 3.1 / § 3.2 : flux 2 complet, flux 3 avec conflit ; § 3.3 : `meta.imports` ; § 4 : `PlanningVersion` figée, `version_de_base` non nul, actions d'audit 4b ; § 5.2 / § 5.3 / § 5.5 : surfaces 4b, logs, variable `N8N_PLANNING_WEBHOOK_URL` ; § 6.1 / § 6.2 / § 6.5 : routes et événements réels ; § 7 : conflit ; § 12 : backlog 4b ; § 15 : leçons « recette croisée ».
> **Changements v1.4 → v1.5** : brique 4 découpée en **4a / 4b**, 4a livrée le 06/09/2026 (§ 8, journal § 14) ; décisions C4.1 → C4.4 (§ 2) dont l'**amendement du § 1.2** sur le type d'absence ; § 1.1 : page planning servie par l'app, versions ; § 3.1 / § 3.2 : app `planning`, flux 2 en place hors publication ; § 3.3 : contrat `DATA` / `STATE` réel ; § 4 : `PlanningVersion` figée ; § 5.2 / § 5.3 : sept surfaces, actions d'audit 4a ; § 6.1 / § 6.4 : routes et garde-fous réels ; § 7 : règles strictes vérifiées, exclusivité ; § 11 : critère différé R4a-1 ; § 12 : hygiène `version_de_base` ; § 15 : leçons « page, brouillon et référence ».
> **Changements v1.3 → v1.4** : brique 3 livrée le 03/09/2026 avec ses sous-briques 3-bis (04/09) et 3-ter (06/09) (§ 8, journal § 14) ; décisions C3.1 → C3.8 (§ 2) dont l'abandon de la migration Notion des absences au profit d'une saisie manuelle ; § 1.1 / § 1.3 : espace salariée en place, la principale y a accès ; § 3.1 / § 3.2 : composants et flux 3 en place, flux 4 côté app ; § 4 : `TypeAbsence`, `AbsenceSalariee` (avec `jours_retenus`), `Compte.email_en_attente`, actions d'audit 3 ; § 5.1 : changement d'adresse livré, HSTS à un an ; § 5.3 : suppressions d'absence journalisées, la leçon du `SET_NULL` ; § 5.5 : deux variables ; § 6.2 / § 6.3 / § 6.5 : surfaces réelles ; § 7 : formule des jours comptés, périodes d'ouverture datées, répartition par mois ; § 10 / § 11 / § 12 : points restants et backlog réordonnés ; § 15 : leçons « paie, audit et recette ».
> **Changements v1.2 → v1.3** : brique 2 livrée le 31/08/2026 avec ses sous-briques 2-bis, 2-ter et 2-quater ; C2.12 (IP cliente = `X-Real-IP`, mesuré) ; § 4 : contrainte et code de `Personne`, `CompteurDebit`, actions d'audit 2 ; § 5.1 : changement d'adresse → brique 3 ; § 5.2 / § 6.5 : limitation de débit en place ; § 7 : gardes de lecture de la fiche ; § 12 : débit sorti du backlog, hygiène post-recette ; § 15 : leçons « proxy, mesure et recette ».
> **Changements v1.1 → v1.2** : brique 1b livrée le 31/08/2026 ; décisions du diff plan 1b v2 intégrées (C2.10, C2.11) ; § 4 : `ImportPresences` et `VerrouImport` ; § 5.5 : cinq variables ; § 6.5 / § 6.6 : routes et comportement réels ; § 15 : leçons de la recette 1b.
> **Changements v1.0 → v1.1** : ajout du § 14 ; C2.9 tranché (a, webhook n8n → Gmail) ; décisions du diff plan 1a intégrées ; § 15 leçons de déploiement Railway.

---

## 1. Périmètre v1

### 1.1 Ce que l'app fait
- **Présences des praticiens** : import du payload `consulter_jours_travail` (contrat brief § 3.2), stockage brut, invariant de recompte, écran « présences du mois ». **En place depuis la 1b** par le chemin fichier ; chemin endpoint câblé, inactif jusqu'à la brique 0.
- **Personnes et contrats** : qui est planifié, rôle, heures hebdomadaires, jours fixes, agenda Doctolib apparié, couleur. Reprend le rôle de la case `Planning` de ☎️ Fiche personnel. **En place depuis la 2.**
- **Absences des salariées** : demande par la salariée, validation par l'assistante principale ou le cabinet pour les types *demandés*, effet immédiat pour les types *déclarés* ; jours d'école des étudiantes comme absences de type `Ecole` ; jours comptés pour la paie, corrigeables par la validatrice ; données de paie du mois servies à n8n. Reprend le rôle des pages « Absence » de 📅 Agenda cabinet, **sans migration** : l'existant est ressaisi à la main (C3.8). **En place depuis la 3.**
- **Planning mensuel** : la page actuelle (proposition, drag & drop, compteurs, notes, impression) est **une vue de l'app depuis la 4a** : `DATA` calculé côté serveur, moteur JS isolé et testé, versions à chaque enregistrement (409 / 422), copie HTML autonome, plus de brouillon navigateur ; **publication d'une version (4b)** : revérification serveur, audit, webhook `planning.publie`, « Mes jours » pour chaque salariée, conflit absence ↔ planning publié signalé (jamais bloquant). Remplace les entrées « Présence » saisies à la main dans 📅 Agenda cabinet (aucun lecteur, aucune migration).
- **Notifications** : v1 = le mail mensuel à la comptable (données de paie), via n8n + Gmail. **La donnée est prête depuis la 3** (endpoint de paie) ; l'envoi reste la brique 5. Le reste est en backlog (§ 12).

### 1.2 Ce que l'app ne fait pas
- **Aucune écriture Doctolib.** Les agendas des praticiens sont lus (présences), jamais modifiés. Les outils de mutation MCP restent hors périmètre.
- **Aucune donnée patient**, nulle part : ni en base, ni en logs, ni en webhook. `consulter_planning` (PHI) n'est pas utilisé.
- **Aucune donnée RH sensible hors besoin** : pas de n° de sécurité sociale, date de naissance, téléphone personnel, IBAN, adresse — ces champs restent là où ils sont (Notion, Google Sheets). **Le type d'une absence et sa précision ne sortent jamais de l'application** : ni dans l'audit, ni dans les logs, ni dans un webhook — **une exception nommée (C5.1, 07/09/2026)** : les données de paie servies à n8n pour la comptable portent la **catégorie de paie** (congé payé, sans solde, maladie, événement familial, enfant malade) des seuls types `paie`, celle qui figure sur chaque bulletin ; la précision, jamais (§ 5.2). **Amendement C4.1 (06/09/2026)** : le libellé du type figure dans le `DATA` de la page planning, donc à l'écran (rôles `cabinet` et `principale`) **et dans la copie HTML autonome téléchargée** ; il ne figure ni dans `STATE`, ni dans les versions, ni dans l'export JSON.
- **Pas de paie** : l'app fournit les données d'absence à la comptable, elle ne calcule ni bulletin ni solde de congés (`fdp-cabinet-k` reste une skill séparée).
- Le « entre autres » (modules futurs, possiblement avec données de santé) est en **backlog** (§ 12), sans décision.

### 1.3 Utilisateurs et rôles
| Rôle | Qui | Voit | Fait |
|---|---|---|---|
| `cabinet` | Yohan | tout : personnes, absences avec types, planning, imports, audit | administre les personnes, valide ou refuse les demandes — **seul à décider d'une demande émise par la personne concernée** (C3.4) —, corrige les jours comptés, publie, déclenche un import |
| `principale` | l'assistante principale, qui construit le planning | **tout ce qui concerne l'agenda, motifs d'absence compris** (décision C2.3b), **et son propre espace de salariée** (3-bis) | édite et enregistre le planning, publie, valide ou refuse les demandes d'absence des autres, corrige les jours comptés, demande ses propres absences |
| `salariee` | chaque assistante et secrétaire | ses jours publiés (« Mes jours », 4b : dates, journée, avec qui — rien d'autre), ses absences et l'état de ses demandes (« son espace ») | demande ou déclare ses absences, annule une demande en attente, change son adresse de connexion |

Rôles extensibles (décision C2.1). Les praticiens n'ont pas de compte en v1. **Implémenté en 1a** : les trois rôles sur `Compte`. **1b** : `role_requis`. **2** : fiche dans l'application, comptes des salariées créés en masse. **3** : premier espace du rôle `salariee` (`/mes-absences/`, `/mon-profil/`), écran de décision pour `principale` et `cabinet`, admin des absences pour `cabinet`. **3-bis** : l'espace personnel est ouvert à `principale` — un compte n'a qu'un rôle, et la principale pose aussi ses congés. Le rôle `cabinet` reste exclu de cet espace (il n'a pas d'absence). La désignation de la principale est un geste dans l'admin (rôle sur son compte), à dater au § 14 quand il a lieu.

---

## 2. Décisions actées

| # | Question | Décision | Conséquences |
|---|---|---|---|
| — | Forme cible | application web hébergée, base partagée (brief § 9.1, confirmé) | Railway + PostgreSQL ; la page HTML devient un front servi par l'app |
| — | Présences Doctolib | **option B** : endpoint `POST /admin/presences` sur le serveur MCP, payload de `consulter_jours_travail` **tel quel** (brief § 9.2 / 9.6) | brique 0, cadrée et exécutée **dans VoiceDoctolib** ; **depuis la 1b** le client côté app existe, inactif sans ses variables ; la brique 0 s'aligne sur `DOCTOLIB_PRESENCES_URL`, `DOCTOLIB_PRESENCES_SECRET`, en-tête `X-Presences-Secret`, corps `{"date","date_fin","praticien":"tous"}`, 200 = payload tel quel |
| C2.1 | Posture sécurité et identité | **option 3 « Planning + fondations »** | lien magique, rôles extensibles, journal d'audit dès la brique 1, type d'absence isolé et jamais journalisé, date de rétention prévue dans le modèle |
| C2.2 | Où vit la logique de règles et de proposition | **option A : dans le navigateur** | trois garde-fous (§ 6.4) ; le serveur calcule `DATA`, stocke `STATE` en versions |
| C2.3 | Validation des absences | **selon le type** : *demandés* (congé payé, congé sans solde) → demande, validée ou refusée ; *déclarés* (tous les autres) → effectifs dès la saisie | **implémenté en 3** : `TypeAbsence.categorie`, statuts `en_attente` / `validee` / `refusee` / `annulee` / `declaree`, `effective` = propriété calculée ; le conflit après publication attend la brique 4 (l'objet « planning publié » n'existe pas avant) |
| C2.3b | Le rôle `principale` voit-il les motifs | **oui, tout** | pas de vue anonymisée pour ce rôle ; minimisation appliquée aux autres sorties (§ 5.2) |
| C2.4 | Stack | **Django + PostgreSQL** sur Railway, page actuelle comme front | comptes, sessions, migrations, admin ; lien magique par django-sesame ; API n8n |
| C2.5 | E-mail de connexion | **choisi par la salariée** | création protégée par invitation ; **changement d'adresse livré en 3** (§ 5.1) |
| — | Durée d'une absence (paie) | **jours de travail selon son contrat**, pas jours calendaires | formule C3.1 ; le planning n'existant pas avant la brique 4, c'est le contrat qui fait foi |
| — | Automatisation à reproduire | **une seule en v1** : le mail mensuel à la comptable | endpoint de paie **livré en 3** (§ 6.5), workflow n8n en brique 5 |
| C2.7 | Qui publie un planning | **`principale` et `cabinet`, pas de dépublication** (tranché 06/09, décision F de la 4b) | audit `planning_publie` à chaque publication ; une correction = nouvelle version puis publication, qui supersède |
| C2.8 | Copie HTML autonome, brouillon navigateur | copie conservée ; brouillon `localStorage` supprimé — **appliqué en 4a** | la copie reste celle de la dernière version enregistrée, pas de variante « copie de la publiée » (4b, décision N) |
| C2.9 | Canal des e-mails de connexion et d'invitation | **(a) webhook n8n → Gmail** | **en place depuis 1a** ; aussi le mail de confirmation de changement d'adresse (3) |
| C2.10 | Tâche de fond des tirs endpoint | thread + verrou en base, péremption 15 minutes | **en place depuis 1b** |
| C2.11 | Secrets et en-têtes des échanges avec n8n | entrant `N8N_API_SECRET` / `X-Api-Secret` ; sortant `N8N_WEBHOOK_SECRET` / `X-Webhook-Secret`, une URL par flux | **en place depuis 1b** ; la 3 ajoute `N8N_ABSENCE_WEBHOOK_URL`, même secret, même en-tête |
| C2.12 | IP cliente derrière le proxy Railway | `X-Real-IP`, réécrit par Railway — établi par mesure | **en place depuis 2-quater** |
| **C3.1** | **Formule des jours comptés** | par semaine lundi→dimanche, `min(J, max(0, B − F))` : `J` = jours d'absence tombant sur un jour d'ouverture du cabinet, fériés exclus ; `B` = briques du contrat (39 h → 4, 35 h → 4, 27 h → 3) ; `F` = fériés tombant sur un jour d'ouverture. Personne à jours fixes : ses jours fixes hors fériés. Contrat incomplet : 0 et signal, jamais de valeur supposée | § 7 ; formule Notion « Durée » jamais fournie — le critère de recette différé (S3b, § 11) est le filet. Le plafond s'applique **une fois par semaine**, et les jours retenus sont **datés** (C3.6) |
| **C3.2** | **Jours d'ouverture du cabinet** | **datés**, dans `regles.json` : mardi→samedi à l'origine, **lundi→vendredi à partir du lundi 5 octobre 2026** ; servent **uniquement** au calcul de paie, le planning lit Doctolib | bascule calée sur un lundi pour qu'aucune semaine ne soit à cheval ; un samedi ouvert ponctuellement se rattrape en paie par correction manuelle |
| **C3.3** | **Demi-journées** | journée entière à la saisie ; la validatrice pose 0,5 par **correction manuelle** ; les montants sont en décimal | aucun champ de saisie en demi-journée ; une absence corrigée à 0,5 reste **un jour bloqué au planning** (divergence assumée, à ne pas « corriger » en brique 4) |
| **C3.4** | **Règle K** | une demande dont la personne concernée est le décideur ne peut être tranchée que par `cabinet` — assise sur la **personne**, pas sur l'auteur de la saisie (qui part en `SET_NULL`) | la principale ne valide jamais ses propres congés |
| **C3.5** | **Rétention (mécanisme)** | réglage `RETENTION_ABSENCES_JOURS`, **absent = aucune purge**, `a_effacer_le` laissé nul, rattrapé par la commande de purge quand le réglage apparaît | ne bloque pas le déploiement (contrairement à `regles.json`) : une durée juridique non rendue n'est pas une condition de fonctionnement. La **valeur** reste C2.6 (§ 10) |
| **C3.6** | **Paie : plage et répartition** | la paie filtre sur le **mois calendaire** (jamais `plage_mois`, outil du planning en semaines complètes) ; **chaque mois reçoit sa portion** d'une absence à cheval, lue sur les **jours retenus datés** figés au calcul ; **on ne recoupe jamais une absence pour relancer le calcul** (le plafond hebdomadaire s'appliquerait deux fois) ; absence corrigée : prorata au demi-jour inférieur, reliquat au mois du premier jour retenu | défaut trouvé au checkpoint diff, avant tout merge : quatre jours facturés deux fois. Voir § 15 |
| **C3.7** | **Client HTTP n8n sortant** | factorisé dans `socle/client_n8n.py` (trois appelants : mail, import, absence) ; l'import `requests` est **conservé** dans les deux appelants historiques, avec commentaire | douze tests patchent `<module>.requests.post` ; le retirer les ferait tomber en `AttributeError`. Factorisation prévue en 5, faite en 3 |
| **C3.8** | **Existant Notion des absences** | ~~aucune migration : ressaisie à la main~~ — **amendée par C3.9** | décision du 01/09/2026, tenue pour septembre à la main jusqu'au 07/09 |
| **C3.9** | **Reprise exceptionnelle de l'existant 2026** (07/09/2026) | **un** import depuis un fichier JSON produit hors de l'app (lecture Notion, arbitrages, fusion des jours consécutifs), par un **écran d'admin** en deux temps — rapport d'analyse, puis confirmation, écriture atomique, idempotente (« déjà présente »), sans webhook ni crochet de conflit (les conflits sont listés dans le rapport) ; Notion devient archive ; l'écran reste disponible mais n'a plus de source | brique 3-quater ; **la fiche de paie prime sur Notion** en cas d'écart (17 arbitrages, § 14) ; les données nominatives du fichier n'entrent ni dans le dépôt ni dans un prompt |
| **C5.1** | **Ce que la paie envoie à la comptable** (07/09/2026) | **dates + catégorie de paie**, par salariée et par absence effective d'un type `paie` ; la comptable décompte selon sa convention (jours ouvrables pour CP et maladie, jours réellement non travaillés pour le sans-solde — constaté sur les bulletins, § 11) ; **`jours_comptes` devient un indicateur interne** (compteurs, corrections, suivi), plus une donnée de paie | amende C3.1 en statut, § 1.2 et § 5.2 en portée ; aucune formule nouvelle ; à implémenter dans le mail de la brique 5 (l'endpoint de paie sert déjà les dates ; la catégorie de paie s'y ajoute) |
| **C4.1** | **Type d'absence dans la page planning** | **comme le gabarit** : codes CP / MAL / SS à l'écran, dans la copie HTML et son `DATA` embarqué ; jamais dans `STATE`, les versions, l'export JSON, l'audit, les logs, les violations, `/api/erreurs/` | décision Yohan du 06/09, prise contre l'avis de Claude ; amende le § 1.2 ; isolée dans une fonction (`libelle_conge`) pour être réversible ; sept surfaces testées (§ 5.2) |
| **C4.2** | **Découpage de la brique 4** | 4a = page servie, moteur isolé, vérification double, versions, copie, erreurs ; 4b = publication, conflit absence / planning publié, « mes jours publiés » (`salariee`, minimale) | champs de publication de `PlanningVersion` créés en 4a, inertes |
| **C4.3** | **Décision de proposer** | jamais un drapeau du `state` : la page propose si et seulement si la version servie est `0` | défaut trouvé en revue v2 : `initialise` retiré par le nettoyage aurait fait re-proposer par-dessus une version enregistrée ; `initialise` / `modifie` sortent du contrat |
| **C4.5** | **Sémantique de la publication** | publier = poser `publiee / publie_le / publie_par` **sur la dernière version**, numéro explicite dans l'URL, **409** si ce n'est plus la dernière ; « version publiée du mois » = dernière `publiee=True` par `numero` ; republier → 200 `deja_publiee`, sans écriture ni audit | pas de copie figée, pas de nouvelle ligne ; écriture en un seul `UPDATE … WHERE NOT publiee AND NOT EXISTS(numero supérieur)` (seul point de sérialisation, comme la contrainte unique de 4a) |
| **C4.6** | **Revérification à la publication** | `verifier(DATA recalculé, state)` ; **422 si violation, rien n'est écrit** ; `verifications` = `{verifie_le, imports[{id, empreinte}], nb_briques}` | une absence devenue effective ou un mouvement Doctolib **avant** publication est attrapé ici ; **après**, c'est C4.7 |
| **C4.7** | **Conflit absence ↔ planning publié** | détecté à **l'entrée en état effectif**, quel que soit le chemin (déclaration, validation, admin) ; conflit = brique de la salariée, **tout slot**, sur une date de l'absence, dans la version publiée de chaque mois dont la plage contient la date ; **types bloquants seulement** ; audit `absence_conflit_publication` + webhook `absence.conflit` + bandeau `/absences/` ; **jamais bloquant**, aucune persistance (recalculé au rendu) | le crochet vient après `save()`, audit et webhook existants, et ne lève jamais ; limite assumée : changer les dates ou le type d'une absence **déjà** effective ne resignale pas (transition seulement) |
| **C4.8** | **« Mes jours »** | page serveur minimale, **sans `DATA`** : pour la personne connectée, dates, journée (J / C, heures sup), libellé du slot (`Prénom Nom` du praticien, Secrétariat, Sureffectif, Administratif) ; **toute la plage** de la version publiée, jours du mois voisin en italique ; pour une date portée par deux versions publiées, **celle du mois calendaire fait foi** | `salariee` et `principale` (pour elle-même) ; `cabinet` → 403 ; compte sans personne → message, jamais 500 |
| **C4.9** | **Brique orpheline (R4a-1-E1)** | la page dessine une ligne « hors présence » dans la case-jour dès qu'une brique pointe un slot praticien non présent (« absent ce jour-là », « jour fermé », « inconnu ») : brique visible, retirable, déplaçable, jamais une cible de dépôt ; pas de nettoyage automatique ; jours **affichés** seulement (un jour hors colonnes reste au chemin export JSON) | défaut vu en R4a-1 : une violation `praticien_absent` que l'utilisatrice ne pouvait pas corriger |
| **C4.10** | **`version_de_base` non nul** | `PositiveIntegerField(default=0)`, migration `planning.0002` (`RunPython` NULL → 0 puis `AlterField`) | hygiène § 12 faite ; 0 ligne touchée en production |
| **C4.11** | **Webhook de publication** | nouveau flux, nouvelle URL `N8N_PLANNING_WEBHOOK_URL` (C2.11), même secret, même en-tête ; corps `{evenement, mois, numero, nb_briques, publie_par_id, lien, horodatage}` ; absente = muet | **non posée** sur Railway : le workflow est brique 5 ; chaque publication journalise « webhook planning non configure » d'ici là |
| **C4.12** | **Webhook de conflit** | événement `absence.conflit` sur l'URL absence existante ; corps absence + `conflits: [{mois, numero, dates}]` — ni slot, ni nom, ni type | même destinataire que les autres événements d'absence ; le workflow « Absences (réception) » le transmet sans branche |
| **C4.13** | **Cycle d'import** | `absences/` importe `planning.conflits` **dans la fonction** (patron `presences/verrou.py`) ; `planning/webhooks.py` n'importe jamais `services` (le comptage lui est passé) | `planning.donnees` importe `absences.services` : le cycle serait direct |
| **C4.4** | **Exclusivité** | stricte **sur les cases praticien** (exclusive ailleurs, non-binôme chez un exclusif = violation) ; le sureffectif reste admis pour une exclusive, comme le gabarit validé le faisait (étape 5 de `proposer`) | constaté à l'implémentation : l'interdire rendait la proposition inenregistrable |
| — | Notion | Notion dit *qui* **jusqu'à la 2**, porte les absences **jusqu'à la 3** ; désormais **archive en lecture seule** ; `regles.json` dit *comment* ; les entrées « Présence » ne sont pas migrées | aucune écriture Notion, jamais |
| — | « Entre autres » | backlog, périmètre v1 = planning | un module portant des données de santé de patients ne s'ajoute pas à cette app sans revoir l'hébergement (§ 5.6) |

---

## 3. Architecture cible

### 3.1 Composants
```
navigateur (PC cabinet, téléphones)          Railway (projet planning-assistante, dédié)
┌─────────────────────────────┐    ┌──────────────────────────────┐    ┌──────────────────────┐
│ page planning (JS validé)   │◄──►│ Django : pages, API JSON,    │◄──►│ PostgreSQL (base de   │
│ espace salariée / admin     │    │ admin, auth, audit           │    │ l'app, dédiée)        │
└─────────────────────────────┘    │ tâche de fond : import S7    │    └──────────────────────┘
                                   └───────┬──────────────▲───────┘
                                           │ POST /admin/presences (secret)   HTTP + secret / webhooks
                                           ▼                                  │
                                   serveur MCP Doctolib (VoiceDoctolib)   n8n Cloud ──► Gmail
                                   lecture seule, zéro PHI                (comptable, salariées, connexion)
```
**En place depuis 1a** : projet Railway **planning-assistante**, service `planning-assistantes` + `Postgres` dédié, région europe-west4, domaine `planning-assistantes-production.up.railway.app`. Webhook n8n « Planning assistantes - Mail sortant » (id `QdyH1ZtTwoDl6mVg`).
**En place depuis 1b** : apps `presences` et `n8n` ; workflows « Import (réception) » (`jb4iRxGeW5XhuaeD`) et « Déclencher import » (`Z4BOQRRxm9KLrQNb`).
**En place depuis 2** : apps `personnes` et `regles`, `comptes/noms.py`, `socle.CompteurDebit`, relevé « topologie proxy ».
**En place depuis 4b** : `planning/conflits.py`, `planning/webhooks.py`, migration `planning.0002`, gabarit `mes_jours.html`, ligne « hors présence » dans `page.js` / `moteur.js` ; **825 tests Python, 57 Node**. Post-squash `0a53bdf`.
**En place depuis 4a** : app `planning` (`models`, `donnees`, `verification`, `services`, `views`, admin lecture seule), statiques `moteur.js` / `page.js` / `styles.css`, tests Node (`node --test`, sans npm, pont pytest), `presences.services.imports_par_date`, `regles.json` section `palette`, blocs `style_base` / `en_tete_page` / `navigation_page` / `classe_html` / `scripts` dans `base.html`. Post-squash `5072226`.
**En place depuis 3** : app `absences` (modèles, calcul pur, services, paie, webhooks, admin, deux commandes de gestion), `socle/feries.py` (fériés français, Pâques incluse), `socle/client_n8n.py` (client factorisé), `comptes/profil.py` (changement d'adresse) ; workflow n8n « Planning assistantes – Absences (réception) » (Webhook `/webhook/absence-planning` en Header Auth → Gmail vers Yohan ; id `eQABsWqayUIR8KuY`, export `docs/n8n/n8n_planning_absences_reception.json`) ; workflow de test « Paie (test) » (Manual Trigger → HTTP GET → Gmail, dupliqué de « Déclencher import »). Aucun de ces workflows n'est « Available in MCP ».

### 3.2 Flux
1. **Import des présences** — en place (1b), chemin fichier ; chemin endpoint câblé, inactif jusqu'à la brique 0.
2. **Page planning — en place (4a, publication 4b)** : `GET /planning/<AAAA-MM>/` sert `DATA` (calculé) et le `STATE` de la dernière version ; la page vérifie les règles strictes avant d'envoyer, le serveur les revérifie (422), refuse une base périmée (409, contrainte unique + `IntegrityError` hors du `with`), enregistre une version (audit `planning_enregistre`) ; copie HTML autonome depuis la dernière version ; erreurs de page remontées (`error.name` seul). **Publier (4b)** : `POST …/versions/<n>/publier/` sur la dernière version, revérification serveur (422), 409 si périmée, audit `planning_publie`, webhook `planning.publie` ; l'en-tête dit « Version N · publiée » ou « publiée : vP » ; « Mes jours » lit la version publiée courante.
3. **Absences — en place (3)** : la salariée (ou la principale, 3-bis) saisit type, dates, précision courte → type *demandé* : `en_attente`, `principale` ou `cabinet` décide (règle K), webhook `absence.demandee` puis `absence.decidee` ; type *déclaré* : `declaree`, effective immédiatement, webhook `absence.declaree` ; à l'entrée en état effectif, jours comptés calculés et **dates retenues figées**, échéance de purge posée si la rétention est réglée ; correction manuelle possible (multiple de 0,5, bornée par la plage), la valeur calculée conservée ; annulation d'une demande en attente, auditée sans webhook. **Conflit avec un planning publié (4b)** : à l'entrée en état effectif d'une absence bloquante, audit `absence_conflit_publication`, webhook `absence.conflit`, bandeau et marqueur sur `/absences/` ; l'absence est écrite dans tous les cas (C4.7).
4. **Paie — côté app en place (3, amendée C5.1)** : la brique 5 ajoute à l'endpoint la catégorie de paie par absence et fait du mail un envoi de **dates + catégorie** ; le paragraphe « N jour(s) » reste indicatif. Tel quel en 3 : `GET /api/n8n/paie/<AAAA-MM>/` rend, par salariée ayant au moins une absence effective d'un type `paie` **dont une portion tombe dans le mois calendaire**, la portion du mois, le total de l'absence, les drapeaux `facture_partiellement` / `corrigee` / `repartition_calculee`, et le paragraphe mis en forme (« Paie 2026-09 — absences à décompter : NOM Prénom : 2,5 jour(s). », avec une phrase d'alerte si une répartition n'a pu être calculée). Une salariée sans absence comptée n'apparaît pas. **Le mail à la comptable reste la brique 5.**
5. **Connexion (1a, en place)** : lien magique django-sesame, 15 min, usage unique.

### 3.3 Contrat `DATA` / `STATE` — ce qui change par rapport à la page actuelle
**Réel depuis 4a.** `DATA` = contrat du brief § 5.2 conservé, plus `meta.imports[{id, empreinte}]` (4b, les imports retenus pour la plage), `meta.non_couverts[]` (dates sans import), `meta.alertes[]` (personne exclue, agenda sans ligne, code en collision, seuils par défaut), `attentes[]` (demandes `en_attente`, informatives). `conges[]` = absences **effectives** de toute nature, une entrée par jour, `bloque = type.bloquant`, `type = libelle` (C4.1) ; une absence `Ecole` d'une étudiante alimente `cours` seulement ; les absences de personnes hors périmètre sont écartées sans alerte. `STATE` = `affectations`, `feries`, `feries_off`, `notes` — rien d'autre (nettoyé côté serveur, `notes` normalisées en liste). Identifiant = `Personne.code`, repli déterministe `code_pour + pk` avec alerte. Export JSON : `mois`, `numero`, les quatre clés, `exporte`. Une absence corrigée à 0,5 reste un jour bloqué (C3.3).

---

## 4. Modèle de données *(figé aux diff plans 1a, 1b et 3 — noms définitifs ; `PlanningVersion` reste indicative)*

| Table | Champs | Notes |
|---|---|---|
| **Personne** *(1a, `comptes.Personne`)* | id, `code` (unique, nullable), nom, prenom, `role_metier`, `heures_hebdo`, `jours_fixes` (JSON), `planifiee`, couleur, `agenda_doctolib`, `email_contact`, actif, `cree_le`, `modifie_le` | jamais : NSS, naissance, téléphone, IBAN, adresse. Contrainte d'unicité (nom, prénom). `modifie_le` n'avance pas lors d'un upsert d'import (`update_fields` sans `auto_now`) — constaté en Phase 1 de la 3 |
| **Compte** *(1a, AUTH_USER_MODEL)* | email (unique), `personne` (OneToOne, PROTECT, nullable), `role`, is_active, is_staff, is_superuser, `invite_le`, `active_le`, `date_creation`, last_login, **`email_en_attente`** *(3)* | mot de passe toujours inutilisable ; `email_en_attente` porte la nouvelle adresse le temps de sa confirmation et rend le jeton à usage unique (§ 5.1) |
| **TypeAbsence** *(3, `absences.TypeAbsence`)* | `libelle` (unique), `bloquant`, `categorie` (`demande` / `declare`), `paie`, `actif`, `ordre` | 13 valeurs posées par migration de données idempotente (`get_or_create` sur le libellé, jamais de réécriture), **orthographe du select Notion reproduite telle quelle** (« Congé évenement familial », « Décés », « Ecole ») ; demandés : Congé payé, Congé sans solde ; paie : ces deux-là plus Maladie, Congé enfant malade, Congé grossesse ; bloquants : les huit premiers du brief § 6 ; modifiable par `cabinet` |
| **AbsenceSalariee** *(3, `absences.AbsenceSalariee`)* | `personne` (FK, PROTECT, `limit_choices_to` assistante / secrétaire), `date_debut`, `date_fin` (`CheckConstraint date_fin >= date_debut`), `type` (FK, PROTECT), `statut` (indexé), `precision` (120 car., facultative), `auteur` (SET_NULL), `cree_le`, `decide_par` (SET_NULL), `decide_le`, `jours_comptes_calcules` et `jours_comptes` (`Decimal(4,1)`), **`jours_retenus`** (JSON, dates ISO), `corrige_par` (SET_NULL), `corrige_le`, `a_effacer_le` (nullable) ; index (personne, date_debut) | **deux valeurs de jours comptés** : la calculée n'est jamais touchée par une correction, la retenue n'est jamais touchée par un recalcul si l'absence est corrigée ; **`jours_retenus`** porte les dates figées au calcul, base de la répartition par mois (C3.6). Décision P (personne salariée seulement) tenue dans `services.creer`, `services.decider`, `clean_personne` et `save_model` de l'admin — `limit_choices_to` n'est qu'un filtre de formulaire. Ni suppression douce ni immuabilité : `annulee` en tient lieu ; une suppression depuis l'admin est journalisée (3-ter) |
| **ImportPresences** *(1b)* | inchangé | |
| **VerrouImport** *(1b)* | inchangé | |
| **CompteurDebit** *(2)* | inchangé | |
| **PlanningVersion** *(4a, figée en 4b, `planning.PlanningVersion`)* | `mois` (char 7), `numero`, `state` (JSON, quatre clés), `version_de_base` (`PositiveIntegerField(default=0)`, **non nul depuis `0002`**), `auteur` (SET_NULL), `cree_le`, `verifications` (JSON : `[]` tant que non publiée ; `{verifie_le, imports[{id, empreinte}], nb_briques}` à la publication), `publiee` (défaut faux), `publie_le` (nullable), `publie_par` (SET_NULL) ; contrainte unique `(mois, numero)` | chaque « Enregistrer » = une ligne ; la publication écrit quatre champs sur la ligne existante, jamais une nouvelle ; rien ne s'efface (admin lecture seule) ; plusieurs `publiee=True` possibles par mois, la courante est la dernière par numéro |
| **EvenementAudit** *(1a)* | `quand`, `qui` (SET_NULL), `action`, `type_objet`, `id_objet`, `details` (JSON) | **sans** type d'absence, précision, donnée de santé, donnée patient, adresse. Actions 1a / 1b / 2 : inchangées. **Actions 3** : `absence_demandee`, `absence_declaree`, `absence_decidee`, `absence_annulee`, `absence_corrigee` (calculé et retenu), `absence_purgee`, `paie_consultee` (mois et nombre de salariées, jamais le contenu), `adresse_changee` ; **3-ter** : `absence_supprimee` (personne, statut, dates). **4a** : `planning_enregistre` (mois, numéro, nombre de briques). **4b** : `planning_publie` (mois, numéro, nombre de briques) ; `absence_conflit_publication` (`personne_id`, `mois`, `numero`, `dates` — jamais le type). `details` ne porte que des identifiants, dates, statuts, comptages — la garde `@` ne reconnaît pas « Maladie », le reste se tient à la main et se prouve par `absences/tests/test_confidentialite.py` |
| **Règles** | `regles.json` versionné, chargé et validé au démarrage | **3** : section obligatoire `periodes_ouverture` (première période non datée = origine, suivantes à date strictement croissante, jours canoniques) ; un fichier sans elle refuse de démarrer — pour de la paie, un défaut d'ouverture silencieux serait pire |

Fériés français : `socle/feries.py`, fonction pure (Pâques incluse), désactivables par mois dans `STATE` (brique 4). Un praticien sans agenda Doctolib apparié n'a pas de mécanisme d'absence : ses jours fixes valent présence.

---

## 5. Sécurité et données

### 5.1 Identité *(1a, complétée en 3 et 3-ter)*
- **Lien magique** django-sesame (15 min, usage unique, invalidation au changement d'adresse). Aucun mot de passe, aucun compte partagé.
- **Création protégée, adresse libre** : invitation sans jeton, compte cabinet assuré au pré-déploiement, commande de secours `lien_connexion`.
- **Changement d'adresse par la salariée — livré en 3** : jeton signé `django.core.signing` portant compte et nouvelle adresse (valable une heure), envoyé à la **nouvelle** adresse ; usage unique par `email_en_attente`, vidé à la confirmation ; adresse déjà prise → réponse neutre sans envoi (doctrine de `/connexion/`) ; `Personne.email_contact` suit ; les liens de connexion en circulation sont invalidés à l'effet (`SESAME_INVALIDATE_ON_EMAIL_CHANGE`). Audité `adresse_changee`, sans l'adresse.
- HTTPS et redirection fournis par Railway ; **`SECURE_HSTS_SECONDS = 31536000` depuis 3-ter** (un an ; sous-domaines et preload restent à `False`, `check --deploy` le signale et c'est voulu).
- Canal d'envoi : C2.9 = a.

### 5.2 Droits et minimisation
- Contrôle porté par `role_requis` ; `/connexion/` et l'API n8n limités en débit (2).
- **3** : `salariee` ne voit que ses absences ; `principale` et `cabinet` voient toutes les absences avec leur type (C2.3b) ; `principale` a aussi son propre espace (3-bis) ; `cabinet` n'y a pas accès (403, conforme).
- **4a** : sept surfaces testées sans nom ni type (`test_confidentialite`) : `state` reçu, `PlanningVersion.state`, export JSON (test Node), audit, logs des vues, corps de `/api/erreurs/`, absences hors périmètre ; `DATA.conges[].type` servi à `cabinet` et `principale` seulement (403 / 302). Les violations sont des codes `{code, date, slot, s}`, le message français est composé par la page.
- **4b** : « Mes jours » ne sert jamais `DATA` (les libellés sont calculés côté serveur depuis le `state` et les personnes) ; testé sans nom d'une autre salariée ni libellé de type ; `cabinet` → 403. Corps de `planning.publie` et `absence.conflit`, audit et logs de publication testés sans nom ni type (`test_confidentialite`, `test_publication`, `test_conflits`).
- **Sorties hors de l'app** — exactement une porte les noms : l'endpoint de paie, réservé à n8n, qui transmet **nom, dates, nombre de jours indicatif et, depuis C5.1 (brique 5), la catégorie de paie — jamais la précision**. Les webhooks d'absence portent identifiants, dates, statut, lien — rien d'autre. Vérifié en recette (§ 14).

### 5.3 Audit et journaux *(1a, étendus 1b, 2, 3, 3-ter)*
- Journal d'audit : toutes les transitions d'une absence, la correction, la consultation de paie, le changement d'adresse ; **la suppression d'une absence depuis l'admin (3-ter)** — `Personne` et `Compte` l'étaient depuis 2-bis, `AbsenceSalariee` ne l'était pas, six absences fictives ont disparu sans trace en recette.
- **La leçon du `SET_NULL`, vue en vraie grandeur** : la suppression du compte fictif de recette a vidé la colonne « qui » de dix-sept événements en une seconde. Sur une salariée réelle, ce serait la perte de qui a demandé quoi. Règle réaffirmée : **désactiver, jamais supprimer** ; le correctif structurel monte en tête du backlog (§ 12).
- Logs applicatifs : aucune absence nominative, aucun type, aucune précision, aucune adresse, aucun secret — vérifié en recette sur la fenêtre couverte (§ 14, R2 sur la fenêtre manquante). Les lignes ne disent que « absence #N creee (statut …, N jour(s) de plage) », « decidee », « corrigee », « webhook absence transmis (statut 200) », « paie AAAA-MM consultee : N salariee(s) » ; **4b** : « planning AAAA-MM : version N publiee (N briques) », « absence #N en conflit avec N planning(s) publie(s) », « mes jours AAAA-MM : N jour(s) », « webhook planning non configure ». Vérifié en recette 4b sur toute la fenêtre (§ 14).

### 5.4 Rétention
- **Mécanisme livré en 3 (C3.5)** : `a_effacer_le` posé à l'entrée en état effectif si `RETENTION_ABSENCES_JOURS` est réglée ; commande `purger_absences` (pose d'abord les échéances manquantes, puis purge, journalise `absence_purgee` ; réglage absent = ne fait rien et le dit) ; commande `recalculer_jours_comptes` (rejoue le calcul, ne touche jamais une absence corrigée).
- **Durées à fixer avec le conseil du cabinet** — C2.6 (§ 10). Rien ne casse tant qu'elles ne le sont pas.

### 5.5 Secrets *(noms réels)*
- 1a / 1b / 2 : inchangés. **3** : `N8N_ABSENCE_WEBHOOK_URL` (posée le 04/09/2026 ; absente = notification muette, « webhook absence non configure » dans les logs) et `RETENTION_ABSENCES_JOURS` (**absente à ce jour**, volontairement). **4b** : `N8N_PLANNING_WEBHOOK_URL` (**absente**, à poser avec le workflow de la brique 5). Jamais dans le code, jamais dans un chat.

### 5.6 Frontières
- Inchangées. Rappel tenu en 3 : merge = migrations sur la base de production (trois en 3, aucune en 3-bis ni 3-ter) ; premier mail de décision à une salariée réelle : tir de test vers Yohan d'abord — fait en recette sur une personne fictive, les trois webhooks reçus.
- **Exposition n8n** : aucun des trois nouveaux workflows n'est « Available in MCP », vérifié à la création.

---

## 6. Surfaces

### 6.0 Présences *(1b)* — inchangé.

### 6.1 Page planning, versions et publication *(4a, 4b ; `principale` et `cabinet`)*
- `GET /planning/` (mois courant), `GET /planning/<AAAA-MM>/` (page ; écran « aucun import ne couvre ce mois » si aucun import), `GET /planning/<AAAA-MM>/copie/` (HTML autonome de la dernière version, scripts inlinés par `finders.find`, 404 sans version).
- `POST /api/planning/<AAAA-MM>/versions/` : `{version_de_base, state}` → 201 `{numero}` ; 409 `{derniere}` ; 422 `{violations}` sans texte ; plafond 1 Mo ; session + CSRF (`{% csrf_token %}` explicite).
- `POST /api/erreurs/` : `{nom, source, ligne, mois}`, `limite_par_ip` puis `role_requis`, 202, log seul.
- « Enregistrer une copie » grisée tant que l'état diffère de la dernière version ; `beforeunload` ; pas de brouillon navigateur (C2.8 appliquée).
- **4b** — `POST /api/planning/<AAAA-MM>/versions/<n>/publier/` : sans corps ; 200 `{numero, publie_le}` ou `{numero, deja_publiee}` ; 409 `{derniere}` ; 422 `{violations}` ; 400 `mois_invalide` / `numero_invalide` ; 405. Bouton « Publier » actif seulement si la page affiche la dernière version sans modification et qu'elle n'est pas déjà publiée ; refus par la page avant l'appel si une règle stricte est enfreinte ; `META.publiee` et `urls.publier` servis au rendu, recalculés après un enregistrement.

### 6.2 Espace salariée (`salariee`, `principale` depuis 3-bis) *(3, complété en 4b)*
- **4b** — `GET /mes-jours/` (mois courant) et `GET /mes-jours/<AAAA-MM>/` : C4.8 ; lien « Mes jours » dans l'accueil des deux rôles.
- `GET /mes-absences/` : ses absences (motif, état, jours comptés), demande ou déclaration, annulation d'une demande en attente.
- `GET/POST /mes-absences/nouvelle/` : type (types actifs, dans l'ordre), dates, précision courte.
- `POST /mes-absences/<id>/annuler/`.
- `GET/POST /mon-profil/` et `GET /mon-profil/confirmer/<jeton>/` : changement d'adresse (§ 5.1).
- Compte sans `Personne` liée : page « votre compte n'est pas encore rattaché à une fiche », aucune saisie, jamais de 500 (décision H).

### 6.3 Administration et décision *(3)*
- `GET /absences/` (`principale`, `cabinet`) : demandes à décider, puis absences du mois ; **4b** : bandeau « N absence(s) tombent sur un jour du planning publié » et marqueur « conflit : AAAA-MM vN (dates) » sur la ligne, recalculés au rendu (semaines complètes, comme le planning — la paie seule est calendaire) ; signal « contrat incomplet » sur les absences dont le calcul a rendu 0 (décision N).
- `POST /absences/<id>/decider/` (règle K côté serveur), `POST /absences/<id>/corriger/` (multiple de 0,5, ≥ 0, ≤ jours de la plage).
- Admin Django : `TypeAbsence` modifiable ; `AbsenceSalariee` en création, modification et suppression journalisée ; **3-quater** : écran « Importer un fichier » (`/admin/absences/absencesalariee/importer/`, rôle `cabinet`, `role_requis` hors `admin_view`) — fichier JSON ≤ 1 Mo, rapport d'analyse (verdicts `à créer` / `déjà présente` / `erreur`, jours comptés, signal, conflit avec un planning publié), confirmation liée à l'empreinte SHA-256 et rejouée après 15 minutes, écriture tout ou rien, audit `absence_importee` par absence et `import_absences` par confirmation ; les absences ne portent que des personnes assistante / secrétaire (`clean_personne` rend une erreur de champ lisible ; `save_model` est le dernier rempart).

### 6.4 Garde-fous de la décision A *(4a, en place)*
1. Règles strictes revérifiées par le serveur (`planning/verification.py`) à chaque enregistrement, mêmes codes que le moteur JS, **un seul jeu de cas** (`cas_verification.json`) lu par les deux suites. La proposition reste dans la page.
2. Moteur JS isolé (`moteur.js`, fabrique `creer(DATA, state)`, aucune fonction n'appelle `commit` / `render` / `toast` / `confirm`), 55 tests Node (`node:test`, sans npm) ; critère de brique = reproduction exacte d'une proposition figée depuis Chrome avec le gabarit d'origine (129 briques, zéro écart).
3. `POST /api/erreurs/` branché sur `window.onerror` et `unhandledrejection`.

### 6.5 API n8n *(1b, complétée en 3)*
- 1b : `GET /api/n8n/sante/`, `POST /api/n8n/imports/`. Inchangés.
- **3** : `GET /api/n8n/paie/<AAAA-MM>/` (`re_path`, slash final) → `{"mois","debut","fin","salariees":[{"personne_id","nom","code","jours_comptes","absences":[{"absence_id","debut","fin","jours_comptes","jours_comptes_absence","facture_partiellement","corrigee","repartition_calculee"}]}],"paragraphe"}` ; 400 `mois_invalide` ; même patron 429 → 503 → 401 → 405 (recetté : quatre 401, POST compris). `facture_partiellement` dit que la portion de ce mois diffère du total — **pas** que l'absence traverse une frontière de mois (renommé depuis `a_cheval` avant le premier merge, aucun consommateur).
- Sortant : `import.termine` / `import.echec` (1b) ; **`absence.demandee`, `absence.declaree`, `absence.decidee` (3)** — trois événements au lieu des deux du § 6.5 v1.3 ; corps `{evenement, absence_id, personne_id, debut, fin, statut, lien, horodatage}` ; l'annulation est auditée sans webhook ; **4b** : `planning.publie` (corps C4.11, URL `N8N_PLANNING_WEBHOOK_URL`) et `absence.conflit` (corps C4.12, URL absence). Workflow « Planning assistantes – Absences (réception) » : id `eQABsWqayUIR8KuY`, Webhook → Gmail vers Yohan, lit `evenement` dynamiquement, export dans `docs/n8n/`.
- Ce que n8n ne peut pas demander : « calcule la proposition » (décision A).

### 6.6 Import des présences *(1b)* — inchangé.

---

## 7. Règles métier
Implémentées et validées, **pas à re-décider** : brief § 5.4, `regles.json`, et désormais :

**Jours comptés (3, `absences/calcul.py`, module pur)** — **indicateur interne depuis C5.1** : la paie réelle compte les CP et les maladies en jours ouvrables (lundi → samedi, fériés exclus) et le sans-solde en jours réellement non travaillés ; la formule ci-dessous ne coïncide qu'avec ce dernier. Formule C3.1, version corrigée en revue de Phase 2 (la v2 déduisait un férié tombant un jour fermé, et comptait un même jour dans `J` et dans `F`). Ordre des branches aligné sur l'avertissement d'import de la 2 : heures dans les gabarits → contrat horaire ; heures hors gabarits → 0 et signal ; pas d'heures mais jours fixes → jours fixes hors fériés ; ni l'un ni l'autre → 0 et signal. Le plafond `max(0, B − F)` s'applique **une fois par semaine, sur la semaine entière**, et ce sont les **premiers** jours ouvrables de la semaine qui sont retenus : `Resultat.dates` porte les dates, `jours == len(dates)`. Cas de référence (régime mardi→samedi, 39 h) : 07→11/04/2026 = 4 ; 26→30/05 = 4 ; 14/05 seul = 0 ; 12→16/05 = 3 ; 27 h, 29/09→03/10 = 3 ; samedi 03/10 = 1, samedi 10/10 = 0.

**Périodes d'ouverture (3, `regles/chargeur.py`)** — C3.2 ; `jours_ouverture(date)` retient la dernière période dont la date de début est passée.

**Paie (3, `absences/paie.py`)** — C3.6 ; `plage_calendaire` (jamais `presences.fenetres.plage_mois`) ; `portions_par_mois` : non corrigée → un jour retenu vaut un jour au mois où il tombe ; corrigée → prorata au demi-jour inférieur, reliquat au mois du premier jour retenu ; corrigée sans jour retenu → tout au mois de `date_debut`, `repartition_calculee = false` et alerte dans le paragraphe.

**Règles strictes du planning (4a, `planning/verification.py` et `moteur.js`)** — treize codes : `hors_plage`, `salariee_inconnue`, `slot_inconnu`, `brique_invalide`, `doublon_jour`, `jour_bloque` (congé bloquant, cours, **tout férié effectif samedi compris**), `jour_non_affiche`, `sans_donnees`, `praticien_absent`, `capacite`, `exclusive_ailleurs`, `exclusif_intrus` (C4.4), `quota_depasse` (port de `reserve` ; seul endroit où un férié ne consomme une brique que du lundi au vendredi). Les règles relatives (binômes, administratif, continuité, équité) restent dans `proposer`. **4b n'ajoute aucun code** ; la revérification à la publication réutilise `verifier` sur `DATA` recalculé.

**Conflit absence ↔ planning publié (4b, `planning/conflits.py`)** — C4.7 ; `mois_candidats(debut, fin)` (mois dont la plage de semaines complètes touche l'absence) et `conflits_dans_state(state, sid, dates)` sont pures ; `conflits(personne, debut, fin)` lit la version publiée de chaque mois candidat et rend `[{mois, numero, dates}]`.

**Lecture d'un payload S7 (1b)** et **lecture de la fiche personnel (2)** — inchangées.

---

## 8. Briques

| # | Brique | Projet | Contenu | Livrable / critère de succès | État |
|---|---|---|---|---|---|
| 0 | Endpoint `POST /admin/presences` | **VoiceDoctolib** | Phase 1 → 5, contrat aligné sur le client de la 1b | 200 avec le payload S7 tel quel ; 401 ; zéro PHI en logs | à faire |
| 1a | Socle + connexion | ce projet | | | **✅ 27/08/2026** |
| 1b | Présences + API n8n | ce projet | | | **✅ 31/08/2026** |
| 2 | Personnes et règles | ce projet | | | **✅ 31/08/2026** (2-bis, 2-ter, 2-quater) |
| **3** | **Absences** | ce projet | types et catégories, espace salariée, décision, jours comptés et **répartition par mois**, endpoint de paie, rétention (mécanisme), changement d'adresse, client n8n factorisé, jours fériés ; **pas de migration Notion** (C3.8) | jeu fictif de cas datés vérifié à la main ; workflow demande → décision → salariée exercé en production sur une personne fictive ; paie calendaire, correction à 0,5, quatre 401 ; logs et audit sans nom, type, précision ni `@` | **✅ 03/09/2026** (3-bis 04/09, 3-ter 06/09 — § 14) |
| **4a** | **Planning — page servie, versions** | ce projet | `DATA` serveur, moteur isolé, double vérification, versions 409 / 422, copie, erreurs, suppression du brouillon | proposition de référence reproduite à la brique près ; 409 en production ; refus page sur praticien absent ; logs sans nom ni type | **✅ 06/09/2026** (R4a-1 différé) |
| **4b** | **Planning — publication** | ce projet | publication (C4.5, C4.6, audit, webhook), conflit absence / planning publié (C4.7), « Mes jours » (C4.8), ligne « hors présence » (C4.9), `version_de_base` non nul (C4.10), `meta.imports` | v4 → v8 de septembre publiées en production ; « Mes jours » d'une personne fictive ; conflit signalé par audit, webhook et bandeau ; 422 serveur sur enregistrement ; import de la brique orpheline manipulable ; logs sans nom ni type | **✅ 07/09/2026** (R4b-1) |
| **3-quater** | **Reprise de l'existant 2026** | ce projet | écran d'import admin (C3.9), `services.importer / analyser_import / executer_import`, `FormulaireImport`, deux actions d'audit ; aucune migration | 201 absences importées en production depuis le fichier arbitré sur les bulletins ; ré-import → « déjà présente » partout ; conflits de septembre signalés dans le rapport ; logs sans nom ni type | **✅ 07/09/2026** |
| 5 | Notifications | n8n | mail comptable depuis `GET /api/n8n/paie/` (**dates + catégorie de paie, C5.1**) ; workflow `planning.publie` + `N8N_PLANNING_WEBHOOK_URL` ; tir de test vers Yohan ; mails du backlog si souhaité | ancien workflow désactivé, pas supprimé | à faire |

Jeu de données de la 1b : inchangé. Jeu d'absences : **fictif** exclusivement, en tests comme en recette (personne `TEST Recette`, supprimée après).

---

## 9. Régime de travail (rappel)
WORKING_HABITS s'applique intégralement. **Confirmé en pratique sur 1a, 1b, 2 et 3** : le diff plan exhaustif comme checkpoint unique ; la revue technique de Claude Code contre le code réel entre v1 et v2 du plan (une correction **bloquante** en 3 : la formule de paie) ; **la relecture du checkpoint diff par Claude conversationnel a trouvé en 3 un défaut de paie que 606 tests verts ne voyaient pas** — les tests étaient verts sur un comportement faux, parce que le plan ne disait pas sur quelle plage la paie devait filtrer ; l'assistance interactive à la recette (jeu local, contrôles négatifs, comptage de logs) ; les gestes dans le navigateur, n8n et l'admin à Yohan.

---

## 10. Points restants (implémentation, pas périmètre)

| # | Question | Options | Tranché |
|---|---|---|---|
| C2.6 | **Valeur** des durées de rétention (absences, données ayant servi à la paie, versions, audit) | à fixer avec le conseil du cabinet ; **le mécanisme est livré (C3.5), la valeur se pose dans `RETENTION_ABSENCES_JOURS`** | avant que la première absence réelle atteigne une échéance plausible |
| ~~—~~ | ~~Calcul des jours comptés ; correction par la validatrice~~ | **tranché C3.1 / C3.3, livré en 3** | ✅ 01/09 |

---

## 11. Éléments d'entrée à fournir
- ~~**Étalon de paie**~~ — **acté le 07/09/2026** autrement que prévu : les **bulletins de janvier → août** (rubriques d'absence avec dates, lus par Claude conversationnel, jamais versés) ont servi d'étalon, plus fiable que la sortie du workflow Notion. Résultat : sans-solde identique ; CP et maladies décomptés en **jours ouvrables** par la comptable (Cécile 03 → 29/08 : 24 sur bulletin, 12 par C3.1). D'où C5.1. Le workflow « PROD – Fiche de paie V2 » n'a jamais été retrouvé ; il n'est plus nécessaire.
- ~~**R4a-1 — planning réel de septembre 2026**~~ — **acté le 06/09/2026** : brouillon du 25/08 repris depuis Chrome, 25 jours importés dans `/planning/2026-09/`, **une violation expliquée** (`praticien_absent` le 09/09 : Doctolib avait bougé entre le 25/08 et l'import #6), corrigée par export JSON puis enregistrée en **version 4**. Écart de page **E1** (brique orpheline invisible) → C4.9. Les absences de septembre restent à ressaisir (C3.8) pour que les compteurs redeviennent fidèles.
- Fournis le 26/08 : capture de la page « Absence » et du select `Type` ; export du workflow de paie. La formule Notion « Durée » n'a jamais été fournie : la formule C3.1 a été fixée sans elle, l'étalon ci-dessus est le filet.

---

## 12. Backlog (hors v1, sans décision)
- ~~`PlanningVersion.version_de_base` nullable~~ — **fait en 4b (C4.10)**.
- **Issus de la 3-quater** : l'écran d'import n'a plus de source (Notion est archive) — le garder ou le retirer en v2 ; « Absence justifiée » n'a pas été créée (aucune entrée sans type après arbitrage) ; deux Lea dans la fiche → `identifiant()` les distingue par le nom, les libellés courts de la page (« Lea D », « Lea W ») restent à la charge de la page.
- **Issus de la recette 4b** : le `DATA` d'un onglet ouvert vieillit (une absence saisie après le rendu n'est vue qu'au refus serveur) → rechargement au focus ou « données du … » dans l'en-tête ; toast d'`afficherViolations` sur un 422 de publication (« rien n'a été enregistré ») ; `__str__` d'`EvenementAudit` en UTC alors que « Quand » est en Paris ; style de l'étiquette « hors présence » (badge noir, à aligner sur un libellé italique) ; un jour hors colonnes portant une brique orpheline (export JSON seul).
- **Conservation structurelle de l'auteur d'un événement d'audit après suppression de son compte** — **monte en tête** : vu en vraie grandeur en recette 3 (§ 5.3). Tant que ce n'est pas fait, la règle « désactiver, jamais supprimer » est la seule protection.
- Mails : demande → validatrice ; décision → salariée ; publication → chaque salariée ; conflit après publication → principale ; correctif de paie après le 20. Les webhooks `absence.*` de la 3 sont les déclencheurs prêts.
- **Annulation d'une demande (S2e)** : non exercée en production, couverte par les tests — à exercer à la première occasion réelle.
- **Saisie native en demi-journées** (champs matin / après-midi) si la correction manuelle devient trop fréquente ; changerait le modèle et le planning.
- **Export de logs Railway** : plafonné, et un redéploiement coupe la fenêtre — exporter par déploiement ; un connecteur Railway en lecture pendant la recette éviterait la manipulation (à instruire).
- Hygiène post-recette 2 : inchangée (pluriel du rapport d'import, avertissement « absente du fichier »).
- Types « paie » supplémentaires : drapeau à cocher par `cabinet`, aucune décision.
- Le « entre autres » ; exposition de l'app à Claude via MCP ; vue « Mes jours » adaptée au téléphone (la page 4b est minimale, non stylée) ; passage de la logique côté serveur (option B) ; hygiène du conftest racine (partiellement réglée en 3 : fixtures remontées, bloc `os.environ` toujours inopérant) ; performance de `couverture()` ; verrou d'import non supprimable ; point d'état par lot ; second tir du canari ; taux de remplissage ; doctrine des couleurs — inchangés.
- ~~HSTS à un an~~ — **fait en 3-ter**.
- ~~Limitation de débit~~ — livrée en 2. ~~Factorisation du client n8n~~ — **faite en 3 (C3.7)**.
- **Hors projet, pour VoiceDoctolib** : le serveur MCP journalise en clair l'adresse du compte technique Doctolib (« Email saisi », « Polling IMAP … ») — 18 occurrences dans 999 lignes, constaté en cherchant un export de logs pendant la recette 3.

---

## 13. Glossaire
Inchangé depuis la v1.3, plus :
- **Jours comptés** : ce que la paie décompte pour une absence ; **calculés** (par la formule C3.1, jamais modifiés) et **retenus** (la valeur envoyée, corrigeable). **Jours retenus** : les dates que la formule a réellement comptées, figées au calcul ; base de la répartition par mois.
- **Portion** : la part des jours retenus d'une absence qui tombe dans un mois calendaire donné.
- **Période d'ouverture** : les jours de la semaine où le cabinet ouvre, à partir d'une date ; sert au calcul de paie, pas au planning.
- **Contrat incomplet** : personne sans heures ni jours fixes, ou aux heures hors gabarits ; le calcul rend 0 et un signal, la validatrice saisit.
- **Recouper** (interdit) : découper une absence par mois pour relancer le calcul sur chaque morceau — le plafond hebdomadaire s'appliquerait deux fois.

---

## 14. État des briques et journal de livraison

### Briques 1a, 1b, 2 — inchangées (voir v1.3).
Complément 2 : la **désignation de la principale** dans l'admin et l'**envoi réel des invitations** aux salariées restent des gestes de Yohan, non datés à ce jour.

### Brique 3-quater — Reprise de l'existant 2026 — ✅ livrée le 07/09/2026
- Branche `brique-3quater-import-absences` (créée depuis `origin/main` = `94b376a`), commit `ec9bba4`, **hash post-squash `6de17f1`** (PR #19). 5 fichiers modifiés, 4 nouveaux (+687 / −4 hors nouveaux) ; **874 tests Python** (+49), 57 Node ; aucune migration.
- **Démarche** : Yohan rouvre C3.8 le 07/09 (« tout importer sur l'année 2026, exceptionnellement, puis plus de Notion ») → analyse Notion en lecture seule (1 900 entrées, 446 nominatives, 6 ambiguïtés tranchées : « Lea » = Lea Dehu, vérifié sur 1 113 entrées « Présence » ; Kelly sans fiche écartée ; personne prime sur le titre ; « école » → Ecole ; Clara étudiante jusqu'au 16/06) → décisions I1 → I3 (tous types, écran admin, effectif sans webhook) → **rapprochement avec les bulletins de janvier → août** (70 rubriques, dates comprises) : 15 écarts, règle « la fiche de paie prime » → diff plan v1 → revue technique (1 bloquant : ordre `save()` / calcul ; 14 écarts) → v2 → Phase 3 en continu → checkpoint diff (8 écarts acceptés) → merge → recette.
- **Recette (07/09, production)** : T1 rapport 190 lignes / 7 erreurs = chevauchements internes de mon fichier (fusion trop large, école pendant un arrêt maladie) → fichier v2, 195 / 0 erreur ; T2 195 créées ; T3 ré-import → « déjà présente » partout ; T4 conflits avec la v8 de septembre listés (Clara 01–02/09, Amandine 17/09) puis v9 publiée après retrait de la brique de Lea W du 02/10 (école du 28/09 → 3 briques dans la semaine) ; T5 tir `2026-08` → **7 blocs de CP fusionnés à tort** (jours d'ouverture inventés entre des jours isolés : Lea D 8 au lieu de 6) → 7 + 1 absences supprimées dans l'admin (journalisé), fichier v3 (fusion seulement à travers dimanche, lundi, férié pour les CP ; strictement consécutive sinon), 14 créées, 187 déjà présentes → **201 absences**, Lea D à 5 ; logs sans nom ni type.
- **Réserve** : aucune. Le fichier `absences_2026.json` et les bulletins restent chez Yohan, hors dépôt.
- **Reste ouvert** : Phase 6 docs (« aucune migration » dans docs/ABSENCES.md § 9, CLAUDE.md, docstring `absences/admin.py`) ; brique 5 avec C5.1 ; brique 0.

### Brique 4b — Planning, publication — ✅ livrée le 07/09/2026
- Branche `brique-4b-publication`, commit `92649d7`, **hash post-squash `0a53bdf`** (PR #17). 24 fichiers modifiés et 7 nouveaux (+671 / −42) ; **825 tests Python** (+47) et **57 Node** (+2) ; une migration en production (`planning.0002`, `RunPython` 0 ligne touchée + `AlterField`).
- **Démarche** : R4a-1 exercé d'abord (06/09 soir) → Phase 1 (rapport de 3 239 lignes, 20 questions ouvertes, écarts au cadrage v1.3 faute de v1.5 sur disque) → décisions Yohan A → F puis P1 / P2 / Q7 → diff plan v1 → **revue technique Claude Code : 7 bloquants** (`deepEqual` d'`importer`, `courant == 0`, `PositiveIntegerField`, crochet admin rejouant à chaque édition, `identite.py` inutile, cycle `donnees`/`services`, fixtures) → v2 → **seconde revue** (cycle `services ↔ webhooks` réintroduit par la v2, `get(mois, numero)`, `Exists` validé sur SQLite en mémoire) → v2.1 → Phase 3 en continu → checkpoint diff (5 écarts nommés, tous acceptés, dont `META.urls.publier` recalculé après un 201, trou du plan) → merge → recette dans la nuit et au matin.
- **Recette (06–07/09, production, personne fictive `TEST Recette`)** : S2 ✓ v4 publiée, `deja_publiee`, v5, v6 ; S3 ✓ « Mes jours » (sa journée seule, italique annoncé), 403 cabinet ; S4 ✓ absence bloquante depuis l'admin → audit `{mois, dates, numero, personne_id}`, mail `absence.conflit` avec `conflits[]`, bandeau ; changement de type → rien (B4) ; S5 ✓ **422 serveur sur enregistrement** (page rendue avant la saisie de l'absence : le serveur voit ce que la page ne voit pas), refus page à la publication après rechargement ; S6 ✓ import du JSON original → « Noemie · hors présence · absent ce jour-là », brique glissée en Sureffectif ; S7 ✓ logs complets sans nom ni type, migration OK. Versions 7 et 8 enregistrées, **v8 publiée**. Nettoyage : compte et personne fictifs **désactivés**, absences fictives supprimées (journalisé).
- **Réserve R4b-1** : le 422 serveur **à la publication** est couvert par `test_publication` mais n'a pas été vu en production (la page l'a refusé avant l'appel).
- **Reste ouvert** : brique 5 (workflow `planning.publie` + variable) ; ressaisie des absences de septembre ; désignation de la principale et invitations réelles ; brique 0.

### Brique 4a — Planning, page servie et versions — ✅ livrée le 06/09/2026
- **PR #15**, commit de branche `13a717e`, **hash post-squash `5072226`**. 10 fichiers modifiés (+134 / −14) et l'app `planning` nouvelle (≈ 9 000 lignes fixtures comprises) ; **778 tests Python** (+127) et **55 tests Node** ; une migration en production (`planning.0001`, table nouvelle, rien d'existant touché). Phase 6 (docs) : branche `brique-4a-phase-6-doc`, commit `71a360e`, **post-squash `8714d52`** (docs/PLANNING.md nouveau, README, CLAUDE.md, formule exacte pour `regles.json`).
- **Démarche** : Phase 1 (rapport de 847 lignes, 29 écarts, 22 questions) → choix Yohan (4a / 4b, C4.1, « mes jours » en 4b) → diff plan v1 → **revue technique v1 : 9 corrections dont 4 comportements faux** (fériés, numéro sous deux workers, école comptée deux fois, absences informatives perdues) → v2 → **revue v2 : 4 corrections dont une destructrice** (`initialise` retiré → re-proposition par-dessus la version enregistrée, C4.3) → v3 → 3-pré (poste resynchronisé, `diff --stat 06eecf9 b243f10` vide, gabarit fictif, proposition figée par Yohan dans Chrome) → Phase 3 en continu → checkpoint diff (13 écarts nommés, tous acceptés, C4.4) → merge → recette le soir même.
- **Recette (06/09, production)** : imports S7 #6 (248 lignes) et #7 (32) ; versions 1 → 3 ; **409 réel** entre deux onglets avec bandeau et « Recharger » ; import d'un JSON bricolé (brique sur un praticien non planifié) → **refus par la page** avant envoi, message composé du code ; copie autonome ouverte hors ligne sans erreur ; logs sans nom ni type. **R4a-1** différé (§ 11) : le fichier de l'assistante était vide — le planning de septembre vit dans un cache de navigateur.
- **Reste ouvert** : ~~R4a-1 ; hygiène `version_de_base` ; cadrage 4b~~ — tout réglé en 4b.

### Brique 3 — Absences — ✅ livrée le 03/09/2026 (3-bis 04/09, 3-ter 06/09)
- **PR #12**, deux commits de branche (`100361e`, `5b2e61b`), **hash post-squash `e2c751d`**. 64 fichiers, +5 736 / −129, 638 tests. **3-bis** (E1) : PR #13, commit `862699e`, **post-squash `d6860a9`**. **3-ter** (E2 + HSTS) : commit `06eecf9`, **post-squash `b243f10`**, 651 tests. Trois migrations en production (`comptes.0003`, `absences.0001`, `absences.0002`), aucune en 3-bis ni 3-ter.
- **Démarche** : Phase 1 d'inspection (01/09, rapport de 7 234 lignes, noms masqués par jetons stables) → diff plan v1 → décisions A–M → v2 → **revue technique de Claude Code : 15 corrections, dont une bloquante sur la formule de paie** → décisions N–P → v3 validé → Phase 3 en continu → **checkpoint diff en trois temps** : migrations et calcul validés ; puis question sur la plage de la paie → **deux défauts trouvés** (semaines complètes au lieu du mois, absence à cheval versée deux fois) → correction avant tout commit → renommage `a_cheval` → merge le 03/09 → recette 04–06/09.
- **Décisions A → P** : § 2 (C3.1 → C3.8) et plan v3 ; en résumé : app `absences` ; `TypeAbsence` en base à l'orthographe Notion ; statut sur l'absence, catégorie sur le type ; formule des jours comptés avec périodes datées et double valeur ; fériés dans `socle` ; rétention fail-closed ; accueil commun ; compte sans personne → message ; paragraphe de paie côté serveur ; client n8n factorisé avec import conservé ; règle K sur la personne ; changement d'adresse par jeton signé ; fixtures remontées au conftest racine (imports dans le corps) ; contrat incomplet → 0 et signal ; demi-journées par correction ; absence réservée aux salariées.
- **Écarts au plan pris par Claude Code, acceptés** : `periodes_ouverture` rendue obligatoire (7 lignes de fixture dans `test_chargeur.py`, aucune fonction de test modifiée) — un défaut d'ouverture silencieux serait pire pour de la paie ; `app_name = "comptes"` (aucun `reverse` ni `{% url %}` nu ne visait ses routes, prouvé par grep) ; `clean_personne` en plus de `save_model` (une `ActionImpossible` dans `save_model` donne un 500 dans l'admin) ; aide `_journaliser_suppression` en 3-ter.
- **Recette (04–06/09, personne fictive `TEST Recette`)** : S1 ✓ cinq cas datés en local ; S2a ✓ demande, webhook `absence.demandee` ; S2b ✓ décision, 3 jours, webhook `absence.decidee` ; S2c ✓ déclaration effective, webhook `absence.declaree` ; S2d → **E1** ; S2e → **E3** ; S3a ✓ paie calendaire 01→30/09, 3 jours, Ecole absente, paragraphe sans type ; S3b **différé** (§ 11) ; S4 ✓ correction à 2,5, paie « 2,5 jour(s) » ; S5 ✓ quatre 401 ; S6a **R2** ; S6b ✓ `details` = `{"statut","personne_id","jours_comptes"}` et `{"mois","nb_salariees"}` ; S7 ✓ ; N ✓ (E2). Hors checklist : refus explicite, trois déclarations dont une de 42 jours (R3), 403 du cabinet sur `/mes-absences/`.
- **Écarts** : **E1** — espace personnel fermé à la principale (défaut du plan v3 § 5) → 3-bis. **E2** — suppression d'absence non journalisée → 3-ter. **E3** — annulation non exercée en production, couverte par les tests.
- **Réserves** : **R1** — `SET_NULL` vu en vrai (§ 5.3). **R2** — export de logs partiel (fenêtre 21:00–21:55 UTC du 04/09 non exportée ; fenêtre couverte propre). **R3** — absence de 42 jours non vérifiable, supprimée avant relecture. Une capture d'invitation reçue en Outlook a montré les liens réécrits par Safelinks ; la recette a basculé sur Gmail (§ 15).
- **Reste ouvert** : étalon de paie (§ 11) ; valeur de rétention (C2.6) ; ressaisie manuelle de l'existant Notion ; ~~identifiant n8n du workflow « Absences (réception) » à reporter~~ (reporté en 4b : `eQABsWqayUIR8KuY`) ; envoi réel des invitations et désignation de la principale ; brique 0.

---

## 15. Leçons de déploiement et de recette

### Railway (1a), Railway et n8n (1b), Tests (1b), Proxy, mesure et recette (2) — inchangées (voir v1.3).

### Reprise d'un existant (brique 3-quater)
- **Une page par jour dans la source impose une fusion, et une fusion se prouve contre les jours réels.** Deux règles de fusion fausses (écart ≤ 3 jours, puis « jours de fermeture » appliquée à tous les types) ont inventé des jours d'absence ; la bonne règle : ne souder qu'à travers des jours de fermeture, et seulement pour les congés payés.
- **La fiche de paie est l'étalon, pas la saisie.** 15 écarts Notion ↔ bulletins sur 450 entrées, tous tranchés par le bulletin ; sans lui, on aurait importé une maladie un lundi fermé et un décès sur la mauvaise personne.
- **« Déjà présente » est la meilleure preuve d'un import** : un ré-import intégral qui ne crée rien dit que fichier et base coïncident. L'idempotence a servi trois fois en une journée.
- **Un rapport qui refuse tant qu'il reste une erreur oblige à corriger la source**, pas la base : les trois séries d'erreurs ont été réglées dans le fichier, jamais par une retouche manuelle en base (hors suppressions journalisées).
- **Un étalon inattendu vaut mieux qu'un étalon attendu** : le workflow Notion n'a jamais été retrouvé ; huit bulletins l'ont remplacé et ont tranché une décision de cadrage (C5.1).

### Recette croisée et double vérification (brique 4b)
- **Le planning vécu se sauve à la première occasion.** R4a-1 a tenu deux semaines dans un `localStorage` ; l'exercer avant la 4b a produit une violation réelle, un écart de page réel (E1) et la version 4 — tout ce que le générateur brut ne pouvait pas donner.
- **La seconde revue vaut la première.** La v2 corrigeait le cycle `donnees`/`services` et en réintroduisait un autre (`services ↔ webhooks`). Une revue par version de plan, contre le code, jusqu'à ce qu'elle ne trouve plus rien.
- **Un essai ORM tranche mieux qu'une phrase de plan.** « Forme de l'`Exists` acceptée par Django 5.2 » a coûté trois lignes sur SQLite en mémoire et a sorti le point de la Phase 3.
- **Deux ordres, deux gardes.** Une absence saisie *avant* publication est refusée à la publication (C4.6) ; saisie *après*, elle est signalée (C4.7). La recette a montré un troisième cas : la page rendue *avant* la saisie laisse poser une brique que le serveur refuse — la double vérification (§ 6.4) n'est pas redondante.
- **Un onglet ouvert est un instantané.** Recharger le planning après toute saisie d'absence, jusqu'à ce que la page se rafraîchisse seule (§ 12).
- **Un identifiant de workflow se reporte le jour où on l'a sous les yeux** : `eQABsWqayUIR8KuY` attendait depuis la 3.

### Page, brouillon et référence (brique 4a)
- **La copie autonome sans version serveur était une perte de données en attente.** Le planning réel de septembre a tenu un mois dans le `localStorage` d'un navigateur, jamais écrit sur disque. La 4a est la réponse structurelle ; tant que R4a-1 n'est pas exercé, ce planning n'est sauvegardé nulle part.
- **Un contrat allégé se relit jusqu'au dernier lecteur.** Retirer `initialise` du `state` était juste ; oublier que la page décidait de proposer dessus aurait écrasé chaque version enregistrée au rechargement. Règle : toute clé retirée d'un contrat se cherche par grep chez tous ses lecteurs, et la décision qu'elle portait se relocalise explicitement (C4.3).
- **Une revue par implémentation, pas par plan** : les deux revues de Claude Code contre le code réel ont trouvé treize défauts que le plan ne voyait pas, dont cinq à comportement faux. C'est désormais une étape obligatoire entre v1 et v3.
- **Deux implémentations d'une même règle s'alignent par un jeu de cas commun**, pas par relecture : `cas_verification.json` lu par pytest et par `node:test`. La divergence « férié samedi » aurait été rouge dès le premier tour.
- **Un résultat de référence se fige depuis l'ancien code, à la main, une fois.** Le gabarit d'origine ne tourne pas sous Node ; sans la proposition exportée depuis Chrome par Yohan, le test aurait comparé le moteur à lui-même.
- **Sous gunicorn à deux workers, la contrainte unique est le seul point de sérialisation** (pas de `select_for_update` en SQLite de test) ; `except IntegrityError` hors du `with atomic()`, sinon la relecture lève.
- **`node --test` prend un motif glob**, pas un répertoire ; `json_script` remplace tout échappement manuel ; `finders.find` pour inliner un statique en production manifest.

### Paie, audit et recette (brique 3)
- **Des tests verts ne prouvent qu'un comportement spécifié.** 606 tests étaient verts sur une paie qui facturait deux fois une absence à cheval, parce que le plan ne disait pas sur quelle plage filtrer et que tous les tests de paie tenaient dans un seul mois. La question « sur quelle plage ? » posée au checkpoint diff a fait plus que la suite de tests. Règle : pour tout calcul lié à de l'argent, un test qui traverse une frontière (mois, semaine, régime) est obligatoire.
- **Ne jamais recouper une absence pour relancer le calcul.** Le plafond hebdomadaire s'appliquerait une fois par morceau (27 h à cheval : 5 au lieu de 3). Figer des **dates** au calcul, puis répartir sur les dates, évite le piège par construction.
- **`plage_mois` est l'outil du planning, pas de la paie.** Semaines complètes d'un côté, mois calendaire de l'autre ; deux fonctions, deux noms.
- **Le `SET_NULL` vu en vrai** : supprimer un compte efface l'auteur de tous ses événements d'audit en une seconde. Désactiver, jamais supprimer — et corriger structurellement (§ 12, tête de liste).
- **Une action d'admin de liste ne se trouve pas sur la fiche.** « Créer les comptes » et « Envoyer une invitation » se font depuis la liste, case cochée, menu « Action ».
- **Les liens à usage unique et les scanners de messagerie** : Outlook/Safelinks réécrit les liens et peut les pré-visiter ; recetter en Gmail, et prévenir les salariées dont la messagerie fait de même.
- **L'export Railway plafonne, et un redéploiement coupe la fenêtre** : exporter par déploiement, avant de merger la sous-brique suivante. Et vérifier le **service** exporté — un export du serveur MCP a été fourni par erreur, ce qui a au passage révélé que ce serveur journalise une adresse en clair (§ 12, hors projet).
- **Renommer un champ avant qu'il ait un consommateur** : `a_cheval` → `facture_partiellement` a coûté cinq minutes avant le premier merge ; après la brique 5, c'était un changement de contrat.
- **Une `ActionImpossible` dans `save_model` de l'admin donne un 500** : la garde métier va dans le `ModelForm` (`clean_<champ>`), `save_model` reste le dernier rempart.
- **Amender une migration initiale est légitime tant qu'elle n'a jamais été appliquée en production** ; `0002` qui en dépend doit être mise de côté le temps de régénérer.
- **`pytest.ini` porte déjà `-q`** : un second `-q` masque le résumé.
