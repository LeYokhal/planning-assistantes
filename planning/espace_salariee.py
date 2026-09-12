"""« Mes jours » en grille (brique 6b, C6.8 / C6.9) : calcul pur des cases et des fiches du jour.

`construire_grille(resultat, absences, feries, mois, aujourd_hui)` reçoit le résultat
de `services.jours_publies` (briques de la salariée, marqueurs d'effectif), **ses**
absences (`en_attente`, `validee`, `declaree`, déjà filtrées sur la personne du
compte), les fériés du calendrier (`{iso: nom}`), le mois et la date du jour ; rend
les semaines complètes L → D du mois calendaire, une case par jour, et la légende.
Aucune requête, aucun accès à `DATA`.

Codes et priorité (D6b.3, D6b.15) : `F` > `A` (rouge si le type est bloquant, orange
sinon) > `A ?` (demande en attente) > `E` (école, reconnue par le libellé
`donnees.LIBELLE_ECOLE`) > `JC` / `J` (brique) > rien. La fiche du jour garde tout :
la brique, **toutes** les absences du jour, la raison d'une case sans marqueur
(D6b.13). Les marqueurs « − » / « + » viennent du compte-rendu de la version qui
porte le jour ; jamais sur une journée fermée.

La légende et les raisons ne reprennent aucun libellé de type d'absence ni de case
du planning (revue 4.3).
"""

import datetime

from absences.models import AbsenceSalariee
from presences.fenetres import plage_mois

from .donnees import LIBELLE_ECOLE

EN_ATTENTE = AbsenceSalariee.Statut.EN_ATTENTE
EFFECTIFS = AbsenceSalariee.STATUTS_EFFECTIFS

LEGENDE = (
    {"code": "J", "classe": "brique", "libelle": "journée"},
    {"code": "JC", "classe": "brique", "libelle": "journée courte"},
    {"code": "A", "classe": "absence-bloquante", "libelle": "absence"},
    {"code": "A ?", "classe": "attente", "libelle": "absence en attente"},
    {"code": "E", "classe": "ecole", "libelle": "école"},
    {"code": "F", "classe": "ferie", "libelle": "férié"},
    {"code": "−", "classe": "moins", "libelle": "effectif insuffisant"},
    {"code": "+", "classe": "plus", "libelle": "sureffectif"},
)

RAISON_WEEK_END = "Week-end"
RAISON_FERME = "Cabinet fermé ce jour"
RAISON_NON_IMPORTE = "Présences non importées ce jour"
RAISON_NON_RENSEIGNE = "Effectif non renseigné pour ce mois"


def _absences_par_jour(absences, plage):
    """`{iso: [absences]}` sur la plage, une absence à cheval comptant chaque jour."""
    par_jour = {}
    for absence in absences:
        jour = max(absence.date_debut, plage.debut)
        fin = min(absence.date_fin, plage.fin)
        while jour <= fin:
            par_jour.setdefault(jour.isoformat(), []).append(absence)
            jour += datetime.timedelta(days=1)
    return par_jour


def _code(ferie, absences_jour, brique):
    """`(code, classe)` de la case ; `classe` vaut None quand rien n'est à afficher."""
    effectives = [a for a in absences_jour if a.statut in EFFECTIFS]
    hors_ecole = [a for a in effectives if a.type.libelle != LIBELLE_ECOLE]
    if ferie:
        return "F", "ferie"
    if hors_ecole:
        bloquante = any(a.type.bloquant for a in hors_ecole)
        return "A", "absence-bloquante" if bloquante else "absence-partielle"
    if any(a.statut == EN_ATTENTE for a in absences_jour):
        return "A ?", "attente"
    if effectives:  # il ne reste que l'école
        return "E", "ecole"
    if brique:
        return ("JC", "brique") if brique["t"] == "C" else ("J", "brique")
    return "", None


def _raison(ferie, entree, jour, sans_compte_rendu, sans_effectif):
    """Pourquoi la case n'a pas de marqueur (D6b.13), ou None."""
    if sans_effectif:
        return None
    if ferie:
        return f"Jour férié : {ferie}"
    if entree is not None:
        if entree.get("ouvert"):
            return None
        return RAISON_WEEK_END if jour.weekday() >= 5 else RAISON_FERME
    if jour.isoformat() in sans_compte_rendu:
        return RAISON_NON_RENSEIGNE
    return RAISON_NON_IMPORTE


def _fiche_brique(brique):
    if not brique:
        return None
    return {
        "slot_libelle": brique["slot_libelle"],
        "courte": brique["t"] == "C",
        "sup": bool(brique["x"]),
    }


def _fiche_absences(absences_jour):
    return [
        {
            "type": absence.type.libelle,
            "statut": absence.get_statut_display(),
            "bloquant": bool(absence.type.bloquant),
            "ecole": absence.type.libelle == LIBELLE_ECOLE,
        }
        for absence in absences_jour
    ]


def construire_grille(resultat, absences, feries, mois, aujourd_hui):
    """`{"semaines": [[case × 7], …], "legende": LEGENDE}` pour le mois calendaire."""
    plage = plage_mois(mois)
    briques = {}
    for ligne in resultat["jours"]:
        briques.setdefault(ligne["date"].isoformat(), ligne)
    par_jour = _absences_par_jour(absences, plage)
    effectif = resultat.get("effectif") or {}
    sans_compte_rendu = set(resultat.get("sans_compte_rendu") or [])
    sans_effectif = bool(resultat.get("sans_effectif"))

    semaines = []
    jour = plage.debut
    while jour <= plage.fin:
        semaine = []
        for _ in range(7):
            iso = jour.isoformat()
            ferie = feries.get(iso)
            absences_jour = par_jour.get(iso, [])
            brique = briques.get(iso)
            entree = effectif.get(iso)
            code, classe = _code(ferie, absences_jour, brique)
            if classe is None:
                classe = "ferme" if entree is not None and not entree.get("ouvert") else "vide"
            ouvert = bool(entree and entree.get("ouvert"))
            semaine.append(
                {
                    "iso": iso,
                    "date": jour,
                    "jour": jour.day,
                    "hors_mois": jour.strftime("%Y-%m") != mois,
                    "aujourd_hui": jour == aujourd_hui,
                    "code": code,
                    "classe": classe,
                    "moins": ouvert and bool(entree.get("moins")),
                    "plus": ouvert and bool(entree.get("plus")),
                    "fiche": {
                        "brique": _fiche_brique(brique),
                        "absences": _fiche_absences(absences_jour),
                        "ferie": ferie,
                        "raison": _raison(ferie, entree, jour, sans_compte_rendu, sans_effectif),
                    },
                }
            )
            jour += datetime.timedelta(days=1)
        semaines.append(semaine)
    return {"semaines": semaines, "legende": LEGENDE}
