"""Recette de la lecture d'un export de fiche personnel.

Noms fictifs uniquement. Aucune de ces lectures ne touche la base.
"""

import json

import pytest

from personnes.lecture_fiche import (
    MOTIF_CONVENTION,
    MOTIF_DEPARTEMENT,
    MOTIF_HEURES,
    MOTIF_JOURS,
    MOTIF_PLANNING,
    FicheInvalide,
    lire,
)

from .fabrique_fiche import MANQUANT, fiche, fiche_liste, ligne_fiche


def motifs(lecture):
    return [motif for _, _, motif in lecture.ignorees]


# --- Formes acceptées --------------------------------------------------------


def test_forme_results():
    lecture = lire(fiche([ligne_fiche("DUPONT Alice")]))

    assert len(lecture.lignes) == 1
    assert lecture.lignes[0].nom == "DUPONT"
    assert lecture.lignes[0].prenom == "Alice"


def test_forme_liste_directe():
    lecture = lire(fiche_liste([ligne_fiche("DUPONT Alice")]))

    assert len(lecture.lignes) == 1


def test_numero_de_ligne_conserve():
    lecture = lire(
        fiche([ligne_fiche("DUPONT Alice"), ligne_fiche("MARTIN Bob")])
    )

    assert [ligne.numero for ligne in lecture.lignes] == [1, 2]


# --- Refus du fichier entier -------------------------------------------------


def test_json_illisible():
    with pytest.raises(FicheInvalide, match="JSON illisible"):
        lire(b"{ pas du json")


def test_forme_inconnue():
    with pytest.raises(FicheInvalide, match="forme inconnue"):
        lire(json.dumps({"autre_chose": []}).encode("utf-8"))


def test_colonne_inattendue_refuse_le_fichier():
    ligne = ligne_fiche("DUPONT Alice")
    ligne["NSS"] = "peu importe"

    with pytest.raises(FicheInvalide) as echec:
        lire(fiche([ligne]))

    message = str(echec.value)
    assert "colonnes inattendues" in message
    assert "NSS" in message
    # Le message ne cite QUE des noms de colonnes, jamais une valeur.
    assert "peu importe" not in message


def test_colonne_manquante_refuse_le_fichier():
    with pytest.raises(FicheInvalide) as echec:
        lire(fiche([ligne_fiche("DUPONT Alice", heures=MANQUANT)]))

    assert "colonnes manquantes" in str(echec.value)
    assert "Heures hebdomadaire" in str(echec.value)


# --- Lignes ignorées ---------------------------------------------------------


def test_departement_inconnu_ignore():
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", department="Comptabilité")]))

    assert lecture.lignes == []
    assert motifs(lecture) == [MOTIF_DEPARTEMENT]


def test_ligne_modele_hors_convention_ignoree():
    lecture = lire(fiche([ligne_fiche("New team member")]))

    assert lecture.lignes == []
    assert motifs(lecture) == [MOTIF_CONVENTION]


def test_nom_sans_prenom_ignore():
    lecture = lire(fiche([ligne_fiche("Dupont")]))

    assert motifs(lecture) == [MOTIF_CONVENTION]


def test_planning_illisible_ignore():
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", planning="peut-être")]))

    assert motifs(lecture) == [MOTIF_PLANNING]


def test_heures_en_chaine_ignorees():
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", heures="39")]))

    assert motifs(lecture) == [MOTIF_HEURES]


def test_jours_invalides_ignores():
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", jours=["Lundi", "Marsdi"])]))

    assert motifs(lecture) == [MOTIF_JOURS]


def test_libelle_de_la_ligne_ignoree_conserve():
    lecture = lire(fiche([ligne_fiche("New team member")]))

    numero, libelle, _ = lecture.ignorees[0]
    assert (numero, libelle) == (1, "New team member")


def test_lignes_valides_et_ignorees_cohabitent():
    lecture = lire(
        fiche(
            [
                ligne_fiche("DUPONT Alice"),
                ligne_fiche("New team member"),
                ligne_fiche("MARTIN Bob"),
            ]
        )
    )

    assert [ligne.nom for ligne in lecture.lignes] == ["DUPONT", "MARTIN"]
    assert motifs(lecture) == [MOTIF_CONVENTION]


# --- Découpage du nom --------------------------------------------------------


def test_nom_compose_de_plusieurs_mots():
    lecture = lire(fiche([ligne_fiche("DA SILVA COSTA Ana")]))

    assert (lecture.lignes[0].nom, lecture.lignes[0].prenom) == (
        "DA SILVA COSTA",
        "Ana",
    )


def test_nom_et_prenom_a_trait_d_union():
    lecture = lire(fiche([ligne_fiche("MARTIN-DUBOIS Jean-Luc")]))

    assert (lecture.lignes[0].nom, lecture.lignes[0].prenom) == (
        "MARTIN-DUBOIS",
        "Jean-Luc",
    )


# --- Colonnes ----------------------------------------------------------------


@pytest.mark.parametrize(
    "departement, attendu",
    [
        ("Assistante", "assistante"),
        ("assistante", "assistante"),
        ("Praticien", "praticien"),
        ("Secretariat", "secretaire"),
        ("Secrétariat", "secretaire"),
    ],
)
def test_departements_reconnus(departement, attendu):
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", department=departement)]))

    assert lecture.lignes[0].role_metier == attendu


@pytest.mark.parametrize(
    "valeur, attendu",
    [("__YES__", True), (True, True), ("__NO__", False), (False, False), (None, False)],
)
def test_planning_interprete(valeur, attendu):
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", planning=valeur)]))

    assert lecture.lignes[0].planifiee is attendu


@pytest.mark.parametrize("valeur, attendu", [(None, None), (39, 39), (27, 27)])
def test_heures_interpretees(valeur, attendu):
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", heures=valeur)]))

    assert lecture.lignes[0].heures == attendu


@pytest.mark.parametrize(
    "valeur, attendu",
    [
        (None, ()),
        ("", ()),
        (["Mardi", "Jeudi"], ("Mardi", "Jeudi")),
        (["mardi", "JEUDI"], ("Mardi", "Jeudi")),
        (["Mercredi "], ("Mercredi",)),
        ('["Mardi", "Jeudi"]', ("Mardi", "Jeudi")),
    ],
)
def test_jours_canoniques(valeur, attendu):
    lecture = lire(fiche([ligne_fiche("DUPONT Alice", jours=valeur)]))

    assert lecture.lignes[0].jours == attendu
