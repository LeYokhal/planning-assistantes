"""Recette de l'administration des absences : la suppression laisse une trace.

Hors purge de rétention, une absence ne disparaît que par un geste
d'administration (reprise de l'existant, jeu de test). Ce geste est journalisé
sur le patron de `comptes/admin.py` : une trace par objet, avant l'effacement —
et, comme tout événement de la brique 3, sans le type d'absence ni la précision.
"""

import datetime

import pytest

from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique
from audit.models import EvenementAudit

pytestmark = pytest.mark.django_db

DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)
LISTE = "/admin/absences/absencesalariee/"


def _absence(personne=None):
    """Une absence au type et à la précision sensibles, déclarée."""
    return fabrique.absence(
        personne or fabrique.personne(),
        fabrique.type_absence(
            libelle="Maladie", categorie=TypeAbsence.Categorie.DECLARE
        ),
        DEBUT,
        FIN,
        statut=AbsenceSalariee.Statut.DECLAREE,
        precision="rendez-vous médical au CHU",
    )


def test_suppression_unitaire_journalisee(client, cabinet, connecter):
    connecter(client, cabinet)
    absence = _absence()
    pk, personne_id = absence.pk, absence.personne_id

    reponse = client.post(f"{LISTE}{pk}/delete/", {"post": "yes"})

    assert reponse.status_code == 302
    assert not AbsenceSalariee.objects.filter(pk=pk).exists()

    evenement = EvenementAudit.objects.get(action="absence_supprimee")
    assert evenement.qui_id == cabinet.pk
    assert evenement.type_objet == "AbsenceSalariee"
    assert evenement.id_objet == str(pk)
    # Rien d'autre que ces quatre clés : ni type, ni précision, ni nom.
    assert evenement.details == {
        "personne_id": personne_id,
        "statut": "declaree",
        "debut": "2026-05-26",
        "fin": "2026-05-30",
    }


def test_suppression_groupee_journalise_chaque_objet(client, cabinet, connecter):
    connecter(client, cabinet)
    personne = fabrique.personne()
    a = _absence(personne)
    b = _absence(personne)

    reponse = client.post(
        LISTE,
        {
            "action": "delete_selected",
            "_selected_action": [str(a.pk), str(b.pk)],
            "post": "yes",
        },
    )

    assert reponse.status_code == 302
    assert not AbsenceSalariee.objects.filter(pk__in=[a.pk, b.pk]).exists()

    evenements = EvenementAudit.objects.filter(action="absence_supprimee")
    assert evenements.count() == 2
    assert {e.id_objet for e in evenements} == {str(a.pk), str(b.pk)}
    assert {e.qui_id for e in evenements} == {cabinet.pk}
    for evenement in evenements:
        assert evenement.details["personne_id"] == personne.pk
        assert "Maladie" not in str(evenement.details)
        assert "médical" not in str(evenement.details)
