"""Recette de la répartition d'une absence entre les mois de paie.

C'est le trou trouvé au checkpoint diff : la paie filtrait sur des semaines
complètes et versait une absence à cheval **entière dans chacun des deux mois**.
Ces tests ferment les deux défauts, et gardent la porte fermée.

Le cas nommé `test_le_piege_du_recoupement` est celui qui condamne l'option
écartée le 01/09 : recouper l'absence puis relancer le calcul sur les morceaux
appliquerait le plafond hebdomadaire deux fois.
"""

import datetime
from decimal import Decimal

import pytest

from absences import calcul, paie, services
from absences.models import AbsenceSalariee
from absences.tests import fabrique

pytestmark = pytest.mark.django_db

# Lundi 28 septembre → vendredi 2 octobre 2026 : une semaine à cheval, sous le
# régime d'origine mardi→samedi (la bascule est au 5 octobre).
CHEVAL_DEBUT = datetime.date(2026, 9, 28)
CHEVAL_FIN = datetime.date(2026, 10, 2)


def _validee(personne, debut=CHEVAL_DEBUT, fin=CHEVAL_FIN, principale=None):
    absence = fabrique.absence(personne, fabrique.type_absence(paie=True), debut, fin)
    services.decider(absence, True, principale)
    absence.refresh_from_db()
    return absence


def _facture(mois):
    donnees = paie.donnees_du_mois(mois, paie.plage_calendaire(mois))
    if not donnees["salariees"]:
        return Decimal("0.0")
    return Decimal(donnees["salariees"][0]["jours_comptes"])


# --- Plage calendaire -------------------------------------------------------


def test_la_plage_est_le_mois_calendaire():
    assert paie.plage_calendaire("2026-10") == (
        datetime.date(2026, 10, 1),
        datetime.date(2026, 10, 31),
    )
    assert paie.plage_calendaire("2026-02") == (
        datetime.date(2026, 2, 1),
        datetime.date(2026, 2, 28),
    )


def test_annee_bissextile():
    assert paie.plage_calendaire("2024-02")[1] == datetime.date(2024, 2, 29)


@pytest.mark.parametrize("mois", ["2026-13", "202610", "octobre", "", None])
def test_mois_invalide_leve(mois):
    with pytest.raises(ValueError):
        paie.plage_calendaire(mois)


def test_deux_mois_consecutifs_ne_se_recouvrent_pas():
    """Le défaut 9.3 : `plage_mois` recouvrait sept jours, plus la calendaire."""
    _, fin_septembre = paie.plage_calendaire("2026-09")
    debut_octobre, _ = paie.plage_calendaire("2026-10")
    assert fin_septembre < debut_octobre


def test_une_absence_de_fin_septembre_n_est_pas_dans_la_paie_d_octobre(principale):
    """Le défaut 9.3, de bout en bout."""
    personne = fabrique.personne(heures_hebdo=39)
    _validee(
        personne,
        datetime.date(2026, 9, 29),
        datetime.date(2026, 9, 30),
        principale=principale,
    )

    assert _facture("2026-10") == Decimal("0.0")
    assert _facture("2026-09") == Decimal("2.0")


# --- Répartition d'une absence à cheval -------------------------------------


def test_la_somme_des_portions_vaut_les_jours_comptes(principale):
    """Le défaut 9.4 : plus de double-compte."""
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)

    septembre = _facture("2026-09")
    octobre = _facture("2026-10")

    assert absence.jours_comptes == Decimal("4.0")
    assert septembre + octobre == absence.jours_comptes


def test_chaque_mois_recoit_sa_part(principale):
    """28-30 septembre ouvrés = mardi, mercredi ; 1-2 octobre = jeudi, vendredi."""
    personne = fabrique.personne(heures_hebdo=39)
    _validee(personne, principale=principale)

    assert _facture("2026-09") == Decimal("2.0")
    assert _facture("2026-10") == Decimal("2.0")


def test_le_piege_du_recoupement(principale):
    """Le cas qui condamne l'option écartée.

    Salariée à 27 h → B = 3. Semaine entière à cheval, régime mardi→samedi :
    J = 5 jours ouvrés, plafond 3, donc **3 jours** pour l'absence entière.
    Recouper en 2 + 3 jours ouvrables donnerait min(2,3) + min(3,3) = 5.
    """
    personne = fabrique.personne(heures_hebdo=27)
    absence = _validee(personne, principale=principale)

    assert absence.jours_comptes == Decimal("3.0")
    somme = _facture("2026-09") + _facture("2026-10")
    assert somme == Decimal("3.0"), "le plafond hebdomadaire a été appliqué deux fois"


def test_les_premiers_jours_de_la_semaine_sont_retenus(principale):
    """Le plafond retient les premiers jours : 28 et 29 septembre, puis le 1er."""
    personne = fabrique.personne(heures_hebdo=27)
    absence = _validee(personne, principale=principale)

    assert absence.jours_retenus == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert _facture("2026-09") == Decimal("2.0")
    assert _facture("2026-10") == Decimal("1.0")


# --- Absence corrigée -------------------------------------------------------


def test_absence_a_cheval_corrigee_la_somme_vaut_la_correction(principale):
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)
    services.corriger(absence, Decimal("3"), principale)

    somme = _facture("2026-09") + _facture("2026-10")
    assert somme == Decimal("3.0")


def test_correction_a_une_demi_journee_repartie_sans_perte(principale):
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)
    services.corriger(absence, Decimal("2.5"), principale)

    assert _facture("2026-09") + _facture("2026-10") == Decimal("2.5")


def test_le_reste_va_au_mois_du_premier_jour_retenu(principale):
    """2,5 réparti sur 2 + 2 jours : 1,0 et 1,0 au prorata, reste 0,5 à septembre."""
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)
    services.corriger(absence, Decimal("2.5"), principale)

    assert _facture("2026-09") == Decimal("1.5")
    assert _facture("2026-10") == Decimal("1.0")


def test_correction_sans_jours_retenus_va_au_mois_de_debut(principale):
    """Contrat incomplet corrigé à la main : rien sur quoi répartir."""
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    absence = _validee(personne, principale=principale)
    assert absence.jours_retenus == []
    services.corriger(absence, Decimal("4"), principale)

    assert _facture("2026-09") == Decimal("4.0")
    assert _facture("2026-10") == Decimal("0.0")


def test_correction_sans_jours_retenus_pose_le_drapeau(principale):
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    absence = _validee(personne, principale=principale)
    services.corriger(absence, Decimal("4"), principale)

    donnees = paie.donnees_du_mois("2026-09", paie.plage_calendaire("2026-09"))
    detail = donnees["salariees"][0]["absences"][0]
    assert detail["repartition_calculee"] is False
    assert "répartition entre mois non calculable" in donnees["paragraphe"]


def test_le_drapeau_est_absent_quand_la_repartition_se_fait(principale):
    personne = fabrique.personne(heures_hebdo=39)
    _validee(personne, principale=principale)

    donnees = paie.donnees_du_mois("2026-09", paie.plage_calendaire("2026-09"))
    detail = donnees["salariees"][0]["absences"][0]
    assert detail["repartition_calculee"] is True
    assert "non calculable" not in donnees["paragraphe"]


# --- Détail exposé à la comptable -------------------------------------------


def test_le_detail_expose_la_portion_et_le_total(principale):
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)

    detail = paie.donnees_du_mois("2026-09", paie.plage_calendaire("2026-09"))[
        "salariees"
    ][0]["absences"][0]

    assert detail["jours_comptes"] == "2.0"
    assert detail["jours_comptes_absence"] == "4.0"
    assert detail["a_cheval"] is True
    assert detail["absence_id"] == absence.pk


def test_une_absence_entierement_dans_le_mois_n_est_pas_a_cheval(principale):
    personne = fabrique.personne(heures_hebdo=39)
    _validee(
        personne,
        datetime.date(2026, 10, 6),
        datetime.date(2026, 10, 9),
        principale=principale,
    )

    detail = paie.donnees_du_mois("2026-10", paie.plage_calendaire("2026-10"))[
        "salariees"
    ][0]["absences"][0]
    assert detail["a_cheval"] is False


# --- Invariant du calcul ----------------------------------------------------


def test_invariant_contrat_horaire():
    """`jours == len(dates)` sur la branche contrat."""
    regles = fabrique.regles()
    personne = fabrique.personne(heures_hebdo=39)
    resultat = calcul.jours_comptes(personne, CHEVAL_DEBUT, CHEVAL_FIN, regles=regles)
    assert resultat.jours == Decimal(len(resultat.dates))


def test_invariant_jours_fixes():
    """`jours == len(dates)` sur la branche jours fixes."""
    from comptes.models import Personne

    regles = fabrique.regles()
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Mardi", "Jeudi"],
    )
    resultat = calcul.jours_comptes(
        personne, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30), regles=regles
    )
    assert resultat.jours == Decimal(len(resultat.dates))


def test_invariant_contrat_incomplet():
    regles = fabrique.regles()
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    resultat = calcul.jours_comptes(personne, CHEVAL_DEBUT, CHEVAL_FIN, regles=regles)
    assert resultat.jours == Decimal("0.0")
    assert resultat.dates == ()


def test_les_dates_sont_ordonnees_et_dans_la_plage():
    regles = fabrique.regles()
    personne = fabrique.personne(heures_hebdo=39)
    dates = calcul.jours_comptes(
        personne, datetime.date(2026, 5, 4), datetime.date(2026, 5, 24), regles=regles
    ).dates
    assert list(dates) == sorted(dates)
    assert all(datetime.date(2026, 5, 4) <= d <= datetime.date(2026, 5, 24) for d in dates)


def test_jours_retenus_stockes_a_la_validation(principale):
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)
    assert absence.jours_retenus == [
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
    ]


def test_le_recalcul_rafraichit_les_dates(principale):
    personne = fabrique.personne(heures_hebdo=39)
    absence = _validee(personne, principale=principale)
    AbsenceSalariee.objects.filter(pk=absence.pk).update(jours_retenus=[])
    absence.refresh_from_db()

    services.recalculer(absence)

    absence.refresh_from_db()
    assert len(absence.jours_retenus) == 4


# --- Décision P côté écriture -----------------------------------------------


def test_decider_refuse_un_praticien(principale):
    """La garde ajoutée dans `services.decider`."""
    absence = fabrique.absence(
        fabrique.praticien(), fabrique.type_absence(), CHEVAL_DEBUT, CHEVAL_FIN
    )
    with pytest.raises(services.ActionImpossible):
        services.decider(absence, True, principale)


def test_l_admin_refuse_un_praticien_au_formulaire():
    from absences.admin import FormulaireAbsenceAdmin

    praticien = fabrique.praticien()
    formulaire = FormulaireAbsenceAdmin(
        {
            "personne": praticien.pk,
            "type": fabrique.type_absence().pk,
            "date_debut": "2026-09-28",
            "date_fin": "2026-10-02",
            "statut": AbsenceSalariee.Statut.EN_ATTENTE,
            "precision": "",
            "jours_retenus": "[]",
        }
    )
    assert not formulaire.is_valid()
    assert "personne" in formulaire.errors


def test_l_admin_refuse_un_praticien_dans_save_model(cabinet):
    """Le dernier rempart, pour les chemins qui contourneraient le formulaire."""
    from django.contrib.admin.sites import AdminSite

    from absences.admin import AbsenceSalarieeAdmin

    class Requete:
        user = cabinet

    absence = AbsenceSalariee(
        personne=fabrique.praticien(),
        type=fabrique.type_absence(),
        date_debut=CHEVAL_DEBUT,
        date_fin=CHEVAL_FIN,
        statut=AbsenceSalariee.Statut.EN_ATTENTE,
    )
    administration = AbsenceSalarieeAdmin(AbsenceSalariee, AdminSite())

    with pytest.raises(services.ActionImpossible):
        administration.save_model(Requete(), absence, None, change=False)


def test_l_admin_accepte_une_salariee(cabinet):
    from django.contrib.admin.sites import AdminSite

    from absences.admin import AbsenceSalarieeAdmin

    class Requete:
        user = cabinet

    absence = AbsenceSalariee(
        personne=fabrique.personne(),
        type=fabrique.type_absence(),
        date_debut=CHEVAL_DEBUT,
        date_fin=CHEVAL_FIN,
        statut=AbsenceSalariee.Statut.VALIDEE,
    )
    administration = AbsenceSalarieeAdmin(AbsenceSalariee, AdminSite())
    administration.save_model(Requete(), absence, None, change=False)

    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("4.0")
    assert len(absence.jours_retenus) == 4
