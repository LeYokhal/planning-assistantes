"""Recette de `agendas_recents` : la liste d'agendas offerte à l'appariement.

Agendas fictifs, fabriqués par `fabrique.py`. Aucun payload réel.
"""

import datetime
import uuid

import pytest

from presences.models import ImportPresences
from presences.services import agendas_recents, importer_fichier

from .fabrique import en_direct, fabriquer_payload

pytestmark = pytest.mark.django_db

DEBUT = datetime.date(2026, 9, 1)
FIN = datetime.date(2026, 9, 3)


def importer(praticiens, debut=DEBUT, fin=FIN, lot=None):
    """Pose un import réussi porteur de ces agendas."""
    import_ = importer_fichier(
        en_direct(fabriquer_payload(debut, fin, praticiens=praticiens)), None
    )
    assert import_.statut == ImportPresences.Statut.REUSSI
    if lot is not None:
        ImportPresences.objects.filter(pk=import_.pk).update(lot=lot)
    return import_


def test_aucun_import_aucune_agenda():
    assert agendas_recents() == ()


def test_agendas_du_dernier_import():
    importer(("DUPONT Alice", "MARTIN Bob"))

    assert agendas_recents() == ("DUPONT Alice", "MARTIN Bob")


def test_tri_insensible_a_la_casse():
    importer(("martin bob", "DUPONT Alice"))

    assert agendas_recents() == ("DUPONT Alice", "martin bob")


def test_espaces_retires():
    importer(("  DUPONT Alice  ",))

    assert agendas_recents() == ("DUPONT Alice",)


def test_union_des_fenetres_du_meme_lot():
    """Un mois se couvre en deux fenêtres : les deux comptent."""
    lot = uuid.uuid4()
    importer(("DUPONT Alice",), lot=lot)
    importer(
        ("MARTIN Bob",),
        debut=datetime.date(2026, 9, 4),
        fin=datetime.date(2026, 9, 6),
        lot=lot,
    )

    assert agendas_recents() == ("DUPONT Alice", "MARTIN Bob")


def test_lot_precedent_ignore():
    importer(("ANCIEN Praticien",), lot=uuid.uuid4())
    importer(("DUPONT Alice",), lot=uuid.uuid4())

    assert agendas_recents() == ("DUPONT Alice",)


def test_import_en_echec_ignore():
    importer(("DUPONT Alice",))
    ImportPresences.objects.create(
        source=ImportPresences.Source.FICHIER,
        statut=ImportPresences.Statut.ECHEC,
        erreur="JSON illisible",
    )

    assert agendas_recents() == ("DUPONT Alice",)
