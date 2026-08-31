"""Recette de l'action d'admin « Créer les comptes de connexion ».

Adresses fictives du domaine example.org uniquement.
"""

import pytest
from django.contrib.auth import get_user_model

from audit.models import EvenementAudit
from comptes.models import Compte, Personne

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/comptes/personne/"


def personne(nom, prenom, email_contact="", **extra):
    return Personne.objects.create(
        nom=nom,
        prenom=prenom,
        role_metier=Personne.RoleMetier.ASSISTANTE,
        email_contact=email_contact,
        **extra,
    )


def lancer(client, personnes):
    return client.post(
        CHANGELIST,
        {
            "action": "creer_comptes",
            "_selected_action": [str(p.pk) for p in personnes],
            "index": "0",
        },
        follow=True,
    )


def test_cree_les_comptes_manquants(client, cabinet, connecter):
    alice = personne("DUPONT", "Alice", "alice@example.org")
    connecter(client, cabinet)

    lancer(client, [alice])

    compte = Compte.objects.get(email="alice@example.org")
    assert compte.personne_id == alice.pk
    assert compte.role == Compte.Role.SALARIEE
    assert compte.is_staff is False
    assert compte.is_active is True
    assert not compte.has_usable_password()


def test_aucune_invitation_envoyee(client, cabinet, connecter):
    alice = personne("DUPONT", "Alice", "alice@example.org")
    connecter(client, cabinet)

    lancer(client, [alice])

    compte = Compte.objects.get(email="alice@example.org")
    assert compte.invite_le is None
    assert compte.active_le is None
    assert not EvenementAudit.objects.filter(action="invitation_envoyee").exists()


def test_sans_adresse_ignoree(client, cabinet, connecter):
    sans = personne("DUPONT", "Alice")
    connecter(client, cabinet)

    lancer(client, [sans])

    assert not Compte.objects.filter(personne=sans).exists()


def test_deja_un_compte_ignoree(client, cabinet, connecter):
    alice = personne("DUPONT", "Alice", "alice@example.org")
    Compte.objects.create_user(email="deja@example.org", personne=alice)
    connecter(client, cabinet)

    lancer(client, [alice])

    assert not Compte.objects.filter(email="alice@example.org").exists()
    assert Compte.objects.filter(personne=alice).count() == 1


def test_adresse_deja_prise_ignoree(client, cabinet, connecter):
    get_user_model().objects.create_user(email="alice@example.org")
    alice = personne("DUPONT", "Alice", "alice@example.org")
    connecter(client, cabinet)

    lancer(client, [alice])

    assert Compte.objects.filter(email="alice@example.org").count() == 1
    assert Compte.objects.get(email="alice@example.org").personne_id is None


def test_lot_mixte_compte_les_ignores(client, cabinet, connecter):
    avec = personne("DUPONT", "Alice", "alice@example.org")
    sans = personne("MARTIN", "Bob")
    connecter(client, cabinet)

    reponse = lancer(client, [avec, sans])

    assert "1 compte(s) créé(s), 1 ignoré(s)." in reponse.content.decode()


def test_audit_par_compte_et_recapitulatif(client, cabinet, connecter):
    avec = personne("DUPONT", "Alice", "alice@example.org")
    sans = personne("MARTIN", "Bob")
    connecter(client, cabinet)

    lancer(client, [avec, sans])

    compte = Compte.objects.get(email="alice@example.org")
    cree = EvenementAudit.objects.get(action="compte_cree")
    assert cree.qui_id == cabinet.pk
    assert cree.type_objet == "Compte"
    assert cree.id_objet == str(compte.pk)

    recapitulatif = EvenementAudit.objects.get(action="comptes_crees")
    assert recapitulatif.qui_id == cabinet.pk
    assert recapitulatif.details == {"crees": 1, "ignores": 1}


def test_audit_ne_porte_aucune_adresse(client, cabinet, connecter):
    alice = personne("DUPONT", "Alice", "alice@example.org")
    connecter(client, cabinet)

    lancer(client, [alice])

    for evenement in EvenementAudit.objects.all():
        assert "alice@example.org" not in str(evenement.details)


def test_action_rejouable(client, cabinet, connecter):
    alice = personne("DUPONT", "Alice", "alice@example.org")
    connecter(client, cabinet)

    lancer(client, [alice])
    lancer(client, [alice])

    assert Compte.objects.filter(email="alice@example.org").count() == 1


def test_filtre_agenda_doctolib(client, cabinet, connecter):
    personne("DUPONT", "Alice", agenda_doctolib="DUPONT Alice")
    personne("MARTIN", "Bob")
    connecter(client, cabinet)

    renseigne = client.get(CHANGELIST, {"agenda": "oui"}).content.decode()
    vide = client.get(CHANGELIST, {"agenda": "non"}).content.decode()

    assert "DUPONT" in renseigne and "MARTIN" not in renseigne
    assert "MARTIN" in vide and "DUPONT" not in vide
