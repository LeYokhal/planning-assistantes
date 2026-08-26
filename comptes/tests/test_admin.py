"""Recette de l'administration : le journal d'audit reste non modifiable."""

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from sesame.utils import get_query_string

from audit.models import EvenementAudit
from audit.services import journaliser


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
