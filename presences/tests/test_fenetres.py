"""Recette des plages de mois et des fenêtres d'appel.

Les valeurs attendues d'octobre 2026 sont celles du jeu S7 réel de la phase 1 :
deux appels, 2026-09-28 → 2026-10-28 puis 2026-10-29 → 2026-11-01.
"""

import datetime

import pytest

from presences.fenetres import (
    FENETRE_MAX_JOURS,
    libelle_mois,
    mois_de_fenetre,
    mois_precedent,
    mois_suivant,
    plage_mois,
)

D = datetime.date


def test_octobre_2026_reproduit_le_jeu_reel():
    plage = plage_mois("2026-10")
    assert plage.debut == D(2026, 9, 28)
    assert plage.fin == D(2026, 11, 1)
    assert plage.fenetres == (
        (D(2026, 9, 28), D(2026, 10, 28)),
        (D(2026, 10, 29), D(2026, 11, 1)),
    )


def test_decembre_2026_franchit_l_annee():
    plage = plage_mois("2026-12")
    assert plage.debut == D(2026, 11, 30)
    assert plage.fin == D(2027, 1, 3)
    assert plage.fenetres == (
        (D(2026, 11, 30), D(2026, 12, 30)),
        (D(2026, 12, 31), D(2027, 1, 3)),
    )


def test_aout_2026_couvre_six_semaines():
    plage = plage_mois("2026-08")
    assert (plage.fin - plage.debut).days + 1 == 42
    assert plage.fenetres == (
        (D(2026, 7, 27), D(2026, 8, 26)),
        (D(2026, 8, 27), D(2026, 9, 6)),
    )


@pytest.mark.parametrize("annee", [2025, 2026, 2027, 2028])
def test_tous_les_mois_sont_bien_formes(annee):
    for numero in range(1, 13):
        mois = f"{annee}-{numero:02d}"
        plage = plage_mois(mois)

        assert plage.debut.weekday() == 0, mois
        assert plage.fin.weekday() == 6, mois
        assert (plage.fin - plage.debut).days + 1 in (28, 35, 42), mois
        assert 1 <= len(plage.fenetres) <= 2, mois

        # Fenêtres contiguës, aucune plus longue que le plafond de l'outil.
        assert plage.fenetres[0][0] == plage.debut, mois
        assert plage.fenetres[-1][1] == plage.fin, mois
        for debut, fin in plage.fenetres:
            assert (fin - debut).days + 1 <= FENETRE_MAX_JOURS, mois
        for precedente, suivante in zip(plage.fenetres, plage.fenetres[1:]):
            assert suivante[0] == precedente[1] + datetime.timedelta(days=1), mois


@pytest.mark.parametrize("mois", ["2026-13", "202610", "2026-1", "2026-00", "", "octobre"])
def test_mois_mal_forme_refuse(mois):
    with pytest.raises(ValueError):
        plage_mois(mois)


@pytest.mark.parametrize(
    "debut, fin, attendu",
    [
        (D(2026, 9, 28), D(2026, 10, 28), "2026-10"),
        (D(2026, 10, 29), D(2026, 11, 1), "2026-10"),
        (D(2026, 8, 27), D(2026, 9, 6), "2026-08"),
        # Seconde fenêtre de mars 2027, bien qu'entièrement en avril.
        (D(2027, 4, 1), D(2027, 4, 4), "2027-03"),
        (D(2028, 1, 31), D(2028, 3, 1), "2028-02"),
        # Fenêtre quelconque : repli sur le mois le mieux représenté.
        (D(2026, 10, 5), D(2026, 10, 9), "2026-10"),
        # Égalité parfaite : l'ordre chronologique tranche.
        (D(2026, 9, 29), D(2026, 10, 2), "2026-09"),
    ],
)
def test_mois_de_fenetre(debut, fin, attendu):
    assert mois_de_fenetre(debut, fin) == attendu


@pytest.mark.parametrize("annee", [2025, 2026, 2027, 2028])
def test_chaque_fenetre_retrouve_son_mois(annee):
    """Toute fenêtre produite par `plage_mois` est reconnue comme sienne."""
    for numero in range(1, 13):
        mois = f"{annee}-{numero:02d}"
        for debut, fin in plage_mois(mois).fenetres:
            assert mois_de_fenetre(debut, fin) == mois


def test_mois_voisins():
    assert mois_precedent("2026-01") == "2025-12"
    assert mois_precedent("2026-10") == "2026-09"
    assert mois_suivant("2026-12") == "2027-01"
    assert mois_suivant("2026-09") == "2026-10"


def test_libelle_en_francais():
    assert libelle_mois("2026-10") == "octobre 2026"
    assert libelle_mois("2026-08") == "août 2026"
