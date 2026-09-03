"""Recette des périodes d'ouverture du cabinet (§ 4.1 du plan).

Le fichier réel du dépôt est vérifié tel quel ; toutes les variantes fautives
sont fabriquées dans un fichier temporaire, jamais en modifiant le vrai — même
convention que `test_chargeur.py`.
"""

import datetime
import json

import pytest
from django.core.exceptions import ImproperlyConfigured

from regles import chargeur
from regles.tests.test_chargeur import BASE

pytestmark = []


@pytest.fixture(autouse=True)
def cache_vierge():
    chargeur._CACHE.clear()
    yield
    chargeur._CACHE.clear()


def ecrire(tmp_path, contenu, nom="regles.json"):
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return chemin


def avec_periodes(periodes):
    fautif = dict(BASE)
    fautif["periodes_ouverture"] = {"liste": periodes}
    return fautif


# --- Fichier réel -----------------------------------------------------------


def test_le_fichier_du_depot_porte_deux_periodes():
    regles = chargeur.charger()
    assert len(regles.periodes_ouverture) == 2
    assert regles.periodes_ouverture[0].a_partir_du is None
    assert regles.periodes_ouverture[1].a_partir_du == datetime.date(2026, 10, 5)


def test_la_bascule_tombe_un_lundi():
    """Aucune semaine ne doit être à cheval sur deux régimes."""
    bascule = chargeur.charger().periodes_ouverture[1].a_partir_du
    assert bascule.weekday() == 0


def test_les_jours_du_fichier_reel_sont_canoniques():
    for periode in chargeur.charger().periodes_ouverture:
        for jour in periode.jours:
            assert jour in (
                "Lundi",
                "Mardi",
                "Mercredi",
                "Jeudi",
                "Vendredi",
                "Samedi",
                "Dimanche",
            )


# --- Recherche de la période applicable -------------------------------------


@pytest.mark.parametrize(
    "jour, attendu_lundi",
    [
        (datetime.date(2026, 9, 30), False),
        (datetime.date(2026, 10, 4), False),
        (datetime.date(2026, 10, 5), True),
        (datetime.date(2027, 6, 1), True),
        (datetime.date(2020, 1, 1), False),
    ],
)
def test_periode_applicable(jour, attendu_lundi):
    jours = chargeur.jours_ouverture(jour)
    assert ("Lundi" in jours) is attendu_lundi
    assert ("Samedi" in jours) is not attendu_lundi


def test_la_periode_d_origine_couvre_le_passe_lointain():
    """La première période est sans date : aucune date n'est orpheline."""
    assert chargeur.jours_ouverture(datetime.date(1990, 1, 1))


# --- Validation -------------------------------------------------------------


def test_section_absente_refusee(tmp_path):
    fautif = dict(BASE)
    del fautif["periodes_ouverture"]
    with pytest.raises(ImproperlyConfigured, match="aucune période d'ouverture"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_liste_vide_refusee(tmp_path):
    with pytest.raises(ImproperlyConfigured, match="aucune période d'ouverture"):
        chargeur.charger(ecrire(tmp_path, avec_periodes([])))


def test_premiere_periode_datee_refusee(tmp_path):
    fautif = avec_periodes(
        [{"a_partir_du": "2026-01-01", "jours": ["Mardi"]}]
    )
    with pytest.raises(ImproperlyConfigured, match="origine"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_dates_decroissantes_refusees(tmp_path):
    fautif = avec_periodes(
        [
            {"a_partir_du": None, "jours": ["Mardi"]},
            {"a_partir_du": "2026-10-05", "jours": ["Lundi"]},
            {"a_partir_du": "2026-01-01", "jours": ["Mardi"]},
        ]
    )
    with pytest.raises(ImproperlyConfigured, match="strictement croissantes"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_dates_egales_refusees(tmp_path):
    fautif = avec_periodes(
        [
            {"a_partir_du": None, "jours": ["Mardi"]},
            {"a_partir_du": "2026-10-05", "jours": ["Lundi"]},
            {"a_partir_du": "2026-10-05", "jours": ["Mardi"]},
        ]
    )
    with pytest.raises(ImproperlyConfigured, match="strictement croissantes"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_date_illisible_refusee(tmp_path):
    fautif = avec_periodes(
        [
            {"a_partir_du": None, "jours": ["Mardi"]},
            {"a_partir_du": "5 octobre 2026", "jours": ["Lundi"]},
        ]
    )
    with pytest.raises(ImproperlyConfigured, match="AAAA-MM-JJ"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_jour_inconnu_refuse(tmp_path):
    fautif = avec_periodes([{"a_partir_du": None, "jours": ["Lundu"]}])
    with pytest.raises(ImproperlyConfigured, match="inconnu"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_jour_en_double_refuse(tmp_path):
    fautif = avec_periodes([{"a_partir_du": None, "jours": ["Mardi", "mardi"]}])
    with pytest.raises(ImproperlyConfigured, match="en double"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_jours_vides_refuses(tmp_path):
    fautif = avec_periodes([{"a_partir_du": None, "jours": []}])
    with pytest.raises(ImproperlyConfigured, match="liste non vide"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_entree_qui_n_est_pas_un_objet_refusee(tmp_path):
    fautif = avec_periodes(["mardi"])
    with pytest.raises(ImproperlyConfigured, match="n'est pas un objet"):
        chargeur.charger(ecrire(tmp_path, fautif))


def test_jours_en_casse_libre_acceptes(tmp_path):
    """« mardi » et « MARDI » valent « Mardi » : `jour_canonique` normalise."""
    valide = avec_periodes([{"a_partir_du": None, "jours": ["mardi", "MERCREDI"]}])
    regles = chargeur.charger(ecrire(tmp_path, valide))
    assert regles.periodes_ouverture[0].jours == ("Mardi", "Mercredi")


def test_cle_doc_ignoree(tmp_path):
    valide = dict(BASE)
    valide["periodes_ouverture"] = {
        "_doc": "documentation",
        "liste": [{"a_partir_du": None, "jours": ["Mardi"]}],
    }
    regles = chargeur.charger(ecrire(tmp_path, valide))
    assert len(regles.periodes_ouverture) == 1
