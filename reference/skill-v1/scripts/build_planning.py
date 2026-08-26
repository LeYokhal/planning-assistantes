#!/usr/bin/env python3
"""build_planning.py — assemble les données du planning assistantes.

Usage : python3 build_planning.py <AAAA-MM> <dossier_de_travail>

Entrées (fichiers JSON dans le dossier de travail, produits par prepare_inputs.py et les appels MCP) :
  - s7_*.json        : résultats BRUTS de consulter_jours_travail (mode "tous"),
                       tels que stockés par l'interface (wrapper [{"text": "..."}]
                       ou payload direct {"succes":..., "donnees":...})
  - fiche.json       : lignes de ☎️ Fiche personnel (colonnes utiles seulement)
  - conges.json      : entrées de 📅 Agenda cabinet de la période (Type ≠ Présence)
Pièces de la skill (prises dans le dossier de la skill, ou dans le dossier de travail si une copie s'y trouve) :
  - regles.json      : gabarits par contrat, binômes, exclusifs, administratif, étudiantes, couleurs, heures par brique
  - assets/gabarit.html : page HTML avec les marqueurs __PLANNING_DATA__ / __PLANNING_STATE__

Sortie : planning-assistantes_<AAAA-MM>.html + data.json (debug) + rapport console.
Gardes : arrêt si un appel S7 a échoué, si son enveloppe ne correspond pas au détail, si un praticien coché
n'a pas d'agenda apparié, ou si une salariée a des heures sans gabarit. Aucune donnée patient ne transite.
"""
import json, re, sys, unicodedata, datetime, glob, collections
from pathlib import Path
SKILL_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- utilitaires
def normaliser(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\(.*?\)", " ", s)          # suffixes « (Villecresnes) »
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    return " ".join(s.casefold().split())

def paques(annee: int) -> datetime.date:
    a = annee % 19; b = annee // 100; c = annee % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) / 451
    mois = (h + l - 7 * int(m) + 114) // 31
    jour = ((h + l - 7 * int(m) + 114) % 31) + 1
    return datetime.date(annee, mois, jour)

def feries_fr(annee: int) -> dict:
    p = paques(annee)
    d = lambda m, j: datetime.date(annee, m, j)
    return {
        d(1, 1): "Jour de l'an", p + datetime.timedelta(1): "Lundi de Pâques",
        d(5, 1): "Fête du Travail", d(5, 8): "Victoire 1945",
        p + datetime.timedelta(39): "Ascension", p + datetime.timedelta(50): "Lundi de Pentecôte",
        d(7, 14): "Fête nationale", d(8, 15): "Assomption", d(11, 1): "Toussaint",
        d(11, 11): "Armistice", d(12, 25): "Noël",
    }

JOURS_FR = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
ABR = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]

# Types de congé qui retirent une journée (bloquants) / qui n'informent que (info)
TYPES_BLOQUANTS = {"Congé payé", "Congé sans solde", "Maladie", "Congé enfant malade",
                   "Congé grossesse", "Ecole", "Congé évenement familial", "Décés"}
TYPES_INFO = {"Heures sans solde", "Départ plus tôt", "Départ plus tard", "Retard", "Autre"}

COULEURS = {  # nom de couleur Notion -> (fond, encre)
    "gray": ("#E6E9EC", "#4F5B63"), "brown": ("#EAD9CB", "#6E4A2E"),
    "orange": ("#FBE1C2", "#9E5410"), "yellow": ("#F6ECAE", "#7A5F00"),
    "green": ("#D2EBD5", "#256B31"), "blue": ("#D3E4F7", "#1F529A"),
    "purple": ("#E2D8F5", "#5E3BA6"), "pink": ("#F8D6E4", "#A32F60"),
    "red": ("#F6D0CD", "#A8342E"), "default": ("#E3E3E3", "#3A3A3A"),
}

def ident(f) -> str:
    """identifiant stable et sans espace : prénom + 3 lettres du nom (lettres seulement)."""
    return re.sub(r"[^a-z]", "", normaliser(f["prenom"])) + "_" + re.sub(r"[^a-z]", "", normaliser(f["nom"]))[:3]

# ---------------------------------------------------------------- chargement
def charger_s7(chemin):
    brut = json.load(open(chemin, encoding="utf-8"))
    if isinstance(brut, list):                       # wrapper interface [{"text": "..."}]
        brut = json.loads(brut[0]["text"])
    if isinstance(brut, dict) and "text" in brut and "donnees" not in brut:
        brut = json.loads(brut["text"])
    if not brut.get("succes"):
        sys.exit(f"❌ {chemin} : appel S7 en échec : {brut.get('message')}")
    # garde : l'enveloppe (message) doit correspondre au détail recompté
    m = re.search(r"(\d+) ouvert\(s\), (\d+) atypique\(s\), (\d+) fermé\(s\), (\d+) non planifié\(s\), (\d+) présent\(s\)", brut["message"])
    if m:
        c = collections.Counter(); pres = 0
        for j in brut["donnees"]["jours"]:
            for pr in j["praticiens"]:
                c[pr["verdict"]] += 1; pres += bool(pr["presence"])
        attendu = tuple(int(x) for x in m.groups())
        obtenu = (c["ouvert"], c["ouvert (atypique)"], c["fermé"], c["non planifié"], pres)
        if attendu != obtenu:
            sys.exit(f"❌ {chemin} : enveloppe {attendu} ≠ recompte {obtenu} — fichier tronqué ou altéré, relancer l'appel")
        print(f"  S7 ok  {Path(chemin).name} : {brut['message']}")
    return brut

def main(mois: str, dossier: str = "."):
    annee, num = map(int, mois.split("-"))
    fiche = json.load(open(f"{dossier}/fiche.json", encoding="utf-8"))
    chemin_regles = Path(dossier, "regles.json") if Path(dossier, "regles.json").exists() else SKILL_ROOT / "regles.json"
    chemin_gabarit = Path(dossier, "gabarit.html") if Path(dossier, "gabarit.html").exists() else SKILL_ROOT / "assets" / "gabarit.html"
    print(f"Règles : {chemin_regles} · gabarit : {chemin_gabarit}")
    regles = json.load(open(chemin_regles, encoding="utf-8"))
    gabarits = {int(k): v for k, v in regles["gabarits"].items() if not k.startswith("_")}
    couleur_de = {normaliser(k): v for k, v in regles.get("couleurs", {}).items()}
    def couleur(f):
        return COULEURS.get(couleur_de.get(normaliser(f["nom"] + " " + f["prenom"]), "default"), COULEURS["default"])
    conges_brut = json.load(open(f"{dossier}/conges.json", encoding="utf-8"))
    appels = [charger_s7(p) for p in sorted(glob.glob(f"{dossier}/s7_*.json"))]
    assert appels, "aucun fichier s7_*.json"

    # --- 1. plage du planning : semaines complètes (lundi -> dimanche) couvrant le mois
    premier = datetime.date(annee, num, 1)
    dernier = (datetime.date(annee + (num == 12), (num % 12) + 1, 1) - datetime.timedelta(1))
    debut = premier - datetime.timedelta(premier.weekday())
    fin = dernier + datetime.timedelta(6 - dernier.weekday())

    # --- 2. fusion des appels S7 : date -> nom agenda -> ligne
    par_jour = {}
    enveloppes = []
    for ap in appels:
        d = ap["donnees"]
        enveloppes.append(ap["message"])
        for j in d["jours"]:
            par_jour.setdefault(j["date"], {})
            for pr in j["praticiens"]:
                par_jour[j["date"]][pr["praticien"].strip()] = pr
    jours_couverts = set(par_jour)
    manquants = [ (debut + datetime.timedelta(i)).isoformat() for i in range((fin - debut).days + 1)
                  if (debut + datetime.timedelta(i)).isoformat() not in jours_couverts ]
    manquants = [m for m in manquants if datetime.date.fromisoformat(m).weekday() != 6]
    if manquants:
        print("⚠️  jours ouvrés sans données S7 :", manquants)

    # --- 3. fiche : praticiens planifiés + appariement Doctolib
    agendas = sorted({nom for jj in par_jour.values() for nom in jj})
    praticiens, salaries, rapport = [], [], []
    planifies = [f for f in fiche if f.get("planning")]
    prenoms = collections.Counter(f["prenom"] for f in planifies)
    def label(f):
        if prenoms[f["prenom"]] > 1:
            return f"{f['prenom']} {f['nom'][0]}"
        return f["prenom"]
    for f in planifies:
        if f["role"] == "praticien":
            cible = normaliser(f["nom"] + " " + f["prenom"])
            exact = [a for a in agendas if normaliser(a) == cible]
            if exact:
                agenda, mode = exact[0], "exact"
            else:  # repli : même prénom + même début de nom (≥4 lettres)
                pren = normaliser(f["prenom"]); pref = normaliser(f["nom"])[:4]
                cand = [a for a in agendas if pren in normaliser(a).split() and
                        any(t.startswith(pref) for t in normaliser(a).split())]
                if len(cand) == 1:
                    agenda, mode = cand[0], "approché"
                elif f.get("fixes"):
                    agenda, mode = None, "planning fixe (aucun agenda Doctolib)"
                else:
                    sys.exit(f"❌ {f['nom']} {f['prenom']} : praticien coché sans agenda Doctolib apparié "
                             f"(candidats : {cand}) et sans jours fixes.")
            rapport.append(f"  praticien {f['nom']} {f['prenom']:<10} -> {agenda!r} ({mode})")
            praticiens.append({"id": ident(f),
                               "label": label(f), "nom": f"{f['nom']} {f['prenom']}",
                               "agenda": agenda, "couleur": couleur(f),
                               "fixes": [JOURS_FR[x.lower()] for x in f.get("fixes", [])],
                               "attendues": 1, "exclusif": False, "binomes": [], "a_part": False, "etiquette": None})
        else:
            heures = f.get("heures")
            suppose, fixes_absolus = False, False
            hb = regles.get("heures_par_brique", {"J": 9.75, "C": 6.75})
            if heures is None and f["role"] == "secretaire" and f.get("fixes"):
                # règle absolue : ses jours fixes font son contrat (ex. Cécile : mardi, mercredi, jeudi), le reste est supplémentaire
                heures, fixes_absolus = round(len(f["fixes"]) * hb["J"], 2), True
                rapport.append(f"  règle   {f['prenom']:<10} {len(f['fixes'])} jours fixes ({', '.join(f['fixes'])}) = {heures} h, journées en plus = heures sup")
            elif heures is None:
                heures, suppose = 39, True
                rapport.append(f"  ⚠️ {f['nom']} {f['prenom']} : heures non renseignées, 39 h SUPPOSÉ")
            gabarit = ["J"] * len(f["fixes"]) if fixes_absolus else gabarits.get(int(heures))
            if gabarit is None:
                sys.exit(f"❌ {f['nom']} {f['prenom']} : {heures} h sans gabarit dans regles.json (connus : {sorted(gabarits)}).")
            salaries.append({"id": ident(f),
                             "label": label(f), "nom": f"{f['nom']} {f['prenom']}", "role": f["role"],
                             "heures": heures, "heures_supposees": suppose, "heures_fixes": fixes_absolus, "gabarit": gabarit,
                             "fixes": [JOURS_FR[x.lower()] for x in f.get("fixes", [])],
                             "couleur": couleur(f), "binomes": [], "exclusif": False, "admin": None})
    print("Appariement Doctolib :"); print("\n".join(rapport))

    # --- 3b. règles : binômes, exclusifs, créneaux administratifs (noms = fiche, normalisés)
    sal_par_nom = {normaliser(s["nom"]): s for s in salaries}
    prat_par_nom = {normaliser(p["nom"]): p for p in praticiens}
    def trouve(table, nom, quoi):
        obj = table.get(normaliser(nom))
        if obj is None:
            print(f"ℹ️  règle ignorée : {quoi} {nom!r} absent des personnes planifiées")
        return obj
    for b in regles.get("binomes", []):
        s = trouve(sal_par_nom, b["assistante"], "assistante"); p = trouve(prat_par_nom, b["praticien"], "praticien")
        if s and p:
            s["binomes"].append(p["id"]); p["binomes"].append(s["id"])
            if b.get("exclusif"): s["exclusif"] = True
    for nom in regles.get("praticiens_exclusifs", {}).get("liste", []):
        p = trouve(prat_par_nom, nom, "praticien exclusif")
        if p:
            p["exclusif"] = True; p["attendues"] = max(1, len(p["binomes"]))
    for ap in regles.get("praticiens_a_part", {}).get("liste", []):
        p = trouve(prat_par_nom, ap["nom"] if isinstance(ap, dict) else ap, "praticien à part")
        if p:
            p["a_part"] = True; p["etiquette"] = ap.get("etiquette") if isinstance(ap, dict) else None
    praticiens.sort(key=lambda p: p.get("a_part", False))   # les praticiens à part passent en fin de liste
    etudiantes = {}
    for e in regles.get("etudiantes", {}).get("liste", []):
        s = trouve(sal_par_nom, e["nom"], "étudiante")
        if s:
            s["etudiante"] = True; s["gabarit"] = e.get("gabarit_sans_cours", ["J", "J", "J", "C"])
            etudiantes[s["id"]] = (s, e.get("mot_cle_notion", "école"))
            print(f"  règle   {s['label']:<10} étudiante : {''.join(s['gabarit'])} sans cours, un cours consomme la courte")
    for c in regles.get("creneau_administratif", []):
        s = trouve(sal_par_nom, c["salariee"], "salariée")
        if s: s["admin"] = c.get("brique", "C")
    for s in salaries:
        if s["binomes"] or s["admin"]:
            print(f"  règle   {s['label']:<10} binômes={[prat_par_nom and next(p['label'] for p in praticiens if p['id']==x) for x in s['binomes']]}"
                  f"{' EXCLUSIVE' if s['exclusif'] else ''}{' admin='+s['admin'] if s['admin'] else ''}")
    for p in praticiens:
        if p["exclusif"]: print(f"  règle   {p['label']:<10} exclusif, {p['attendues']} assistante(s) attendue(s)")

    # --- 4. présence compacte, praticiens planifiés seulement, lignes non triviales
    jours = {}
    stats = collections.Counter()
    for iso in sorted(par_jour):
        d = datetime.date.fromisoformat(iso)
        if not (debut <= d <= fin):
            continue
        for p in praticiens:
            if p["agenda"] is None:
                continue
            ligne = par_jour[iso].get(p["agenda"])
            if ligne is None:
                continue
            triviale = (not ligne["presence"] and ligne["verdict"] == "non planifié" and ligne["nb_rdv"] == 0)
            if triviale:
                continue
            cr = [[c["debut"], c["fin"]] for c in ligne["creneaux"]]
            jours.setdefault(iso, {})[p["id"]] = {
                "pr": bool(ligne["presence"]), "v": ligne["verdict"], "c": cr,
                "fin": cr[-1][1] if cr else None, "n": ligne["nb_rdv"],
                "jc": bool(ligne["journee_courte"]), "min": ligne["duree_rdv_vivants_minutes"],
            }
            stats["présents" if ligne["presence"] else "non présents visibles"] += 1

    # --- 5. congés attribués aux salariées planifiées
    by_label = {s["label"]: s["id"] for s in salaries}
    by_prenom = {normaliser(s["nom"].split()[-1]): s["id"] for s in salaries}  # prénom = dernier token
    conges, orphelins = [], []
    for c in conges_brut:
        qui = c.get("concerne")
        sid = by_label.get(qui) or by_prenom.get(normaliser(qui or ""))
        d0 = c["debut"][:10]; d1 = (c.get("fin") or c["debut"])[:10]
        if sid is None:
            orphelins.append(f"{c.get('titre')} ({c['type']}, {d0}{'→'+d1 if d1!=d0 else ''}, concerné={qui!r})")
            continue
        typ = c["type"]
        bloque = typ in TYPES_BLOQUANTS
        if typ not in TYPES_BLOQUANTS and typ not in TYPES_INFO:
            print(f"⚠️  type de congé inconnu {typ!r} traité comme information")
        cur = datetime.date.fromisoformat(d0)
        while cur <= datetime.date.fromisoformat(d1):
            if debut <= cur <= fin:
                conges.append({"s": sid, "date": cur.isoformat(), "type": typ, "bloque": bloque})
            cur += datetime.timedelta(1)
    # jours de cours des étudiantes : entrées Notion « Ecole » dont le titre contient leur étiquette (ex. « Lea W école »)
    cours = {}
    for c in conges_brut:
        if c["type"] != "Ecole":
            continue
        for sid, (s, mot) in etudiantes.items():
            titre = normaliser(c.get("titre") or "")
            if normaliser(s["label"]) in titre or (normaliser(mot) in titre and normaliser(s["label"].split()[0]) in titre):
                d0 = c["debut"][:10]; d1 = (c.get("fin") or c["debut"])[:10]
                cur = datetime.date.fromisoformat(d0)
                while cur <= datetime.date.fromisoformat(d1):
                    if debut <= cur <= fin: cours.setdefault(sid, []).append(cur.isoformat())
                    cur += datetime.timedelta(1)
                orphelins = [o for o in orphelins if c.get("titre") not in o]
    for sid, dates in cours.items():
        print(f"  cours   {next(s['label'] for s in salaries if s['id']==sid):<10} {len(dates)} jour(s) : {', '.join(sorted(dates))}")
    if orphelins:
        print("ℹ️  entrées de congé non rattachées à une salariée planifiée (ignorées) :")
        for o in orphelins: print("   -", o)

    # --- 6. fériés de la plage
    feries = {}
    for an in {debut.year, fin.year}:
        for d, nom in feries_fr(an).items():
            if debut <= d <= fin:
                feries[d.isoformat()] = nom

    data = {
        "meta": {"mois": mois, "libelle": f"{MOIS_FR[num-1].capitalize()} {annee}",
                 "debut": debut.isoformat(), "fin": fin.isoformat(),
                 "genere": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                 "source": "Doctolib · consulter_jours_travail (mode tous)",
                 "heures": {k: v for k, v in regles.get("heures_par_brique", {"J": 9.75, "C": 6.75}).items() if not k.startswith("_")},
                 "seuils": {"courte_h": appels[0]["donnees"]["seuil_heures"],
                            "presence_h": appels[0]["donnees"]["seuil_presence"]},
                 "enveloppes": enveloppes},
        "praticiens": praticiens, "salaries": salaries,
        "jours": jours, "conges": conges, "feries": feries, "cours": cours,
    }
    json.dump(data, open(f"{dossier}/data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Plage {debut} → {fin} · {len(praticiens)} praticiens, {len(salaries)} salariées, "
          f"{stats['présents']} présences praticien-jour, {len(conges)} jours de congé, {len(feries)} fériés")

    gabarit = open(chemin_gabarit, encoding="utf-8").read()
    etat = {"initialise": False, "affectations": {}, "modifie": None}
    html = (gabarit.replace("__PLANNING_DATA__", json.dumps(data, ensure_ascii=False))
                   .replace("__PLANNING_STATE__", json.dumps(etat, ensure_ascii=False)))
    sortie = f"{dossier}/planning-assistantes_{mois}.html"
    open(sortie, "w", encoding="utf-8").write(html)
    print("→", sortie, f"({len(html)//1024} Ko)")

def plage(mois: str):
    """Affiche la plage du planning (semaines complètes) et les fenêtres d'appel S7 (≤ 31 jours chacune)."""
    annee, num = map(int, mois.split("-"))
    premier = datetime.date(annee, num, 1)
    dernier = datetime.date(annee + (num == 12), (num % 12) + 1, 1) - datetime.timedelta(1)
    debut = premier - datetime.timedelta(premier.weekday())
    fin = dernier + datetime.timedelta(6 - dernier.weekday())
    appels, cur = [], debut
    while cur <= fin:
        stop = min(cur + datetime.timedelta(30), fin)
        appels.append([cur.isoformat(), stop.isoformat()]); cur = stop + datetime.timedelta(1)
    print(json.dumps({"mois": mois, "debut": debut.isoformat(), "fin": fin.isoformat(), "appels": appels}, ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--plage":
        plage(sys.argv[2])
    elif len(sys.argv) >= 2:
        main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ".")
    else:
        sys.exit(__doc__)
