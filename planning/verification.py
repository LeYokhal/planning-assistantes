"""Vérification stricte d'un état de planning, côté serveur (brique 4a).

Mêmes règles et mêmes codes que `verifier()` du moteur JS
(`planning/static/planning/moteur.js`) : les deux implémentations sont
éprouvées sur le même jeu de cas, `planning/tests/cas_verification.json`.
Une divergence est un test rouge.

Une violation ne porte que `code`, `date`, `slot`, `s` : jamais de texte libre,
jamais de type d'absence. Le message français est composé par la page à partir
du code.

Le port de `virtuels` / `consommer` / `quota` / `reserve` (gabarit l.400-455)
sert à `quota_depasse` ; c'est la seule règle qui regarde une semaine entière.
"""

import copy
import datetime
from dataclasses import dataclass

BRIQUES = ("J", "C")
MISC = ("secretariat", "sureffectif", "administratif")
CLES_STATE = ("affectations", "feries", "feries_off", "notes")
CODES = (
    "hors_plage",
    "salariee_inconnue",
    "slot_inconnu",
    "brique_invalide",
    "doublon_jour",
    "jour_bloque",
    "jour_non_affiche",
    "sans_donnees",
    "praticien_absent",
    "capacite",
    "exclusive_ailleurs",
    "exclusif_intrus",
    "quota_depasse",
)


@dataclass(frozen=True)
class Violation:
    """Une règle stricte enfreinte. Sans message : le code suffit."""

    code: str
    date: str = None
    slot: str = None
    s: str = None

    def en_dict(self):
        return {"code": self.code, "date": self.date, "slot": self.slot, "s": self.s}


# --- Nettoyage -------------------------------------------------------------------


def _liste_de_notes(brut):
    liste = [brut] if isinstance(brut, str) else brut if isinstance(brut, list) else []
    return [x.strip() for x in liste if isinstance(x, str) and x.strip()]


def nettoyer(state):
    """Réduit un état reçu aux quatre clés du contrat, copiées.

    `notes` accepte une chaîne (ancien format, gabarit l.591) ou une liste de
    chaînes, et rend toujours une liste. Les briques ne sont pas filtrées ici :
    c'est `verifier` qui les juge, brique par brique.
    """
    if not isinstance(state, dict):
        state = {}
    affectations = state.get("affectations")
    affectations = copy.deepcopy(affectations) if isinstance(affectations, dict) else {}
    feries_brut = state.get("feries")
    feries = (
        {str(cle): str(nom) for cle, nom in feries_brut.items()}
        if isinstance(feries_brut, dict)
        else {}
    )
    off_brut = state.get("feries_off")
    feries_off = [x for x in off_brut if isinstance(x, str)] if isinstance(off_brut, list) else []
    notes = {}
    notes_brut = state.get("notes")
    if isinstance(notes_brut, dict):
        for cle, valeur in notes_brut.items():
            liste = _liste_de_notes(valeur)
            if liste:
                notes[str(cle)] = liste
    return {
        "affectations": affectations,
        "feries": feries,
        "feries_off": feries_off,
        "notes": notes,
    }


# --- Lecture de DATA et de l'état (port du gabarit l.354-455) -------------------


def _date_valide(iso):
    if not isinstance(iso, str) or len(iso) != 10:
        return False
    try:
        return datetime.date.fromisoformat(iso).isoformat() == iso
    except ValueError:
        return False


def _weekday(iso):
    return datetime.date.fromisoformat(iso).weekday()


class _Lecture:
    """Les fonctions de lecture du gabarit, fermées sur `DATA` et un état propre."""

    def __init__(self, data, state):
        self.data = data
        self.state = state
        meta = data["meta"]
        self.debut = meta["debut"]
        self.fin = meta["fin"]
        self.sal = {s["id"]: s for s in data.get("salaries") or []}
        self.prat = {p["id"]: p for p in data.get("praticiens") or []}
        self.jours = data.get("jours") or {}
        self.feries = data.get("feries") or {}
        self.cours = data.get("cours") or {}
        self.non_couverts = set(meta.get("non_couverts") or [])
        self.conges = {}
        for conge in data.get("conges") or []:
            self.conges.setdefault(conge["s"], {})[conge["date"]] = conge
        self.weeks = []
        debut = datetime.date.fromisoformat(self.debut)
        fin = datetime.date.fromisoformat(self.fin)
        lundi = debut
        while lundi <= fin:
            jours = [(lundi + datetime.timedelta(days=n)).isoformat() for n in range(7)]
            self.weeks.append({"start": lundi.isoformat(), "days": jours})
            lundi += datetime.timedelta(days=7)
        # Colonnes affichées : jours où quelqu'un est présent ou a un jour fixe,
        # jamais le dimanche (gabarit l.368-375).
        shown = set()
        for iso, lignes in self.jours.items():
            if any(ligne.get("pr") for ligne in lignes.values()):
                shown.add(_weekday(iso))
        for s in self.sal.values():
            shown.update(s.get("fixes") or [])
        for p in self.prat.values():
            if not p.get("agenda"):
                shown.update(p.get("fixes") or [])
        shown.discard(6)
        self.shown = shown

    # -- calendrier et blocages
    def shown_days(self, week):
        return [iso for iso in week["days"] if _weekday(iso) in self.shown]

    def is_ferie(self, iso):
        return (iso in self.feries and iso not in self.state["feries_off"]) or (
            iso in self.state["feries"]
        )

    def conge_de(self, sid, iso):
        return self.conges.get(sid, {}).get(iso)

    def cours_de(self, sid, iso):
        return iso in (self.cours.get(sid) or [])

    def bloque(self, sid, iso):
        conge = self.conge_de(sid, iso)
        return (
            self.is_ferie(iso)
            or bool(conge and conge.get("bloque") is True)
            or self.cours_de(sid, iso)
        )

    def present(self, iso, p):
        """Présence brute du praticien, hors férié (le férié relève de `bloque`)."""
        if p.get("agenda"):
            ligne = (self.jours.get(iso) or {}).get(p["id"])
            return bool(ligne and ligne.get("pr"))
        return _weekday(iso) in (p.get("fixes") or [])

    # -- réserve hebdomadaire (gabarit l.400-455)
    def virtuels(self, s, week):
        out = []
        for iso in week["days"]:
            if self.cours_de(s["id"], iso):
                out.append({"prefer": "C"})
                continue
            if _weekday(iso) not in self.shown:
                continue
            if (
                s.get("role") == "secretaire"
                and s.get("fixes")
                and _weekday(iso) not in s["fixes"]
            ):
                continue
            conge = self.conge_de(s["id"], iso)
            if conge and conge.get("bloque"):
                out.append({})
            elif self.is_ferie(iso) and _weekday(iso) <= 4:
                out.append({})
        return out

    @staticmethod
    def consommer(bricks, items):
        q = list(bricks)
        for item in items:
            prefer = item.get("prefer")
            if prefer and prefer in q:
                t = prefer
            elif "J" in q:
                t = "J"
            else:
                t = q[-1] if q else None
            if t is not None and t in q:
                q.remove(t)
        return q

    def quota(self, s, week):
        jours = self.shown_days(week)
        if s.get("role") == "secretaire" and s.get("fixes"):
            return ["J" for iso in jours if _weekday(iso) in s["fixes"]]
        return list(s.get("gabarit") or [])

    def placed(self, s, week):
        out = []
        for iso in week["days"]:
            slots = self.state["affectations"].get(iso)
            if not isinstance(slots, dict):
                continue
            for arr in slots.values():
                if not isinstance(arr, list):
                    continue
                for b in arr:
                    if isinstance(b, dict) and b.get("s") == s["id"]:
                        out.append(b)
        return out

    def reserve(self, s, week):
        q = self.consommer(self.quota(s, week), self.virtuels(s, week))
        over = 0
        for b in self.placed(s, week):
            if b.get("x"):
                continue
            if b.get("t") in q:
                q.remove(b["t"])
            elif q:
                q.pop()
            else:
                over += 1
        return {"rest": q, "over": over}


# --- Vérification ----------------------------------------------------------------


def verifier(data, state):
    """Liste des violations strictes d'un état PROPRE (passé par `nettoyer`).

    Ordre : affectations jour par jour, puis doublons, puis dates hors plage
    des fériés et notes, puis la réserve hebdomadaire de chaque salariée.
    """
    lecture = _Lecture(data, state)
    violations = []
    dans_plage = lambda iso: _date_valide(iso) and lecture.debut <= iso <= lecture.fin  # noqa: E731

    par_jour = {}
    for iso, slots in state["affectations"].items():
        if not dans_plage(iso):
            violations.append(Violation("hors_plage", iso if isinstance(iso, str) else None))
            continue
        if not isinstance(slots, dict):
            violations.append(Violation("brique_invalide", iso))
            continue
        for slot, arr in slots.items():
            if slot not in lecture.prat and slot not in MISC:
                violations.append(Violation("slot_inconnu", iso, slot))
                continue
            if not isinstance(arr, list):
                violations.append(Violation("brique_invalide", iso, slot))
                continue
            for b in arr:
                s = b.get("s") if isinstance(b, dict) else None
                if (
                    not isinstance(b, dict)
                    or b.get("t") not in BRIQUES
                    or not isinstance(s, str)
                ):
                    violations.append(
                        Violation("brique_invalide", iso, slot, s if isinstance(s, str) else None)
                    )
                    continue
                if s not in lecture.sal:
                    violations.append(Violation("salariee_inconnue", iso, slot, s))
                    continue
                par_jour.setdefault(iso, {})
                par_jour[iso][s] = par_jour[iso].get(s, 0) + 1
                if lecture.bloque(s, iso):
                    violations.append(Violation("jour_bloque", iso, slot, s))
                if slot in lecture.prat:
                    p = lecture.prat[slot]
                    if iso in lecture.non_couverts:
                        violations.append(Violation("sans_donnees", iso, slot, s))
                    elif not lecture.present(iso, p):
                        violations.append(Violation("praticien_absent", iso, slot, s))
                    # Une exclusive ne va chez aucun autre praticien ; les slots
                    # secrétariat / sureffectif / administratif lui restent
                    # ouverts (le moteur y pose son reliquat, gabarit l.724).
                    if lecture.sal[s].get("exclusif") and slot not in (
                        lecture.sal[s].get("binomes") or []
                    ):
                        violations.append(Violation("exclusive_ailleurs", iso, slot, s))
                    if p.get("exclusif") and s not in (p.get("binomes") or []):
                        violations.append(Violation("exclusif_intrus", iso, slot, s))
                elif _weekday(iso) not in lecture.shown:
                    violations.append(Violation("jour_non_affiche", iso, slot, s))
            if slot in lecture.prat and len(arr) > (lecture.prat[slot].get("attendues") or 1):
                violations.append(Violation("capacite", iso, slot))

    for iso, comptes in par_jour.items():
        for s, nombre in comptes.items():
            if nombre > 1:
                violations.append(Violation("doublon_jour", iso, None, s))

    for iso in list(state["feries"]) + list(state["feries_off"]) + list(state["notes"]):
        if not dans_plage(iso):
            violations.append(Violation("hors_plage", iso if isinstance(iso, str) else None))

    for s in data.get("salaries") or []:
        for week in lecture.weeks:
            if lecture.reserve(s, week)["over"] > 0:
                violations.append(Violation("quota_depasse", week["start"], None, s["id"]))

    return violations
