"""Recette des commandes de gestion."""

import logging
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from audit.models import EvenementAudit

ADRESSE_CABINET = "cabinet@example.org"


@pytest.mark.django_db
def test_assurer_compte_cabinet_cree_puis_est_idempotente(settings):
    settings.CABINET_EMAIL = ADRESSE_CABINET
    Compte = get_user_model()

    sortie = StringIO()
    call_command("assurer_compte_cabinet", stdout=sortie)

    compte = Compte.objects.get(email=ADRESSE_CABINET)
    assert compte.role == "cabinet"
    assert compte.is_staff and compte.is_superuser
    assert not compte.has_usable_password()
    assert EvenementAudit.objects.get(action="compte_cabinet_assure").details == {
        "cree": True
    }

    # Deuxième passage : aucun nouveau compte, événement avec "cree": False.
    call_command("assurer_compte_cabinet", stdout=StringIO())
    assert Compte.objects.filter(email=ADRESSE_CABINET).count() == 1
    evenements = list(
        EvenementAudit.objects.filter(action="compte_cabinet_assure").order_by("id")
    )
    assert [e.details for e in evenements] == [{"cree": True}, {"cree": False}]


@pytest.mark.django_db
def test_assurer_compte_cabinet_sans_adresse_sort_en_code_zero(settings):
    settings.CABINET_EMAIL = ""
    sortie, erreurs = StringIO(), StringIO()

    # Aucune exception ne doit remonter : le pré-déploiement ne doit jamais échouer.
    call_command("assurer_compte_cabinet", stdout=sortie, stderr=erreurs)

    assert get_user_model().objects.count() == 0
    assert "CABINET_EMAIL" in sortie.getvalue()
    assert erreurs.getvalue() == ""


@pytest.mark.django_db
def test_assurer_compte_cabinet_ne_leve_jamais(settings, monkeypatch):
    settings.CABINET_EMAIL = ADRESSE_CABINET

    def echouer(*args, **kwargs):
        raise RuntimeError("panne simulee")

    monkeypatch.setattr(
        "comptes.management.commands.assurer_compte_cabinet.Command._assurer", echouer
    )
    erreurs = StringIO()
    call_command("assurer_compte_cabinet", stdout=StringIO(), stderr=erreurs)

    assert "RuntimeError" in erreurs.getvalue()
    assert "panne simulee" not in erreurs.getvalue()


@pytest.mark.django_db
def test_lien_connexion_affiche_le_lien_sans_le_journaliser(settings, caplog):
    settings.APP_URL = "http://testserver"
    compte = get_user_model().objects.create_user(email="assistante@example.org")

    sortie = StringIO()
    with caplog.at_level(logging.DEBUG):
        call_command("lien_connexion", compte.email, stdout=sortie)

    lien = sortie.getvalue().strip()
    assert lien.startswith("http://testserver/connexion/lien/?sesame=")
    assert lien not in caplog.text
    assert "sesame" not in caplog.text
    assert compte.email not in caplog.text

    evenement = EvenementAudit.objects.get(action="lien_secours")
    assert evenement.qui_id == compte.pk
    assert evenement.details == {}


@pytest.mark.django_db
def test_lien_connexion_refuse_une_adresse_inconnue():
    with pytest.raises(CommandError):
        call_command("lien_connexion", "inconnue@example.org", stdout=StringIO())
