"""Marqueurs d'effectif d'une version publiée (brique 6b, C6.9) : `effectif.calculer` et `effectif.lire`.

`calculer` est éprouvé sur `data_commune` de `cas_verification.json` — le jeu fictif du
moteur : trois praticiens à agenda Doctolib, plage 2026-09-28 → 2026-11-01, un férié de
test le samedi 17 octobre, le 31 octobre non couvert — et sur des états construits par
`fabrique`. Décisions D6b.12 (« − » = un praticien présent sans aucune brique dans sa
colonne), D6b.13 (`ouvert` faux un férié ou un jour non affiché, aucune entrée un jour
non couvert), D6b.14 (« + » = une brique hors heures sup dans « sureffectif ») ;
revue 4.1 (b) : le férié est celui du calendrier seul.
"""

import copy
import datetime
import json
import re
from pathlib import Path

import pytest

from planning import effectif, historique
from planning.models import PlanningVersion
from planning.tests import fabrique

FICHIER = json.loads(
    (Path(__file__).resolve().parent / "cas_verification.json").read_text(encoding="utf-8")
)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Dates du jeu : mardi 29 septembre (les trois praticiens présents), mercredi 30 (Alice et
# Chloe), samedi 3 octobre (Chloe seule, exclusive à deux binômes), lundi 5 (personne :
# jour non affiché), samedi 17 (férié de test), samedi 31 (non couvert), dimanche 1er
# novembre (Toussaint).
MARDI, MERCREDI, SAMEDI, LUNDI = "2026-09-29", "2026-09-30", "2026-10-03", "2026-10-05"
FERIE, NON_COUVERT, TOUSSAINT = "2026-10-17", "2026-10-31", "2026-11-01"
FERME = {"moins": False, "plus": False, "ouvert": False}


def data_commune():
    return copy.deepcopy(FICHIER["data_commune"])


def calculer(affectations=None, data=None, **cles):
    return effectif.calculer(data or data_commune(), fabrique.etat(affectations, **cles))["jours"]


# --- « − » : praticien présent sans brique (D6b.12) -------------------------------


def test_praticien_present_sans_brique_allume_moins():
    jours = calculer()
    assert jours[MARDI] == {"moins": True, "plus": False, "ouvert": True}
    assert jours[SAMEDI]["moins"] is True  # Chloe seule présente, colonne vide


def test_tous_les_presents_pourvus_n_allument_pas_moins():
    # Mercredi 30 : Alice et Chloe présentes, une brique chacune.
    pourvus = calculer(
        {MERCREDI: {"alice_dup": [fabrique.brique("emma_ber")], "chloe_ler": [fabrique.brique("zoe_gir")]}}
    )
    assert pourvus[MERCREDI] == {"moins": False, "plus": False, "ouvert": True}
    # La même journée sans la brique de Chloe : « − ».
    assert calculer({MERCREDI: {"alice_dup": [fabrique.brique("emma_ber")]}})[MERCREDI]["moins"] is True


def test_exclusif_a_deux_binomes_avec_une_seule_brique_n_allume_pas_moins():
    """D6b.12 : zéro brique, pas « moins que `attendues` » (Chloe en attend deux)."""
    assert calculer({SAMEDI: {"chloe_ler": [fabrique.brique("zoe_gir")]}})[SAMEDI]["moins"] is False


def test_praticien_a_jours_fixes_present_sans_brique_allume_moins():
    """Revue 3.1 : sans agenda, aucune ligne dans `data["jours"]` ; ses jours fixes le rendent présent."""
    data = data_commune()
    bob = next(p for p in data["praticiens"] if p["id"] == "bob_mar")
    bob["agenda"] = None
    bob["fixes"] = [0]  # lundi
    assert LUNDI not in data["jours"]
    assert calculer(data=data)[LUNDI] == {"moins": True, "plus": False, "ouvert": True}
    # Avec sa brique du lundi : rien à signaler.
    assert calculer({LUNDI: {"bob_mar": [fabrique.brique("lina_rou")]}}, data=data)[LUNDI]["moins"] is False


# --- « + » : sureffectif (D6b.14) --------------------------------------------------


def test_brique_en_sureffectif_allume_plus():
    assert calculer({MARDI: {"sureffectif": [fabrique.brique("nora_fon")]}})[MARDI]["plus"] is True


def test_seule_brique_en_sureffectif_hors_quota_n_allume_pas_plus():
    seule = calculer({MARDI: {"sureffectif": [fabrique.brique("nora_fon", x=True)]}})
    assert seule[MARDI]["plus"] is False
    melange = calculer(
        {MARDI: {"sureffectif": [fabrique.brique("nora_fon", x=True), fabrique.brique("lea_mor", "C")]}}
    )
    assert melange[MARDI]["plus"] is True


# --- jours fermés et jours non couverts (D6b.13) ------------------------------------


def test_ferie_du_calendrier_est_ferme_meme_avec_des_briques():
    jours = calculer({FERIE: {"sureffectif": [fabrique.brique("nora_fon")]}})
    assert jours[FERIE] == FERME
    assert jours[TOUSSAINT] == FERME


def test_jour_non_affiche_est_ferme():
    """Le lundi n'est dans `shown` de personne : la journée est fermée, sans marqueur."""
    jours = calculer()
    assert jours[LUNDI] == FERME
    assert jours["2026-10-04"] == FERME  # dimanche


def test_jour_non_couvert_sans_entree_et_tous_les_autres_avec():
    jours = calculer()
    attendues = []
    jour = datetime.date(2026, 9, 28)
    while jour <= datetime.date(2026, 11, 1):
        if jour.isoformat() != NON_COUVERT:
            attendues.append(jour.isoformat())
        jour += datetime.timedelta(days=1)
    assert list(jours) == attendues  # 34 entrées, dates triées
    assert NON_COUVERT not in jours


def test_pont_ajoute_et_ferie_rouvert_de_la_page_sont_ignores():
    """Revue 4.1 (b) : le calendrier seul fait le férié ; `state["feries"]` et `feries_off` ne comptent pas."""
    jours = calculer({}, feries={"2026-10-06": "Fermé (ajouté)"}, feries_off=[FERIE])
    assert jours["2026-10-06"]["ouvert"] is True
    assert jours[FERIE]["ouvert"] is False


def test_entrees_booleennes_et_dates_seulement():
    resultat = effectif.calculer(data_commune(), fabrique.etat_propre())
    assert set(resultat) == {"jours"}
    for iso, entree in resultat["jours"].items():
        assert ISO.match(iso), iso
        assert set(entree) == {"moins", "plus", "ouvert"}
        assert all(isinstance(valeur, bool) for valeur in entree.values())
    texte = json.dumps(resultat)
    for mot in ("emma_ber", "sara_pet", "alice_dup", "BERNARD", "Maladie", "secretariat"):
        assert mot not in texte, mot


def test_etat_brut_est_nettoye_avant_lecture():
    """Un état non nettoyé (clé en trop, `feries_off` mal formé) ne fait pas tomber le calcul."""
    brut = {
        "affectations": {MARDI: {"alice_dup": [fabrique.brique("emma_ber")]}},
        "conges": [{"s": "x"}],
        "feries_off": None,
    }
    assert effectif.calculer(data_commune(), brut)["jours"][MARDI]["moins"] is True  # Bob et Chloe sans brique


# --- lire ----------------------------------------------------------------------------


def test_lire_rend_les_jours_du_compte_rendu():
    entree = {MARDI: {"moins": True, "plus": False, "ouvert": True}}
    version = PlanningVersion(verifications={"verifie_le": "x", "effectif": {"jours": entree, "calcule_le": "x"}})
    assert effectif.lire(version) == entree


@pytest.mark.parametrize(
    "verifications",
    [[], {}, {"verifie_le": "x", "imports": [], "nb_briques": 2}, {"effectif": None}, {"effectif": {}}],
)
def test_lire_sans_compte_rendu_rend_vide(verifications):
    assert effectif.lire(PlanningVersion(verifications=verifications)) == {}


@pytest.mark.django_db
def test_lire_une_version_historique_rend_vide(cabinet):
    """C7.8 : une version importée (brique 7a) n'a pas de compte-rendu, et n'en aura pas."""
    fabrique.personnes_historiques()
    version = historique.executer(
        historique.analyser(fabrique.planning_exporte(affectations=fabrique.affectations_historiques())), cabinet
    )
    assert version.publiee is True
    assert effectif.lire(version) == {}
