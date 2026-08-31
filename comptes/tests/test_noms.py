"""Recette de la normalisation des noms et des jours.

Noms fictifs. Ce module ne touche ni la base ni les réglages.
"""

import pytest

from comptes.noms import code_pour, decouper_nom_prenom, jour_canonique, normaliser


@pytest.mark.parametrize(
    "entree, attendu",
    [
        ("DUPONT Alice", "dupont alice"),
        ("dupont alice", "dupont alice"),
        ("  DUPONT   Alice  ", "dupont alice"),
        ("DUPONT Alice (Villecresnes)", "dupont alice"),
        ("Dr DUPONT Alice", "dupont alice"),
        ("Docteur DUPONT Alice", "dupont alice"),
        ("MARTIN-DUBOIS Jean-Luc", "martin dubois jean luc"),
        ("O'BRIEN Sean", "o brien sean"),
        ("DUPONT Alice 2", "dupont alice"),
        ("", ""),
        (None, ""),
    ],
)
def test_normaliser(entree, attendu):
    assert normaliser(entree) == attendu


def test_normaliser_accents_composes_et_decomposes():
    """Précomposé et « e + accent combinant » doivent se rejoindre.

    L'assertion d'inégalité qui suit n'est pas décorative : si un outil
    d'édition uniformisait les deux formes, le test cesserait de vérifier quoi
    que ce soit — il échouerait au lieu de passer en silence (leçon de la 1b).
    """
    compose = "LÉVÊQUE Chloé"
    decompose = "LÉVÊQUE Chloé"

    assert compose != decompose
    assert normaliser(compose) == normaliser(decompose) == "leveque chloe"


@pytest.mark.parametrize(
    "prenom, nom, attendu",
    [
        ("Léa", "DEHU", "lea_deh"),
        ("Jean-Luc", "MARTIN-DUBOIS", "jeanluc_mar"),
        ("Ana", "DA SILVA COSTA", "ana_das"),
        ("Alice", "DUPONT", "alice_dup"),
    ],
)
def test_code_pour(prenom, nom, attendu):
    assert code_pour(prenom, nom) == attendu


def test_code_pour_collision_sur_trois_lettres():
    """Trois lettres de nom ne suffisent pas toujours : c'est assumé et traité ailleurs."""
    assert code_pour("Jean", "MARTIN") == code_pour("Jean", "MARTINEZ")


@pytest.mark.parametrize("prenom, nom", [("", "DUPONT"), ("Alice", ""), ("", "")])
def test_code_pour_sans_matiere(prenom, nom):
    assert code_pour(prenom, nom) == ""


@pytest.mark.parametrize(
    "entree, attendu",
    [
        ("DUPONT Alice", ("DUPONT", "Alice")),
        ("DA SILVA COSTA Ana", ("DA SILVA COSTA", "Ana")),
        ("MARTIN-DUBOIS Jean-Luc", ("MARTIN-DUBOIS", "Jean-Luc")),
        ("O'BRIEN Sean", ("O'BRIEN", "Sean")),
        ("LÉVÊQUE Chloé", ("LÉVÊQUE", "Chloé")),
    ],
)
def test_decouper_nom_prenom(entree, attendu):
    assert decouper_nom_prenom(entree) == attendu


@pytest.mark.parametrize(
    "entree",
    ["New team member", "Dupont", "", None, "   ", "Alice Dupont"],
)
def test_decouper_nom_prenom_hors_convention(entree):
    assert decouper_nom_prenom(entree) is None


@pytest.mark.parametrize(
    "entree, attendu",
    [
        ("Mardi", "Mardi"),
        ("mardi", "Mardi"),
        ("MARDI", "Mardi"),
        ("Mardi ", "Mardi"),
        ("mercredi", "Mercredi"),
        ("Marsdi", None),
        ("", None),
        (None, None),
    ],
)
def test_jour_canonique(entree, attendu):
    assert jour_canonique(entree) == attendu
