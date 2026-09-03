"""Recette du cycle de vie d'une absence : création, décision, correction."""

import datetime
from decimal import Decimal

import pytest

from absences import services
from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique
from audit.models import EvenementAudit
from comptes.models import Personne

pytestmark = pytest.mark.django_db

DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)


# --- Création ---------------------------------------------------------------


def test_type_demande_attend_une_decision(salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DEMANDE)

    absence, _ = services.creer(personne, type_, DEBUT, FIN, salariee)

    assert absence.statut == AbsenceSalariee.Statut.EN_ATTENTE
    assert absence.effective is False
    assert absence.jours_comptes is None


def test_type_declaration_est_effectif_immediatement(salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence(
        libelle="Maladie", categorie=TypeAbsence.Categorie.DECLARE
    )

    absence, _ = services.creer(personne, type_, DEBUT, FIN, salariee)

    assert absence.statut == AbsenceSalariee.Statut.DECLAREE
    assert absence.effective is True
    assert absence.jours_comptes == Decimal("4.0")
    assert absence.jours_comptes_calcules == Decimal("4.0")


def test_creation_refusee_pour_un_praticien(salariee):
    """Décision P : une absence ne porte que sur une salariée."""
    type_ = fabrique.type_absence()

    with pytest.raises(services.ActionImpossible):
        services.creer(fabrique.praticien(), type_, DEBUT, FIN, salariee)


def test_creation_refusee_si_les_dates_sont_inversees(salariee):
    type_ = fabrique.type_absence()

    with pytest.raises(services.ActionImpossible):
        services.creer(fabrique.personne(), type_, FIN, DEBUT, salariee)


def test_creation_journalisee(salariee):
    personne = fabrique.personne()
    type_ = fabrique.type_absence()

    services.creer(personne, type_, DEBUT, FIN, salariee)

    evenement = EvenementAudit.objects.get(action="absence_demandee")
    assert evenement.details["personne_id"] == personne.pk
    assert evenement.details["statut"] == "en_attente"


# --- Décision ---------------------------------------------------------------


def test_validation_pose_les_jours_comptes(principale, salariee):
    personne = fabrique.personne()
    absence = fabrique.absence(personne, fabrique.type_absence(), DEBUT, FIN)

    services.decider(absence, True, principale)

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.VALIDEE
    assert absence.decide_par == principale
    assert absence.decide_le is not None
    assert absence.jours_comptes == Decimal("4.0")


def test_refus_ne_pose_aucun_jour_compte(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)

    services.decider(absence, False, principale)

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.REFUSEE
    assert absence.jours_comptes is None
    assert absence.effective is False


def test_une_absence_deja_decidee_ne_se_redecide_pas(principale):
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        statut=AbsenceSalariee.Statut.VALIDEE,
    )

    with pytest.raises(services.ActionImpossible):
        services.decider(absence, True, principale)


def test_decision_journalisee_sans_type_ni_precision(principale):
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(libelle="Maladie"),
        precision="rendez-vous médical",
    )

    services.decider(absence, True, principale)

    evenement = EvenementAudit.objects.get(action="absence_decidee")
    assert "Maladie" not in str(evenement.details)
    assert "médical" not in str(evenement.details)


# --- Règle K ----------------------------------------------------------------


def test_la_principale_ne_decide_pas_de_sa_propre_absence(principale):
    """Règle K, assise sur la PERSONNE concernée, pas sur l'auteur de la saisie."""
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    absence = fabrique.absence(personne, fabrique.type_absence())

    assert services.peut_decider(absence, principale) is False
    with pytest.raises(services.ActionImpossible):
        services.decider(absence, True, principale)


def test_le_cabinet_tranche_l_absence_de_la_principale(cabinet, principale):
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    absence = fabrique.absence(personne, fabrique.type_absence())

    assert services.peut_decider(absence, cabinet) is True
    services.decider(absence, True, cabinet)
    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.VALIDEE


def test_la_principale_decide_de_l_absence_d_une_autre(principale):
    personne_principale = fabrique.personne(nom="MARTIN", prenom="Bob")
    fabrique.lier(principale, personne_principale)
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())

    assert services.peut_decider(absence, principale) is True


def test_regle_k_sans_personne_liee_laisse_decider(principale):
    """Un compte non rattaché ne peut être la personne concernée."""
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    assert principale.personne_id is None
    assert services.peut_decider(absence, principale) is True


# --- Annulation -------------------------------------------------------------


def test_annulation_d_une_demande_en_attente(salariee):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())

    services.annuler(absence, salariee)

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.ANNULEE
    assert EvenementAudit.objects.filter(action="absence_annulee").exists()


def test_une_absence_validee_ne_s_annule_pas(salariee):
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        statut=AbsenceSalariee.Statut.VALIDEE,
    )

    with pytest.raises(services.ActionImpossible):
        services.annuler(absence, salariee)


# --- Correction (décision O) ------------------------------------------------


def test_correction_a_une_demi_journee(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    services.decider(absence, True, principale)

    services.corriger(absence, Decimal("0.5"), principale)

    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("0.5")
    assert absence.jours_comptes_calcules == Decimal("4.0")
    assert absence.corrigee is True
    assert absence.corrige_par == principale


@pytest.mark.parametrize("valeur", ["0.3", "1.2", "2.7"])
def test_correction_refusee_hors_pas_de_zero_cinq(principale, valeur):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    with pytest.raises(services.ActionImpossible):
        services.corriger(absence, Decimal(valeur), principale)


def test_correction_refusee_si_negative(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    with pytest.raises(services.ActionImpossible):
        services.corriger(absence, Decimal("-1"), principale)


def test_correction_refusee_au_dela_de_la_duree(principale):
    """La plage du 26 au 30 mai fait 5 jours : 6 est refusé."""
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    with pytest.raises(services.ActionImpossible):
        services.corriger(absence, Decimal("6"), principale)


def test_correction_acceptee_a_la_borne(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.corriger(absence, Decimal("5"), principale)
    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("5.0")


def test_correction_journalisee_sans_type(principale):
    absence = fabrique.absence(
        fabrique.personne(), fabrique.type_absence(libelle="Maladie")
    )
    services.corriger(absence, Decimal("1"), principale)

    evenement = EvenementAudit.objects.get(action="absence_corrigee")
    assert "Maladie" not in str(evenement.details)
    assert evenement.details["retenus"] == "1.0"


# --- Recalcul ---------------------------------------------------------------


def test_le_recalcul_ne_touche_pas_une_absence_corrigee(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)
    services.corriger(absence, Decimal("0.5"), principale)

    services.recalculer(absence)

    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("0.5")
    assert absence.jours_comptes_calcules == Decimal("4.0")


def test_le_recalcul_met_a_jour_une_absence_non_corrigee(principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)
    AbsenceSalariee.objects.filter(pk=absence.pk).update(
        jours_comptes=Decimal("9.0"), jours_comptes_calcules=Decimal("9.0")
    )
    absence.refresh_from_db()

    services.recalculer(absence)

    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("4.0")


def test_le_recalcul_ignore_une_absence_non_effective():
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    assert services.recalculer(absence) is False


# --- Contrat incomplet (décision N) -----------------------------------------


def test_contrat_incomplet_signale_sans_bloquer(principale):
    personne = fabrique.personne(heures_hebdo=None, jours_fixes=[])
    absence = fabrique.absence(personne, fabrique.type_absence(), DEBUT, FIN)

    signal = services.decider(absence, True, principale)

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.VALIDEE
    assert absence.jours_comptes == Decimal("0.0")
    assert signal == "sans_contrat"


def test_une_secretaire_a_jours_fixes_n_est_pas_incomplete(principale):
    personne = fabrique.personne(
        role_metier=Personne.RoleMetier.SECRETAIRE,
        heures_hebdo=None,
        jours_fixes=["Mardi", "Jeudi"],
    )
    absence = fabrique.absence(personne, fabrique.type_absence(), DEBUT, FIN)

    signal = services.decider(absence, True, principale)

    assert signal == ""
    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("2.0")
