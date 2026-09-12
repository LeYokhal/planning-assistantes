"""Recette de `rattraper_effectif` (brique 6b, D6b.10) : marqueurs d'effectif des versions déjà publiées.

Jeu fictif de `fabrique` (personnes, imports d'octobre 2026) ; `donnees.construire` voit
les règles fictives par le `conftest` de `planning/tests`. La commande n'est jamais lancée
ailleurs que dans ces tests.
"""

import datetime
import json
import logging

import pytest
from django.core.management import call_command

from audit.models import Action, EvenementAudit
from planning import donnees, effectif, historique, services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

MOIS = fabrique.MOIS
AUTRE_MOIS = "2026-11"
ACTION = "planning_effectif_rattrape"
NOMS = ("BERNARD", "Emma", "ROUX", "Lina", "MOREL", "Lea", "DUPONT", "Alice", "LEROY", "Chloe", "PETIT", "Sara")
TYPES = ("Maladie", "Congé payé", "Retard", "Ecole")


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


def _sortie(capsys, **options):
    call_command("rattraper_effectif", **options)
    return capsys.readouterr()


def _publiee(cabinet, state=None):
    version = services.enregistrer(MOIS, 0, state or fabrique.etat_propre(), cabinet)
    return services.publier(MOIS, version.numero, cabinet)


def _avant_la_brique(version):
    """Une version publiée par `publier` avant la 6b : les mêmes clés, sans `effectif`."""
    sans = {cle: valeur for cle, valeur in version.verifications.items() if cle != "effectif"}
    PlanningVersion.objects.filter(pk=version.pk).update(verifications=sans)
    version.refresh_from_db()
    return version


def _version_publiee(mois, numero, affectations):
    """Patron de `test_mes_jours.py:42-46` : `publiee=True`, `verifications=[]` (défaut du modèle)."""
    return PlanningVersion.objects.create(
        mois=mois, numero=numero, state=fabrique.etat(affectations), publiee=True
    )


def _attendu(version):
    return effectif.calculer(donnees.construire(version.mois), version.state)["jours"]


def test_la_constante_d_audit_existe():
    assert Action.PLANNING_EFFECTIF_RATTRAPE == ACTION


def test_marque_une_version_publiee_avant_la_brique(cabinet, jeu, capsys):
    version = _avant_la_brique(_publiee(cabinet))
    assert set(version.verifications) == {"verifie_le", "imports", "nb_briques"}

    sortie = _sortie(capsys)

    version.refresh_from_db()
    attendu = _attendu(version)
    assert set(version.verifications) == {"verifie_le", "imports", "nb_briques", "effectif"}
    assert version.verifications["effectif"]["jours"] == attendu
    datetime.datetime.fromisoformat(version.verifications["effectif"]["calcule_le"])
    nb_moins = sum(1 for entree in attendu.values() if entree["moins"])
    nb_plus = sum(1 for entree in attendu.values() if entree["plus"])
    assert (
        f"{MOIS} v1 : marquee ({len(attendu)} jours evalues, {nb_moins} moins, {nb_plus} plus)"
        in sortie.out
    )
    assert "1 version(s) marquee(s), 0 ignoree(s)" in sortie.out
    assert "imports differents" not in sortie.out


def test_marque_une_version_publiee_sans_compte_rendu(jeu, capsys):
    """Revue 3.2 : `publiee=True, verifications=[]` (fabriques de test) — marquée, sans casser."""
    version = _version_publiee(MOIS, 1, {"2026-09-29": {"alice_dup": [fabrique.brique("emma_ber")]}})

    _sortie(capsys)

    version.refresh_from_db()
    assert set(version.verifications) == {"effectif"}
    assert version.verifications["effectif"]["jours"] == _attendu(version)


def test_rejouee_ignore_la_version_deja_marquee(cabinet, jeu, capsys):
    version = _publiee(cabinet)  # `publier` écrit le compte-rendu depuis la 6b
    avant = version.verifications

    sortie = _sortie(capsys)

    version.refresh_from_db()
    assert f"{MOIS} v1 : deja marquee, ignoree" in sortie.out
    assert "0 version(s) marquee(s), 1 ignoree(s)" in sortie.out
    assert version.verifications == avant
    assert not EvenementAudit.objects.filter(action=ACTION).exists()


def test_ignore_la_version_historique(cabinet, capsys):
    fabrique.personnes_historiques()
    version = historique.executer(
        historique.analyser(fabrique.planning_exporte(affectations=fabrique.affectations_historiques())), cabinet
    )
    avant = version.verifications

    sortie = _sortie(capsys)

    version.refresh_from_db()
    assert f"{fabrique.MOIS_HISTORIQUE} v{version.numero} : historique, ignoree" in sortie.out
    assert version.verifications == avant and "effectif" not in avant
    assert not EvenementAudit.objects.filter(action=ACTION).exists()


def test_mois_limite_la_selection(cabinet, jeu, capsys):
    octobre = _avant_la_brique(_publiee(cabinet))
    novembre = _version_publiee(AUTRE_MOIS, 1, {})

    sortie = _sortie(capsys, mois=MOIS)

    octobre.refresh_from_db()
    novembre.refresh_from_db()
    assert "effectif" in octobre.verifications
    assert novembre.verifications == []
    assert AUTRE_MOIS not in sortie.out


def test_mois_invalide_ne_fait_rien(cabinet, jeu, capsys):
    version = _avant_la_brique(_publiee(cabinet))

    sortie = _sortie(capsys, mois="2026-13")

    version.refresh_from_db()
    assert "mois invalide" in sortie.err
    assert "effectif" not in version.verifications
    assert "marquee" not in sortie.out


def test_a_blanc_n_ecrit_rien_et_n_audite_rien(cabinet, jeu, capsys):
    version = _avant_la_brique(_publiee(cabinet))
    avant = version.verifications

    sortie = _sortie(capsys, a_blanc=True)

    version.refresh_from_db()
    assert version.verifications == avant
    assert f"[a blanc] {MOIS} v1 : marquee (" in sortie.out
    assert "[a blanc] 1 version(s) marquee(s), 0 ignoree(s)" in sortie.out
    assert not EvenementAudit.objects.filter(action=ACTION).exists()


def test_imports_differents_de_la_publication_sont_signales(cabinet, jeu, capsys):
    version = _avant_la_brique(_publiee(cabinet))
    autres = {**version.verifications, "imports": [{"id": 999999, "empreinte": "0" * 64}]}
    PlanningVersion.objects.filter(pk=version.pk).update(verifications=autres)

    sortie = _sortie(capsys)

    version.refresh_from_db()
    assert f"{MOIS} v1 : marquee (" in sortie.out
    assert ", imports differents de la publication" in sortie.out
    assert "effectif" in version.verifications
    assert version.verifications["imports"] == autres["imports"]  # jamais réécrits


def test_ne_touche_ni_la_publication_ni_l_etat(cabinet, jeu, capsys):
    version = _avant_la_brique(_publiee(cabinet))

    def empreinte(v):
        return (
            v.numero,
            v.publie_le,
            v.publie_par_id,
            v.publiee,
            json.dumps(v.state, sort_keys=True),
            v.verifications["verifie_le"],
            v.verifications["imports"],
            v.verifications["nb_briques"],
        )

    avant = empreinte(version)
    _sortie(capsys)
    version.refresh_from_db()
    assert empreinte(version) == avant
    assert PlanningVersion.objects.filter(mois=MOIS).count() == 1  # aucune republication


def test_journal_un_evenement_par_version_sans_nom_ni_type(cabinet, jeu, capsys, caplog):
    _avant_la_brique(_publiee(cabinet))
    _version_publiee(AUTRE_MOIS, 1, {"2026-11-03": {"sureffectif": [fabrique.brique("emma_ber")]}})

    with caplog.at_level(logging.INFO):
        sortie = _sortie(capsys)

    evenements = list(EvenementAudit.objects.filter(action=ACTION).order_by("id"))
    assert [(e.details["mois"], e.details["numero"]) for e in evenements] == [(MOIS, 1), (AUTRE_MOIS, 1)]
    for evenement in evenements:
        assert set(evenement.details) == {"mois", "numero", "jours_evalues", "moins", "plus"}
        assert evenement.qui is None and evenement.type_objet == "PlanningVersion"
        assert "@" not in str(evenement.details)
    assert "2 version(s) marquee(s), 0 ignoree(s)" in sortie.out
    texte = sortie.out + caplog.text + " ".join(str(e.details) for e in evenements)
    for mot in NOMS + TYPES + ("emma_ber", "alice_dup"):
        assert mot not in texte, mot
