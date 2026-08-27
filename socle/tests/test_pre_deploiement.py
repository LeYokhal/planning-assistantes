"""Recette de la commande de pré-déploiement.

Railway n'exécute pas le pré-déploiement dans un shell : une seule commande.
Ces tests vérifient qu'elle enchaîne bien les deux gestes, et qu'un échec de
migration interrompt le déploiement au lieu de le laisser continuer.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

MODULE = "socle.management.commands.pre_deploiement.call_command"
ADRESSE_CABINET = "cabinet@example.org"


def test_enchaine_migrate_puis_compte(monkeypatch):
    appels = []

    def enregistrer(nom, *args, **options):
        appels.append((nom, options))

    monkeypatch.setattr(MODULE, enregistrer)
    sortie = StringIO()
    call_command("pre_deploiement", stdout=sortie)

    assert [nom for nom, _ in appels] == ["migrate", "assurer_compte_cabinet"]
    assert appels[0][1]["interactive"] is False
    assert "pre_deploiement termine." in sortie.getvalue()


def test_echec_migrate_remonte(monkeypatch):
    appels = []

    def echouer(nom, *args, **options):
        appels.append(nom)
        if nom == "migrate":
            raise RuntimeError("migration en echec")

    monkeypatch.setattr(MODULE, echouer)

    # L'exception doit remonter : un schema incomplet ne doit jamais demarrer.
    with pytest.raises(RuntimeError):
        call_command("pre_deploiement", stdout=StringIO())

    assert appels == ["migrate"]


@pytest.mark.django_db
def test_reel_sur_base_de_test(monkeypatch):
    """Sans aucun bouchon : la commande tourne pour de vrai sur la base de test."""
    monkeypatch.setenv("CABINET_EMAIL", ADRESSE_CABINET)

    call_command("pre_deploiement", stdout=StringIO())

    compte = get_user_model().objects.get(email=ADRESSE_CABINET)
    assert compte.role == "cabinet"
