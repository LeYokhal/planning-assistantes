"""Recette du verrou d'import et de la reprise après interruption."""

import datetime
import uuid

import pytest
from django.utils import timezone

from presences import verrou
from presences.models import ImportPresences, VerrouImport

pytestmark = pytest.mark.django_db


def _vieillir(minutes):
    """Fait reculer la prise du verrou de `minutes` (auto_now_add oblige)."""
    VerrouImport.objects.filter(cle=verrou.CLE).update(
        pris_le=timezone.now() - datetime.timedelta(minutes=minutes)
    )


def test_prise_et_liberation():
    prise = verrou.prendre("endpoint 2026-10", uuid.uuid4())

    assert prise is not None
    assert prise.cle == verrou.CLE
    assert verrou.actif() is not None

    verrou.liberer(prise)
    assert verrou.actif() is None
    assert verrou.prendre("endpoint 2026-11", uuid.uuid4()) is not None


def test_second_appel_refuse():
    assert verrou.prendre("premier", uuid.uuid4()) is not None
    assert verrou.prendre("second", uuid.uuid4()) is None


def test_verrou_recent_non_repris():
    verrou.prendre("premier", uuid.uuid4())
    _vieillir(5)
    assert verrou.prendre("second", uuid.uuid4()) is None


def test_verrou_perime_repris_et_lignes_requalifiees():
    verrou.prendre("premier", uuid.uuid4())
    _vieillir(20)

    ligne = ImportPresences.objects.create(
        source=ImportPresences.Source.ENDPOINT,
        statut=ImportPresences.Statut.EN_COURS,
        mois="2026-10",
    )
    ImportPresences.objects.filter(pk=ligne.pk).update(
        importe_le=timezone.now() - datetime.timedelta(minutes=20)
    )

    prise = verrou.prendre("second", uuid.uuid4())

    assert prise is not None
    assert VerrouImport.objects.count() == 1
    ligne.refresh_from_db()
    assert ligne.statut == ImportPresences.Statut.ECHEC
    assert ligne.erreur == "interrompu (délai dépassé)"
    assert ligne.termine_le is not None


def test_ligne_en_cours_recente_epargnee():
    verrou.prendre("premier", uuid.uuid4())
    _vieillir(20)
    ligne = ImportPresences.objects.create(
        source=ImportPresences.Source.ENDPOINT,
        statut=ImportPresences.Statut.EN_COURS,
    )

    verrou.prendre("second", uuid.uuid4())

    ligne.refresh_from_db()
    assert ligne.statut == ImportPresences.Statut.EN_COURS


def test_actif_ignore_un_verrou_perime():
    verrou.prendre("premier", uuid.uuid4())
    _vieillir(20)
    assert verrou.actif() is None


def test_liberer_sur_verrou_deja_disparu():
    prise = verrou.prendre("premier", uuid.uuid4())
    VerrouImport.objects.all().delete()
    verrou.liberer(prise)  # ne lève rien
    verrou.liberer(None)


def test_peremption_suit_le_reglage(settings):
    settings.VERROU_IMPORT_PEREMPTION_MINUTES = 1
    assert verrou.peremption() == datetime.timedelta(minutes=1)

    verrou.prendre("premier", uuid.uuid4())
    _vieillir(2)
    assert verrou.actif() is None
