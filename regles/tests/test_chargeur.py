"""Recette du chargement de `regles.json`.

Le fichier réel du dépôt est vérifié tel quel ; toutes les variantes fautives
sont fabriquées dans un fichier temporaire, jamais en modifiant le vrai.
"""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured

from regles import chargeur

# Un jeu de règles minimal mais valide, sur lequel greffer chaque faute.
BASE = {
    "_doc": "règles de test",
    "gabarits": {"_doc": "ignoré", "39": ["J", "J", "J", "J"]},
    "binomes": [
        {"assistante": "DUPONT Alice", "praticien": "MARTIN Bob"},
        {"assistante": "DA SILVA COSTA Ana", "praticien": "LEROY Chloe", "exclusif": True},
    ],
    "praticiens_exclusifs": {"_doc": "ignoré", "liste": ["LEROY Chloe"]},
    "creneau_administratif": [{"salariee": "DUPONT Alice", "brique": "C"}],
    "couleurs": {"DUPONT Alice": "yellow", "MARTIN Bob": "blue"},
    "praticiens_a_part": {"liste": [{"nom": "LEROY Chloe", "etiquette": "ortho"}]},
    "heures_par_brique": {"_doc": "ignoré", "J": 9.75, "C": 6.75},
    # Section ajoutée en brique 3 : elle est obligatoire, comme les gabarits.
    "periodes_ouverture": {
        "liste": [
            {"a_partir_du": None, "jours": ["Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]},
            {"a_partir_du": "2026-10-05", "jours": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]},
        ]
    },
    "etudiantes": {
        "liste": [
            {
                "nom": "DA SILVA COSTA Ana",
                "gabarit_sans_cours": ["J", "J", "J", "C"],
                "mot_cle_notion": "école",
            }
        ]
    },
}


@pytest.fixture(autouse=True)
def cache_vierge():
    """Le chargeur met en cache par chemin : chaque test repart à zéro."""
    chargeur._CACHE.clear()
    yield
    chargeur._CACHE.clear()


def ecrire(tmp_path, contenu, nom="regles.json"):
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return chemin


class PersonneFictive:
    """Le chargeur ne lit que `nom` et `prenom` : pas besoin de la base."""

    def __init__(self, nom, prenom):
        self.nom = nom
        self.prenom = prenom


# --- Le fichier réel du dépôt ------------------------------------------------


def test_fichier_du_depot_se_charge():
    regles = chargeur.charger()

    assert len(regles.noms) == 18
    assert len(regles.binomes) == 6
    assert len(regles.praticiens_exclusifs) == 1
    assert regles.gabarits[39] == ("J", "J", "J", "J")
    assert regles.heures_par_brique == {"J": 9.75, "C": 6.75}


def test_chargement_mis_en_cache():
    assert chargeur.charger() is chargeur.charger()


def test_cles_de_documentation_ignorees(tmp_path):
    regles = chargeur.charger(ecrire(tmp_path, BASE))

    # « _doc » figure dans gabarits et heures_par_brique : il n'en reste rien.
    assert set(regles.gabarits) == {39}
    assert set(regles.heures_par_brique) == {"J", "C"}


# --- Refus -------------------------------------------------------------------


def test_fichier_absent(tmp_path):
    with pytest.raises(ImproperlyConfigured, match="introuvable"):
        chargeur.charger(tmp_path / "nulle-part.json")


def test_json_illisible(tmp_path):
    chemin = tmp_path / "regles.json"
    chemin.write_text("{ pas du json", encoding="utf-8")

    with pytest.raises(ImproperlyConfigured, match="JSON illisible"):
        chargeur.charger(chemin)


def test_gabarit_de_brique_inconnue(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["gabarits"]["39"] = ["J", "X"]

    with pytest.raises(ImproperlyConfigured, match="attendu J ou C"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_binome_sans_praticien(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["binomes"][0].pop("praticien")

    with pytest.raises(ImproperlyConfigured, match="chaîne non vide"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_exclusif_absent_des_binomes(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["praticiens_exclusifs"]["liste"] = ["MARTIN Bob"]

    with pytest.raises(ImproperlyConfigured, match="binôme marqué exclusif"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_creneau_administratif_de_brique_inconnue(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["creneau_administratif"][0]["brique"] = "Z"

    with pytest.raises(ImproperlyConfigured, match="brique « Z » inconnue"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_heures_par_brique_negatives(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["heures_par_brique"]["C"] = 0

    with pytest.raises(ImproperlyConfigured, match="strictement positif"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_etudiante_sans_mot_cle(tmp_path):
    fautif = json.loads(json.dumps(BASE))
    fautif["etudiantes"]["liste"][0]["mot_cle_notion"] = ""

    with pytest.raises(ImproperlyConfigured, match="chaîne non vide"):
        chargeur.charger(ecrire(tmp_path, fautif))


# --- Couleurs et vérification ------------------------------------------------


def test_couleur_insensible_a_la_casse_aux_accents_et_au_suffixe(tmp_path, settings):
    settings.REGLES_FICHIER = ecrire(tmp_path, BASE)

    assert chargeur.couleur_de("dupont alice") == "yellow"
    assert chargeur.couleur_de("DUPONT ALICE (Villecresnes)") == "yellow"
    assert chargeur.couleur_de("Dr MARTIN Bob") == "blue"
    assert chargeur.couleur_de("INCONNUE Zoe") == ""


def test_verifier_compte_les_noms_resolus(tmp_path, settings):
    settings.REGLES_FICHIER = ecrire(tmp_path, BASE)

    rapport = chargeur.verifier(
        [
            PersonneFictive("DUPONT", "Alice"),
            PersonneFictive("MARTIN", "Bob"),
        ]
    )

    # Quatre noms distincts dans BASE, deux reconnus.
    assert rapport.total == 4
    assert rapport.resolus == 2
    assert set(rapport.non_resolus) == {"DA SILVA COSTA Ana", "LEROY Chloe"}


def test_verifier_tout_resolu(tmp_path, settings):
    settings.REGLES_FICHIER = ecrire(tmp_path, BASE)

    rapport = chargeur.verifier(
        [
            PersonneFictive("DUPONT", "Alice"),
            PersonneFictive("MARTIN", "Bob"),
            PersonneFictive("DA SILVA COSTA", "Ana"),
            PersonneFictive("LEROY", "Chloe"),
        ]
    )

    assert rapport.non_resolus == ()
    assert rapport.resolus == rapport.total == 4
