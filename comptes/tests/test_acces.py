"""Recette du décorateur de contrôle de rôle."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from audit.models import EvenementAudit
from comptes.acces import role_requis


@role_requis("cabinet")
def vue_jouet(request):
    """Vue minimale, uniquement là pour éprouver le décorateur."""
    return HttpResponse("ok")


@pytest.fixture
def cabinet(db):
    return get_user_model().objects.create_superuser(email="cabinet@example.org")


@pytest.fixture
def salariee(db):
    return get_user_model().objects.create_user(email="salariee@example.org")


def test_anonyme_redirige_avec_le_next(rf):
    requete = rf.get("/presences/2026-10/")
    requete.user = AnonymousUser()

    reponse = vue_jouet(requete)

    assert reponse.status_code == 302
    assert reponse.url == "/connexion/?next=/presences/2026-10/"


@pytest.mark.django_db
def test_mauvais_role_refuse_et_journalise(rf, salariee):
    requete = rf.get("/presences/2026-10/")
    requete.user = salariee

    with pytest.raises(PermissionDenied):
        vue_jouet(requete)

    evenement = EvenementAudit.objects.get(action="acces_refuse")
    assert evenement.qui == salariee
    assert evenement.details == {"vue": "vue_jouet"}


@pytest.mark.django_db
def test_bon_role_passe(rf, cabinet):
    requete = rf.get("/presences/2026-10/")
    requete.user = cabinet

    reponse = vue_jouet(requete)

    assert reponse.status_code == 200
    assert not EvenementAudit.objects.filter(action="acces_refuse").exists()


@pytest.mark.django_db
def test_superutilisateur_ne_contourne_pas_le_role(rf, salariee):
    """`is_superuser` ne vaut pas rôle : seul `role` décide."""
    salariee.is_superuser = True
    salariee.is_staff = True
    salariee.save()
    requete = rf.get("/presences/2026-10/")
    requete.user = salariee

    with pytest.raises(PermissionDenied):
        vue_jouet(requete)


@pytest.mark.django_db
def test_plusieurs_roles_admis(rf, salariee):
    @role_requis("cabinet", "salariee")
    def vue_ouverte(request):
        return HttpResponse("ok")

    requete = rf.get("/presences/")
    requete.user = salariee

    assert vue_ouverte(requete).status_code == 200
