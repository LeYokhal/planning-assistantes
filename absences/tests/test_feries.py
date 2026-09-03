"""Recette du calendrier des jours fériés."""

import datetime

import pytest

from socle import feries


@pytest.mark.parametrize(
    "annee, attendu",
    [
        (2024, datetime.date(2024, 3, 31)),
        (2025, datetime.date(2025, 4, 20)),
        (2026, datetime.date(2026, 4, 5)),
        (2027, datetime.date(2027, 3, 28)),
        (2038, datetime.date(2038, 4, 25)),
    ],
)
def test_paques(annee, attendu):
    """Dates de Pâques connues, dont une année bissextile (2024)."""
    assert feries.paques(annee) == attendu


def test_onze_feries_par_an():
    assert len(feries.feries_annee(2026)) == 11


@pytest.mark.parametrize(
    "jour",
    [
        datetime.date(2026, 1, 1),
        datetime.date(2026, 5, 1),
        datetime.date(2026, 5, 8),
        datetime.date(2026, 7, 14),
        datetime.date(2026, 8, 15),
        datetime.date(2026, 11, 1),
        datetime.date(2026, 11, 11),
        datetime.date(2026, 12, 25),
    ],
)
def test_feries_fixes(jour):
    assert feries.est_ferie(jour)


def test_feries_mobiles_2026():
    """Les trois mobiles de 2026, tous adossés à Pâques du 5 avril."""
    assert feries.est_ferie(datetime.date(2026, 4, 6))   # lundi de Pâques
    assert feries.est_ferie(datetime.date(2026, 5, 14))  # Ascension
    assert feries.est_ferie(datetime.date(2026, 5, 25))  # lundi de Pentecôte


def test_jour_ordinaire_non_ferie():
    assert not feries.est_ferie(datetime.date(2026, 5, 26))


def test_annee_bissextile_29_fevrier_non_ferie():
    assert not feries.est_ferie(datetime.date(2024, 2, 29))


def test_nom_ferie():
    assert feries.nom_ferie(datetime.date(2026, 12, 25)) == "Noël"
    assert feries.nom_ferie(datetime.date(2026, 12, 24)) == ""


def test_feries_entre_traverse_deux_annees():
    trouves = feries.feries_entre(
        datetime.date(2026, 12, 20), datetime.date(2027, 1, 5)
    )
    assert set(trouves) == {
        datetime.date(2026, 12, 25),
        datetime.date(2027, 1, 1),
    }
