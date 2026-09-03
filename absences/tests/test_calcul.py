"""Recette du calcul des jours comptés.

Les trois cas datés viennent de la revue technique de Phase 2 : ce sont eux qui
ont fait tomber la formule de la v2, et ils sont ici nommément.

Régime d'origine : mardi → samedi. À partir du lundi 5 octobre 2026 :
lundi → vendredi. Contrat 39 h et 35 h → 4 briques, 27 h → 3.
"""

import datetime
from decimal import Decimal

import pytest

from absences import calcul
from absences.tests import fabrique
from comptes.models import Personne

pytestmark = pytest.mark.django_db

REGLES = None


@pytest.fixture(autouse=True)
def regles_fictives():
    """Règles fabriquées : les tests ne dépendent pas du fichier du dépôt."""
    global REGLES
    REGLES = fabrique.regles()
    yield
    REGLES = None


def compter(personne, debut, fin):
    return calcul.jours_comptes(personne, debut, fin, regles=REGLES).jours


# --- Les trois cas datés de la revue ----------------------------------------


def test_lundi_de_paques_2026_ne_retire_rien_car_le_lundi_est_ferme():
    """06/04/2026 est férié un LUNDI, jour fermé sous le régime mardi→samedi.

    La v2 déduisait ce férié de `B` sans vérifier l'ouverture : elle rendait 3
    au lieu de 4, un jour de paie perdu.
    """
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 4, 7), datetime.date(2026, 4, 11))
    assert jours == Decimal("4.0")


def test_lundi_de_pentecote_2026_ne_retire_rien_non_plus():
    """25/05/2026, même défaut de la v2, même correction."""
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("4.0")


def test_ascension_2026_seule_ne_compte_aucun_jour():
    """14/05/2026 est férié un JEUDI, jour ouvert : il ne se compte pas.

    La v2 le comptait dans `J` tout en le réservant dans `F` — le même jour
    deux fois.
    """
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 14), datetime.date(2026, 5, 14))
    assert jours == Decimal("0.0")


def test_semaine_de_l_ascension_plafonnee_par_le_ferie():
    """Mardi→samedi de la semaine de l'Ascension : J = 4, B − F = 3 → 3."""
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 12), datetime.date(2026, 5, 16))
    assert jours == Decimal("3.0")


# --- Bascule du 5 octobre 2026 ----------------------------------------------


def test_avant_la_bascule_le_lundi_ne_compte_pas():
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 9, 28), datetime.date(2026, 10, 2))
    assert jours == Decimal("4.0")


def test_apres_la_bascule_le_lundi_compte():
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 10, 5), datetime.date(2026, 10, 9))
    assert jours == Decimal("4.0")


def test_apres_la_bascule_le_samedi_ne_compte_plus():
    """Samedi 10/10/2026 : fermé sous le nouveau régime."""
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 10, 10), datetime.date(2026, 10, 10))
    assert jours == Decimal("0.0")


def test_avant_la_bascule_le_samedi_compte():
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 10, 3), datetime.date(2026, 10, 3))
    assert jours == Decimal("1.0")


def test_aucune_semaine_a_cheval_sur_deux_regimes():
    """La bascule tombe un lundi : la semaine du 5 octobre est homogène."""
    personne = fabrique.personne(heures_hebdo=39)
    avant = compter(personne, datetime.date(2026, 9, 28), datetime.date(2026, 10, 4))
    apres = compter(personne, datetime.date(2026, 10, 5), datetime.date(2026, 10, 11))
    assert avant == Decimal("4.0")
    assert apres == Decimal("4.0")


# --- Plafond du gabarit -----------------------------------------------------


def test_contrat_27h_plafonne_a_trois_briques():
    personne = fabrique.personne(heures_hebdo=27)
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("3.0")


def test_contrat_35h_plafonne_a_quatre_briques():
    personne = fabrique.personne(heures_hebdo=35)
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("4.0")


def test_absence_d_un_seul_jour_ouvert():
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 26))
    assert jours == Decimal("1.0")


def test_dimanche_seul_ne_compte_rien():
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 31), datetime.date(2026, 5, 31))
    assert jours == Decimal("0.0")


# --- Plusieurs semaines -----------------------------------------------------


def test_absence_sur_deux_semaines_pleines():
    """Deux semaines sans férié : 4 + 4."""
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 6, 1), datetime.date(2026, 6, 14))
    assert jours == Decimal("8.0")


def test_absence_sur_trois_semaines_dont_deux_feriees():
    """Trois semaines de mai 2026, deux d'entre elles fériées un jour ouvert.

    Semaine du 4 : vendredi 8 (Victoire 1945) → J = 4, B − F = 3 → 3.
    Semaine du 11 : jeudi 14 (Ascension) → 3.
    Semaine du 18 : aucun férié → J = 5, B = 4 → 4.
    """
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 5, 4), datetime.date(2026, 5, 24))
    assert jours == Decimal("10.0")


def test_absence_a_cheval_sur_deux_semaines():
    """Jeudi 4 juin au mardi 9 juin 2026, régime mardi→samedi.

    Semaine 1 : jeudi, vendredi, samedi ouverts (dimanche fermé) → 3.
    Semaine 2 : lundi fermé, mardi ouvert → 1.
    """
    personne = fabrique.personne(heures_hebdo=39)
    jours = compter(personne, datetime.date(2026, 6, 4), datetime.date(2026, 6, 9))
    assert jours == Decimal("4.0")


# --- Branche « jours fixes » ------------------------------------------------


def test_jours_fixes_comptes_hors_feries():
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Mardi", "Jeudi"],
    )
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("2.0")


def test_jours_fixes_un_ferie_ne_compte_pas():
    """Jeudi de l'Ascension : la secrétaire y travaille normalement, pas ce jour-là."""
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Mardi", "Jeudi"],
    )
    jours = compter(personne, datetime.date(2026, 5, 12), datetime.date(2026, 5, 16))
    assert jours == Decimal("1.0")


def test_jours_fixes_ignorent_une_valeur_illisible():
    """`jours_fixes` est un JSONField : une entrée fantaisiste ne casse rien."""
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Mardi", "Lundu", 42, None],
    )
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("1.0")


def test_jours_fixes_ne_dependent_pas_des_periodes_d_ouverture():
    """Une secrétaire à jours fixes le samedi les garde après la bascule."""
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Samedi"],
    )
    jours = compter(personne, datetime.date(2026, 10, 10), datetime.date(2026, 10, 10))
    assert jours == Decimal("1.0")


# --- Contrat incomplet (décision N) -----------------------------------------


def test_sans_heures_ni_jours_fixes_rend_zero_et_signale():
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    resultat = calcul.jours_comptes(
        personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), regles=REGLES
    )
    assert resultat.jours == Decimal("0.0")
    assert resultat.signal == calcul.SIGNAL_SANS_CONTRAT
    assert resultat.message


def test_heures_hors_gabarits_rend_zero_et_signale():
    personne = fabrique.personne(heures_hebdo=42)
    resultat = calcul.jours_comptes(
        personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), regles=REGLES
    )
    assert resultat.jours == Decimal("0.0")
    assert resultat.signal == calcul.SIGNAL_HEURES_HORS_GABARITS


def test_contrat_incomplet_ne_leve_pas():
    """Décision N : rien n'est bloqué, la validatrice corrigera."""
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    assert compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30)) == Decimal("0.0")


def test_signal_vide_quand_le_contrat_est_complet():
    personne = fabrique.personne(heures_hebdo=39)
    resultat = calcul.jours_comptes(
        personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), regles=REGLES
    )
    assert resultat.signal == ""
    assert resultat.message == ""


def test_les_heures_priment_sur_les_jours_fixes():
    """Ordre repris de `personnes/services.py:_avertir_heures`."""
    personne = fabrique.personne(heures_hebdo=27, jours_fixes=["Mardi"])
    jours = compter(personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    assert jours == Decimal("3.0")


# --- Décision P -------------------------------------------------------------


def test_est_salariee_refuse_un_praticien():
    assert not calcul.est_salariee(fabrique.praticien())


def test_est_salariee_accepte_assistante_et_secretaire():
    assert calcul.est_salariee(fabrique.personne())
    assert calcul.est_salariee(
        fabrique.personne(
            nom="MARTIN", prenom="Bob", role_metier=Personne.RoleMetier.SECRETAIRE
        )
    )
