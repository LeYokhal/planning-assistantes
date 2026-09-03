"""Recette de la rétention : échéances, rattrapage et purge.

Décision F : sans réglage, rien ne se passe et rien n'est perdu.
"""

import datetime

import pytest
from django.core.management import call_command

from absences import services
from absences.models import AbsenceSalariee
from absences.tests import fabrique
from audit.models import EvenementAudit

pytestmark = pytest.mark.django_db

DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)


def _sortie(capsys, *args, **options):
    call_command(*args, **options)
    return capsys.readouterr().out


# --- Réglage absent ---------------------------------------------------------


def test_sans_reglage_aucune_echeance_posee(principale, settings):
    settings.RETENTION_ABSENCES_JOURS = ""
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)

    services.decider(absence, True, principale)

    absence.refresh_from_db()
    assert absence.a_effacer_le is None


def test_sans_reglage_la_purge_ne_fait_rien_et_le_dit(capsys, settings, principale):
    settings.RETENTION_ABSENCES_JOURS = ""
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)

    sortie = _sortie(capsys, "purger_absences")

    assert "aucune purge" in sortie
    assert AbsenceSalariee.objects.count() == 1


def test_reglage_illisible_traite_comme_absent(settings):
    settings.RETENTION_ABSENCES_JOURS = "beaucoup"
    assert services._retention_jours() is None


def test_reglage_zero_traite_comme_absent(settings):
    settings.RETENTION_ABSENCES_JOURS = "0"
    assert services._retention_jours() is None


# --- Réglage présent --------------------------------------------------------


def test_echeance_posee_a_la_validation(principale, settings):
    settings.RETENTION_ABSENCES_JOURS = "365"
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)

    services.decider(absence, True, principale)

    absence.refresh_from_db()
    assert absence.a_effacer_le is not None


def test_echeance_posee_a_la_declaration(salariee, settings):
    from absences.models import TypeAbsence

    settings.RETENTION_ABSENCES_JOURS = "365"
    personne = fabrique.personne()
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DECLARE)

    absence, _ = services.creer(personne, type_, DEBUT, FIN, salariee)

    assert absence.a_effacer_le is not None


def test_une_demande_en_attente_n_a_pas_d_echeance(settings):
    settings.RETENTION_ABSENCES_JOURS = "365"
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    assert absence.a_effacer_le is None


# --- Rattrapage -------------------------------------------------------------


def test_le_rattrapage_pose_les_echeances_manquantes(capsys, settings, principale):
    """Le réglage apparaît après coup : la purge rattrape le stock."""
    settings.RETENTION_ABSENCES_JOURS = ""
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)
    absence.refresh_from_db()
    assert absence.a_effacer_le is None

    settings.RETENTION_ABSENCES_JOURS = "3650"
    sortie = _sortie(capsys, "purger_absences")

    absence.refresh_from_db()
    assert absence.a_effacer_le == FIN + datetime.timedelta(days=3650)
    assert "1 echeance(s) posee(s)" in sortie


def test_l_echeance_est_comptee_depuis_la_fin_de_l_absence(settings, principale, capsys):
    """Une absence ancienne ne gagne pas une nouvelle vie au rattrapage."""
    settings.RETENTION_ABSENCES_JOURS = "30"
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        datetime.date(2020, 1, 6),
        datetime.date(2020, 1, 10),
        statut=AbsenceSalariee.Statut.VALIDEE,
    )

    _sortie(capsys, "purger_absences")

    assert not AbsenceSalariee.objects.filter(pk=absence.pk).exists()


# --- Purge ------------------------------------------------------------------


def test_purge_des_absences_echues(capsys, settings, principale):
    settings.RETENTION_ABSENCES_JOURS = "30"
    echue = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        datetime.date(2020, 1, 6),
        datetime.date(2020, 1, 10),
        statut=AbsenceSalariee.Statut.VALIDEE,
        a_effacer_le=datetime.date(2020, 2, 10),
    )

    sortie = _sortie(capsys, "purger_absences")

    assert not AbsenceSalariee.objects.filter(pk=echue.pk).exists()
    assert "1 absence(s) purgee(s)" in sortie


def test_purge_journalisee_sans_type(capsys, settings):
    settings.RETENTION_ABSENCES_JOURS = "30"
    fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(libelle="Maladie"),
        datetime.date(2020, 1, 6),
        datetime.date(2020, 1, 10),
        statut=AbsenceSalariee.Statut.VALIDEE,
        a_effacer_le=datetime.date(2020, 2, 10),
    )

    _sortie(capsys, "purger_absences")

    evenement = EvenementAudit.objects.get(action="absence_purgee")
    assert "Maladie" not in str(evenement.details)
    assert evenement.details["absence_id"]


def test_une_absence_non_echue_survit(capsys, settings):
    settings.RETENTION_ABSENCES_JOURS = "3650"
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        DEBUT,
        FIN,
        statut=AbsenceSalariee.Statut.VALIDEE,
        a_effacer_le=datetime.date(2099, 1, 1),
    )

    _sortie(capsys, "purger_absences")

    assert AbsenceSalariee.objects.filter(pk=absence.pk).exists()


def test_mode_a_blanc_n_ecrit_rien(capsys, settings):
    settings.RETENTION_ABSENCES_JOURS = "30"
    absence = fabrique.absence(
        fabrique.personne(),
        fabrique.type_absence(),
        datetime.date(2020, 1, 6),
        datetime.date(2020, 1, 10),
        statut=AbsenceSalariee.Statut.VALIDEE,
        a_effacer_le=datetime.date(2020, 2, 10),
    )

    sortie = _sortie(capsys, "purger_absences", a_blanc=True)

    assert AbsenceSalariee.objects.filter(pk=absence.pk).exists()
    assert "[a blanc]" in sortie


# --- Recalcul ---------------------------------------------------------------


def test_commande_de_recalcul_preserve_les_corrections(capsys, principale):
    from decimal import Decimal

    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)
    services.corriger(absence, Decimal("0.5"), principale)

    sortie = _sortie(capsys, "recalculer_jours_comptes")

    absence.refresh_from_db()
    assert absence.jours_comptes == Decimal("0.5")
    assert "1 correction(s) manuelle(s) preservee(s)" in sortie


def test_commande_de_recalcul_sur_un_mois(capsys, principale):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)

    sortie = _sortie(capsys, "recalculer_jours_comptes", mois="2026-05")

    assert "1 absence(s) recalculee(s)" in sortie


def test_commande_de_recalcul_mois_invalide(capsys):
    call_command("recalculer_jours_comptes", mois="2026-13")
    assert "mois invalide" in capsys.readouterr().err
