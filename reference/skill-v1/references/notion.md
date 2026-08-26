# Notion — sources de la skill planning-assistante

Deux bases sont lues, jamais modifiées. Les requêtes ci-dessous sont testées ; les recopier telles quelles
(seules les dates changent). Outil : `Notion:notion-query-data-sources`, mode `sql` — charger avec
`tool_search("Notion query data sources SQL")` si l'outil n'est pas encore visible.

## 1. ☎️ Fiche personnel — qui planifier, contrats, jours fixes

- Data source : `collection://15a12b4c-433a-81b9-b4d3-000b4c679be5`
- Colonnes utilisées, et **seulement** celles-là (la base contient aussi n° de sécurité sociale, date de naissance,
  téléphone, e-mail : ne jamais faire `SELECT *`) :
  - `Name` — « NOM Prénom » (le prénom est le dernier mot, le nom tout ce qui précède, ex. « DA VEIGA MONTEIRO Dilsa »)
  - `Department` — `Assistante` / `Secrétariat` / `Praticien`
  - `Planning` — case à cocher, **source de vérité** de qui est planifié (`"__YES__"` / `"__NO__"` dans le résultat)
  - `Heures hebdomadaire` — 39 / 35 / 27 / null
  - `Jours de travail` — chaîne JSON `"[\"Mardi\",\"Jeudi\"]"` ou null (jours fixes des secrétaires ; indicatif pour les praticiens)

```sql
SELECT "Name", "Department", "Planning", "Heures hebdomadaire", "Jours de travail"
FROM "collection://15a12b4c-433a-81b9-b4d3-000b4c679be5"
ORDER BY "Department", "Name"
```

Résultat : `{"results": [ {...}, ... ]}` → enregistrer tel quel dans `notion_fiche.json`.
Le filtre `WHERE "Planning" = TRUE` ne fonctionne pas dans ce dialecte : filtrer côté script (prepare_inputs.py le fait).

Règles portées par la fiche :
- Praticien coché sans agenda Doctolib apparié → le générateur s'arrête (sauf s'il a des jours fixes : planning fixe).
- Secrétaire à jours fixes sans heures (ex. Cécile) → ses jours fixes *sont* son contrat, le reste est en heures sup.
- Assistante sans heures → 39 h supposé, bannière dans la page.

## 2. 📅 Agenda cabinet — absences et cours de la période

- Data source : `collection://15a12b4c-433a-8192-a1d4-000b35638438`
- Colonnes : `Titre`, `Type`, `Concerné absence` (prénom de la salariée, comme dans le planning), `Date` (plage possible)
- Types d'absence bloquants (une journée comptée comme placée) : `Congé payé`, `Maladie`, `Congé sans solde`,
  `Congé enfant malade`, `Congé grossesse`, `Ecole`, `Congé évenement familial`, `Décés`.
  Types informatifs (simple note dans la case) : `Heures sans solde`, `Départ plus tôt`, `Départ plus tard`, `Retard`, `Autre`.
- Cours des étudiantes : entrées de Type `Ecole` dont le **titre** contient l'étiquette de la personne (ex. « Lea W école »),
  généralement sans `Concerné absence` — le générateur les rattache via `regles.json › etudiantes`.

Remplacer `DEBUT` et `FIN` par les bornes de la plage (semaines complètes, voir SKILL.md) :

```sql
SELECT "Titre", "Type", "Concerné absence", "date:Date:start" AS debut, "date:Date:end" AS fin
FROM "collection://15a12b4c-433a-8192-a1d4-000b35638438"
WHERE "Type" NOT IN ('Présence','Tâche','Evenement')
  AND date(substr("date:Date:start",1,10)) <= date('FIN')
  AND date(substr(COALESCE("date:Date:end", "date:Date:start"),1,10)) >= date('DEBUT')
ORDER BY debut
```

Résultat : `{"results": [ {"Titre","Type","Concerné absence","debut","fin"}, ... ]}` → `notion_conges.json`.

## 3. Correspondances de noms (faites par le générateur, rien à saisir)

- Doctolib ↔ fiche : nom complet normalisé (casse, accents et suffixes « (Villecresnes) » ignorés) ; repli prénom + 4 premières
  lettres du nom pour les orthographes divergentes (« Jaffrennou » / « JAFFRENOU »), signalé « approché » dans le rapport.
- Fiche ↔ Agenda cabinet : prénom ; deux prénoms identiques → initiale du nom ajoutée (« Lea D », « Lea W »).
- Les praticiens Doctolib absents de la fiche (Krameisen…) ne sont pas planifiés : la fiche fait foi.
