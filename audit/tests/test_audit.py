"""Recette du journal d'audit."""

import pytest
from django.contrib.auth import get_user_model
from sesame.utils import get_query_string

from audit.models import Action, EvenementAudit
from audit.services import journaliser


@pytest.mark.django_db
def test_journaliser_ecrit_un_evenement():
    compte = get_user_model().objects.create_user(email="assistante@example.org")

    evenement = journaliser(Action.LIEN_DEMANDE, qui=compte, objet=compte, motif="essai")

    assert evenement.pk is not None
    assert evenement.action == "lien_demande"
    assert evenement.qui_id == compte.pk
    assert evenement.type_objet == "Compte"
    assert evenement.id_objet == str(compte.pk)
    assert evenement.details == {"motif": "essai"}
    assert evenement.quand is not None


@pytest.mark.django_db
def test_journaliser_accepte_un_acteur_anonyme():
    from django.contrib.auth.models import AnonymousUser

    evenement = journaliser(Action.LIEN_REFUSE, qui=AnonymousUser(), motif="inconnu")
    assert evenement.qui is None


@pytest.mark.django_db
def test_une_adresse_glissee_dans_les_details_est_masquee():
    evenement = journaliser(Action.LIEN_REFUSE, motif="inconnu", trace="a@example.org")
    assert evenement.details == {"motif": "inconnu", "trace": "[masque]"}


@pytest.mark.django_db
def test_aucune_adresse_dans_les_details_du_parcours_reel(client):
    """Parcours complet : aucun détail journalisé ne contient d'adresse."""
    compte = get_user_model().objects.create_user(email="assistante@example.org")

    client.post("/connexion/", {"email": compte.email})
    client.post("/connexion/", {"email": "inconnue@example.org"})
    lien = "/connexion/lien/" + get_query_string(compte)
    client.get(lien)
    client.post("/deconnexion/")
    client.get(lien)

    assert EvenementAudit.objects.count() >= 5
    for evenement in EvenementAudit.objects.all():
        contenu = str(evenement.details)
        assert "@" not in contenu, f"adresse dans {evenement.action} : {contenu}"
        assert "sesame" not in contenu
