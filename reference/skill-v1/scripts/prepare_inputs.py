#!/usr/bin/env python3
"""prepare_inputs.py — transforme les résultats bruts des requêtes Notion en fiche.json et conges.json.

Usage : python3 prepare_inputs.py <dossier_de_travail> [--sans "Jelly,Lea W"] [--praticiens "Yohan,Sacha"]

Entrées (dans le dossier de travail, collées telles quelles depuis les résultats de notion-query-data-sources) :
  - notion_fiche.json  : {"results": [{"Name","Department","Planning","Heures hebdomadaire","Jours de travail"}, ...]}
  - notion_conges.json : {"results": [{"Titre","Type","Concerné absence","debut","fin"}, ...]}
Sorties : fiche.json, conges.json (formats attendus par build_planning.py) + résumé console.

Surcharges optionnelles (l'appel de la skill) : --sans exclut des personnes ; --praticiens restreint les praticiens.
Une personne ne peut être AJOUTÉE qu'en cochant « Planning » dans ☎️ Fiche personnel : la fiche fait foi.
"""
import json, sys, re, unicodedata, argparse
from pathlib import Path

def normaliser(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-zA-Z ]", " ", s).casefold().split())

ROLES = {"assistante": "assistante", "secretariat": "secretaire", "praticien": "praticien"}

def lire(chemin):
    if not Path(chemin).exists():
        sys.exit(f"❌ {chemin} manquant")
    d = json.load(open(chemin, encoding="utf-8"))
    if isinstance(d, dict) and "results" in d:
        return d["results"]
    if isinstance(d, list):
        return d
    sys.exit(f"❌ {chemin} : forme inattendue (attendu {{'results': [...]}})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier"); ap.add_argument("--sans", default=""); ap.add_argument("--praticiens", default="")
    a = ap.parse_args()
    d = Path(a.dossier)
    sans = [normaliser(x) for x in a.sans.split(",") if x.strip()]
    seuls = [normaliser(x) for x in a.praticiens.split(",") if x.strip()]

    fiche = []
    for r in lire(d / "notion_fiche.json"):
        role = ROLES.get(normaliser(r.get("Department") or ""))
        if role is None:
            print(f"ℹ️  ignoré (département inconnu) : {r.get('Name')!r} / {r.get('Department')!r}"); continue
        tokens = (r.get("Name") or "").strip().split()
        if len(tokens) < 2:
            print(f"ℹ️  ignoré (nom incomplet) : {r.get('Name')!r}"); continue
        nom, prenom = " ".join(tokens[:-1]), tokens[-1]
        jours = r.get("Jours de travail")
        if isinstance(jours, str):
            try:
                jours = json.loads(jours)
            except json.JSONDecodeError:
                jours = [x.strip() for x in jours.split(",") if x.strip()]
        planning = r.get("Planning") in (True, "__YES__", "true", "True", 1, "1")
        cles = {normaliser(prenom), normaliser(nom), normaliser(prenom + " " + nom[0]), normaliser(prenom + " " + nom), normaliser(nom + " " + prenom)}
        if planning and any(s in cles for s in sans):
            planning = False; print(f"  surcharge : {prenom} {nom} exclu(e) ce mois (--sans)")
        if planning and role == "praticien" and seuls and not any(s in cles for s in seuls):
            planning = False; print(f"  surcharge : praticien {prenom} {nom} hors liste (--praticiens)")
        fiche.append({"nom": nom, "prenom": prenom, "role": role, "heures": r.get("Heures hebdomadaire"),
                      "fixes": jours or [], "planning": planning})
    json.dump(fiche, open(d / "fiche.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    conges = []
    for r in lire(d / "notion_conges.json"):
        if not r.get("debut"):
            continue
        conges.append({"titre": r.get("Titre"), "type": r.get("Type"), "concerne": r.get("Concerné absence"),
                       "debut": r["debut"][:10], "fin": (r.get("fin") or "")[:10] or None})
    json.dump(conges, open(d / "conges.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    p = [f for f in fiche if f["planning"]]
    print(f"fiche.json : {len(p)} personnes planifiées sur {len(fiche)} — "
          f"{sum(f['role'] == 'praticien' for f in p)} praticiens, {sum(f['role'] == 'assistante' for f in p)} assistantes, "
          f"{sum(f['role'] == 'secretaire' for f in p)} secrétaires")
    print(f"conges.json : {len(conges)} entrées d'absence sur la période")

if __name__ == "__main__":
    main()
