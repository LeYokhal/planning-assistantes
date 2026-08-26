---
name: planning-assistante
description: >-
  Génère le planning mensuel des assistantes et secrétaires du cabinet Espace K Dentaire
  (Villecresnes) sous forme d'une page HTML autonome, à partir des présences réelles des
  praticiens dans Doctolib (MCP consulter_jours_travail) et de la fiche personnel Notion.
  Use this skill whenever the user invokes /planning-assistante, or asks in French for the
  "planning assistantes", "planning des assistantes", "planning du mois", "génère / prépare / refais le planning", "répartition des assistantes",
  "qui assiste qui", or wants to match assistantes to praticiens for a given month —
  even if they only name a month ("octobre", "planning de novembre 2026") or add
  overrides like "sans Jelly" or "praticiens : Yohan, Sacha". Do not use it for a
  single practitioner's Doctolib week (use consulter_jours_travail directly) nor for
  payslips (fdp-cabinet-k).
---

# Planning assistantes — Espace K Dentaire

## What this skill does

Produces **one self-contained HTML file** `planning-assistantes_AAAA-MM.html` that the practice's
assistante opens in Chrome on the office PC. The page:
- reproduces the month as a calendar of **full weeks (Monday→Sunday)**, showing only weekdays where
  someone is present (typically Tuesday→Saturday; Monday appears only if a practitioner opens);
- lists, per day, the practitioners present according to Doctolib (`presence = true`, i.e. agenda
  open or ≥ 5 h of live appointments) — Laura (orthodontist) on her own full-width line, then a
  Secrétariat line, and Sureffectif / Administratif / Absent lines only when they contain something;
- pre-fills a **proposal** computed in the page (binômes, exclusives, coverage, Amandine's
  administrative slot, leftovers in sureffectif) that the assistante then adjusts by drag & drop;
- tracks per person and per week the days to place (contract bricks: J = full day 9h–19h30,
  C = short day 9h–16h30), absences (CP / MAL / SS, counted as placed days), public holidays,
  overtime hours, comments per day, filters, printing, save/export/import.

The user (Yohan) runs this skill; the assistante only manipulates the resulting file. Nothing here
writes to Notion or Doctolib. The Notion export of the finished planning is a separate, future step.

## Inputs and their sources

| Input | Source | How |
|---|---|---|
| Month | the request (`/planning-assistante octobre 2026`) | ask if missing or ambiguous — one question only |
| Who to plan, contracts, fixed days | Notion ☎️ Fiche personnel, checkbox **Planning** | SQL query → `notion_fiche.json` (see `references/notion.md`) |
| Absences and school days of the period | Notion 📅 Agenda cabinet | SQL query → `notion_conges.json` |
| Practitioners' presence | Doctolib via `MCP Doctolib:consulter_jours_travail`, mode `tous` | 2 calls (31-day cap) → `s7_01_*.json`, `s7_02_*.json` |
| Rules: contract templates, binômes, exclusives, admin slot, students, colours, hours per brick | `regles.json` in this skill | read by the generator |
| Page template | `assets/gabarit.html` | read by the generator |

Optional overrides in the request: `sans X, Y` (exclude people this month), `praticiens : A, B`
(restrict practitioners). Overrides can only **remove**; to add someone, the Planning checkbox in
Notion must be ticked — the fiche is the single source of truth.

## Procedure

Work in a fresh directory, e.g. `WORK=/home/claude/planning-AAAA-MM`. The skill's own files live
under `/mnt/skills/user/planning-assistante/` (read-only): call the scripts from there.

### 1. Month and range

```bash
python3 /mnt/skills/user/planning-assistante/scripts/build_planning.py --plage AAAA-MM
```
Prints `debut`, `fin` (full weeks) and `appels`: the date windows for the Doctolib calls, each ≤ 31
days (the server caps `praticien="tous"` at 31 days; a month of full weeks needs two calls).

### 2. Notion — fiche and absences (read-only)

Run the two SQL queries from `references/notion.md` with `Notion:notion-query-data-sources`
(load it with `tool_search` if needed). Replace DEBUT/FIN in the absences query by the range.
Save each raw result **verbatim** with `create_file`: `$WORK/notion_fiche.json` and
`$WORK/notion_conges.json` (the tool returns `{"results": [...]}` — keep that shape). Never
`SELECT *` on the fiche: it holds social-security numbers and birth dates that must not enter context.

```bash
python3 /mnt/skills/user/planning-assistante/scripts/prepare_inputs.py $WORK [--sans "Jelly,Lea W"] [--praticiens "Yohan,Sacha"]
```
Produces `fiche.json` and `conges.json` and prints who is planned. Stop here if the counts look
wrong (e.g. 0 practitioners) and tell the user what to check in Notion.

### 3. Doctolib — presence (read-only)

Load the tool once with `tool_search("consulter_jours_travail")`, then for each window in `appels`:

`MCP Doctolib:consulter_jours_travail` with `date`, `date_fin`, `praticien = "tous"` (leave the
thresholds at their defaults: 4 h short day, 5 h presence).

The first result is large (~250 KB) and the interface stores it on disk: the tool result says
`stored at /mnt/user-data/tool_results/<file>.json`. Copy it, do not retype it:
```bash
cp /mnt/user-data/tool_results/<file>.json $WORK/s7_01_<debut>_<fin>.json
```
A short result (a few days) comes back inline: write it verbatim with `create_file` to
`$WORK/s7_02_<debut>_<fin>.json`. The generator accepts both the raw payload and the
`[{"text": "..."}]` wrapper, and re-counts every envelope — a truncated copy is refused.

### 4. Generate

```bash
python3 /mnt/skills/user/planning-assistante/scripts/build_planning.py AAAA-MM $WORK
```
Read the console report line by line. It shows the Doctolib ↔ fiche matching (`exact` /
`approché` / `planning fixe`), every rule applied (binômes, exclusives, admin slot, students and
their school days), the range and the counts. The script **stops** (❌) on: a failed or altered
Doctolib call, a ticked practitioner with no matching agenda and no fixed days, a person with
hours that have no template in `regles.json`. Fix the cause (Notion checkbox, hours, or
`regles.json`) and rerun; never bypass the guard. Relay every ⚠️ / ℹ️ line to the user.

### 5. Deliver

```bash
cp $WORK/planning-assistantes_AAAA-MM.html /mnt/user-data/outputs/
```
Then `present_files` with that path — this is the only deliverable. Do not present `data.json`
or the intermediate files unless asked.

## Report to the user (in French, compact)

After presenting the file, give:

1. **Périmètre** : mois, plage (du … au …), nombre de praticiens / assistantes / secrétaires planifiés,
   surcharges appliquées.
2. **Doctolib** : les deux enveloppes (jours, ouverts, présents) et tout appariement « approché ».
3. **Absences et cours** repris de Notion (par personne), et les entrées non rattachées (ignorées).
4. **Alertes** du générateur (⚠️ heures supposées, ℹ️ règles ignorées faute de personne planifiée).
5. **Rappel d'usage** en deux phrases : ouvrir dans Chrome, la proposition est déjà posée ;
   **Enregistrer** retélécharge le fichier avec le planning dedans ; un brouillon de ce fichier est
   aussi gardé dans le navigateur (bandeau « Brouillon repris » avec bouton « Repartir du fichier »).

No congratulations, no restating the page's features: the user built the page.

## Business rules (for understanding — they are implemented, not to be re-decided)

- **Strict**: weekly hours (bricks per contract: 39 h = 4 J, 35 h = 3 J + 1 C, 27 h = 2 J + 1 C;
  a fixed-days secretary without hours = her fixed days), one brick per person per day, absences and
  closed days block placement, one assistante per practitioner (Laura: exactly her two, Emilie and
  Lea W, never anyone else), exclusives never go elsewhere.
- **Relative** (the proposal): binômes Lea D↔Yohan, Maeva↔Justine, Dilsa↔Noemie, Charlotte↔Sabrina;
  coverage by continuity within the week then fairness over the month; Amandine keeps her short day
  as an administrative slot unless that would leave a post uncovered; leftovers go to sureffectif
  on the busiest days, Tuesday→Friday.
- **Absences** (CP, MAL, SS, plus Notion's other blocking types) and **public holidays Monday→Friday**
  occupy a contract brick (counted as a placed day); a Saturday/Sunday holiday does not.
- **Students** (Lea W): rhythm without school = 3 J + 1 C; each school day consumes the week's
  short day (a second one in the same week consumes a full day). School days are pre-filled from
  Notion « Ecole » entries and adjustable in the page (− N + on her tile).
- **Presence** signal is `presence` from consulter_jours_travail (agenda open OR ≥ 5 h of live
  appointments), never `creneaux_effectifs` alone.

## Maintenance

- **Binômes, exclusives, admin slot, students, colours, hours per brick, contract templates** live in
  `regles.json` (names = `Name` of the fiche, "NOM Prénom"). To change them, produce the edited
  `regles.json` for the user and ask them to re-upload the skill with it; for a one-off month,
  a `regles.json` placed in `$WORK` overrides the skill's copy.
- **Who is planned, contracts, fixed days** are edited by the user in Notion (checkbox Planning,
  Heures hebdomadaire, Jours de travail) — never by this skill.
- **The page** is `assets/gabarit.html` (vanilla HTML/JS, no build step). Any change must keep the
  two markers `__PLANNING_DATA__` and `__PLANNING_STATE__` and the `<script id="planning-state">`
  block, which the page rewrites when the user clicks Enregistrer.
- Future step (backlog): export the finished planning back to 📅 Agenda cabinet from the page's
  « Exporter JSON » file — with a human checkpoint before any write.

## Pitfalls seen during development

- A stale draft in the browser can hide a fresh proposal: the page keys drafts on the file's
  generation timestamp, so a regenerated file always starts from its own proposal — but if the user
  says "the proposal is incomplete", ask whether the orange banner « Brouillon repris » is showing.
- `WHERE "Planning" = TRUE` returns nothing in Notion's SQL dialect; filter in the script.
- Doctolib agenda names differ from the fiche (case, accents, « (Villecresnes) », one-letter
  spelling differences such as Jaffrennou/JAFFRENOU): the generator normalises and reports
  approximate matches — check them, do not "fix" names in Notion for that.
- Never retype a Doctolib result by hand; copy the stored file. The envelope re-count catches
  truncation, not transcription errors elsewhere.
