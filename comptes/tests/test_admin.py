"""Recette de l'administration : le journal d'audit reste non modifiable."""

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from sesame.utils import get_query_string

from audit.models import EvenementAudit
from audit.services import journaliser
from comptes.models import Personne


@pytest.fixture
def cabinet(db):
    return get_user_model().objects.create_superuser(email="cabinet@example.org")


def test_journal_non_modifiable(cabinet, rf):
    admin_audit = site._registry[EvenementAudit]
    requete = rf.get("/admin/audit/evenementaudit/")
    requete.user = cabinet

    assert admin_audit.has_add_permission(requete) is False
    assert admin_audit.has_change_permission(requete) is False
    assert admin_audit.has_delete_permission(requete) is False


@pytest.mark.django_db
def test_pages_du_journal_refusent_ajout_et_suppression(client, cabinet):
    evenement = journaliser("connexion", qui=cabinet)
    client.get("/connexion/lien/" + get_query_string(cabinet))

    assert client.get("/admin/audit/evenementaudit/").status_code == 200
    assert client.get("/admin/audit/evenementaudit/add/").status_code == 403
    assert (
        client.get(f"/admin/audit/evenementaudit/{evenement.pk}/delete/").status_code
        == 403
    )

    # La page de detail existe mais en lecture seule : aucune sauvegarde possible.
    reponse = client.post(f"/admin/audit/evenementaudit/{evenement.pk}/change/", {})
    assert reponse.status_code in (302, 403)
    assert EvenementAudit.objects.filter(pk=evenement.pk).exists()


@pytest.mark.django_db
def test_creation_de_compte_dans_admin_journalise(client, cabinet):
    client.get("/connexion/lien/" + get_query_string(cabinet))

    reponse = client.post(
        "/admin/comptes/compte/add/",
        {
            "email": "nouvelle@example.org",
            "role": "salariee",
            "is_active": "on",
            "personne": "",
        },
    )
    assert reponse.status_code == 302

    nouvelle = get_user_model().objects.get(email="nouvelle@example.org")
    assert not nouvelle.has_usable_password()

    evenement = EvenementAudit.objects.get(action="compte_cree")
    assert evenement.qui_id == cabinet.pk
    assert evenement.type_objet == "Compte"
    assert evenement.id_objet == str(nouvelle.pk)
    assert evenement.details == {}


@pytest.mark.django_db
def test_suppression_de_personne_journalisee(client, cabinet):
    client.get("/connexion/lien/" + get_query_string(cabinet))
    personne = Personne.objects.create(
        nom="DUPONT", prenom="Alice", role_metier=Personne.RoleMetier.ASSISTANTE
    )
    pk = personne.pk

    reponse = client.post(
        f"/admin/comptes/personne/{pk}/delete/", {"post": "yes"}
    )
    assert reponse.status_code == 302
    assert not Personne.objects.filter(pk=pk).exists()

    evenement = EvenementAudit.objects.get(action="personne_supprimee")
    assert evenement.qui_id == cabinet.pk
    assert evenement.type_objet == "Personne"
    assert evenement.id_objet == str(pk)


@pytest.mark.django_db
def test_suppression_de_compte_journalisee(client, cabinet):
    client.get("/connexion/lien/" + get_query_string(cabinet))
    compte = get_user_model().objects.create_user(email="asupprimer@example.org")
    pk = compte.pk

    reponse = client.post(f"/admin/comptes/compte/{pk}/delete/", {"post": "yes"})
    assert reponse.status_code == 302
    assert not get_user_model().objects.filter(pk=pk).exists()

    evenement = EvenementAudit.objects.get(action="compte_supprime")
    assert evenement.qui_id == cabinet.pk
    assert evenement.type_objet == "Compte"
    assert evenement.id_objet == str(pk)


@pytest.mark.django_db
def test_suppression_groupee_journalise_chaque_objet(client, cabinet):
    client.get("/connexion/lien/" + get_query_string(cabinet))
    a = Personne.objects.create(
        nom="DUPONT", prenom="Alice", role_metier=Personne.RoleMetier.ASSISTANTE
    )
    b = Personne.objects.create(
        nom="MARTIN", prenom="Bob", role_metier=Personne.RoleMetier.ASSISTANTE
    )

    reponse = client.post(
        "/admin/comptes/personne/",
        {
            "action": "delete_selected",
            "_selected_action": [str(a.pk), str(b.pk)],
            "post": "yes",
        },
    )
    assert reponse.status_code == 302
    assert not Personne.objects.filter(pk__in=[a.pk, b.pk]).exists()

    evenements = EvenementAudit.objects.filter(action="personne_supprimee")
    assert evenements.count() == 2
    assert {e.id_objet for e in evenements} == {str(a.pk), str(b.pk)}
