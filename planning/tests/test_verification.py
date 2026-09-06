"""Vérification stricte côté serveur, sur le jeu de cas commun avec le moteur JS.

`cas_verification.json` est lu tel quel ici et par
`planning/tests_js/verification.test.js` : un cas qui passe d'un côté et pas de
l'autre est une divergence entre les deux implémentations.
"""

import json
from pathlib import Path

import pytest

from planning.verification import CODES, Violation, nettoyer, verifier

FICHIER = json.loads(
    (Path(__file__).resolve().parent / "cas_verification.json").read_text(encoding="utf-8")
)
CAS = FICHIER["cas"]


def data_de(cas):
    return json.loads(json.dumps(cas.get("data") or FICHIER["data_commune"]))


@pytest.mark.parametrize("cas", CAS, ids=[cas["nom"] for cas in CAS])
def test_cas_commun(cas):
    codes = sorted(v.code for v in verifier(data_de(cas), nettoyer(cas["state"])))
    assert codes == sorted(cas["attendu"])


def test_tous_les_codes_sont_emis_par_le_jeu_de_cas():
    emis = set()
    for cas in CAS:
        emis.update(v.code for v in verifier(data_de(cas), nettoyer(cas["state"])))
    assert emis == set(CODES)


def test_violation_sans_texte():
    violation = Violation("capacite", "2026-09-29", "alice_dup")
    assert violation.en_dict() == {"code": "capacite", "date": "2026-09-29", "slot": "alice_dup", "s": None}
    assert set(Violation.__dataclass_fields__) == {"code", "date", "slot", "s"}


def test_nettoyer_reduit_aux_quatre_cles_et_normalise_les_notes():
    propre = nettoyer(
        {
            "affectations": {"2026-09-29": {}},
            "conges": [{"s": "x", "type": "Maladie"}],
            "cours": {},
            "modifie": "hier",
            "initialise": True,
            "feries": {"2026-10-02": 7},
            "feries_off": ["2026-11-01", 3, None],
            "notes": {"a": " un ", "b": ["", "deux", 4], "c": [], "d": ""},
        }
    )
    assert propre == {
        "affectations": {"2026-09-29": {}},
        "feries": {"2026-10-02": "7"},
        "feries_off": ["2026-11-01"],
        "notes": {"a": ["un"], "b": ["deux"]},
    }


def test_nettoyer_copie_les_affectations():
    brut = {"affectations": {"2026-09-29": {"alice_dup": [{"s": "emma_ber", "t": "J"}]}}}
    propre = nettoyer(brut)
    propre["affectations"]["2026-09-29"]["alice_dup"][0]["s"] = "autre"
    assert brut["affectations"]["2026-09-29"]["alice_dup"][0]["s"] == "emma_ber"


@pytest.mark.parametrize("brut", [None, 42, "texte", [], {"affectations": []}])
def test_nettoyer_tolere_n_importe_quoi(brut):
    assert nettoyer(brut) == {"affectations": {}, "feries": {}, "feries_off": [], "notes": {}}


def test_notes_en_chaine_et_en_liste_sont_equivalentes():
    assert nettoyer({"notes": {"2026-09-29": "un mot"}}) == nettoyer({"notes": {"2026-09-29": ["un mot"]}})
