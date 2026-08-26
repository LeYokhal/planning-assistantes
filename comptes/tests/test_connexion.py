"""Recette de la connexion par lien magique.

Aucune adresse réelle : uniquement des adresses du domaine example.org.
"""

import re
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from sesame.utils import get_query_string

from audit.models import EvenementAudit

ADRESSE_CONNUE = "assistante@example.org"
ADRESSE_INCONNUE = "personne-sans-compte@example.org"
ADRESSE_INACTIVE = "ancienne@example.org"


@pytest.fixture
def compte_actif(db):
    return get_user_model().objects.create_user(email=ADRESSE_CONNUE)


@pytest.fixture
def compte_inactif(db):
    return get_user_model().objects.create_user(email=ADRESSE_INACTIVE, is_active=False)


# Le jeton CSRF est remasqué à chaque rendu : il ne porte aucune information
# sur le compte et doit être neutralisé avant de comparer deux réponses.
MOTIF_CSRF = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')


def _corps_normalise(reponse):
    return MOTIF_CSRF.sub(b'name="csrfmiddlewaretoken" value="X"', reponse.content)


def _reponses_identiques(a, b):
    return a.status_code == b.status_code and _corps_normalise(a) == _corps_normalise(b)


@pytest.mark.django_db
def test_adresse_connue_declenche_un_envoi(client, compte_actif):
    with patch("comptes.views.envoyer_mail", return_value=True) as envoi:
        reponse = client.post("/connexion/", {"email": ADRESSE_CONNUE})

    assert reponse.status_code == 200
    assert envoi.call_count == 1
    destinataire, objet, texte = envoi.call_args.args
    assert destinataire == ADRESSE_CONNUE
    assert "/connexion/lien/?sesame=" in texte

    evenements = EvenementAudit.objects.filter(action="lien_demande")
    assert evenements.count() == 1
    assert evenements.get().details == {"envoye": True}


@pytest.mark.django_db
def test_adresse_inconnue_reponse_identique_et_aucun_envoi(client, compte_actif):
    with patch("comptes.views.envoyer_mail", return_value=True) as envoi:
        reponse_connue = client.post("/connexion/", {"email": ADRESSE_CONNUE})
        reponse_inconnue = client.post("/connexion/", {"email": ADRESSE_INCONNUE})
        appels_apres_inconnue = envoi.call_count

    # Un seul envoi au total : celui de l'adresse connue.
    assert appels_apres_inconnue == 1
    assert _reponses_identiques(reponse_connue, reponse_inconnue)

    refus = EvenementAudit.objects.filter(action="lien_refuse")
    assert refus.count() == 1
    assert refus.get().details == {"motif": "inconnu"}


@pytest.mark.django_db
def test_envoi_impossible_journalise_envoye_faux(client, compte_actif, settings):
    """Webhook non configuré : l'événement le dit, la réponse reste neutre."""
    settings.N8N_MAIL_WEBHOOK_URL = ""
    settings.N8N_WEBHOOK_SECRET = ""

    reponse_sans_webhook = client.post("/connexion/", {"email": ADRESSE_CONNUE})
    assert reponse_sans_webhook.status_code == 200
    assert EvenementAudit.objects.get(action="lien_demande").details == {"envoye": False}

    # La réponse est identique à celle obtenue quand l'envoi aboutit.
    with patch("comptes.views.envoyer_mail", return_value=True):
        reponse_avec_webhook = client.post("/connexion/", {"email": ADRESSE_CONNUE})
    assert _reponses_identiques(reponse_sans_webhook, reponse_avec_webhook)

    details = [e.details for e in EvenementAudit.objects.filter(action="lien_demande").order_by("id")]
    assert details == [{"envoye": False}, {"envoye": True}]


@pytest.mark.django_db
def test_compte_inactif_motif_inactif(client, compte_inactif):
    with patch("comptes.views.envoyer_mail", return_value=True) as envoi:
        reponse = client.post("/connexion/", {"email": ADRESSE_INACTIVE})

    assert reponse.status_code == 200
    assert envoi.call_count == 0
    refus = EvenementAudit.objects.get(action="lien_refuse")
    assert refus.details == {"motif": "inactif"}


@pytest.mark.django_db
def test_adresse_mal_formee_reste_neutre(client):
    with patch("comptes.views.envoyer_mail", return_value=True) as envoi:
        reponse = client.post("/connexion/", {"email": "pas-une-adresse"})

    assert reponse.status_code == 200
    assert envoi.call_count == 0
    assert EvenementAudit.objects.get(action="lien_refuse").details == {"motif": "inconnu"}


@pytest.mark.django_db
def test_jeton_valide_connecte(client, compte_actif):
    reponse = client.get("/connexion/lien/" + get_query_string(compte_actif))
    assert reponse.status_code == 302
    assert reponse["Location"] == "/"
    assert client.get("/").status_code == 200

    assert EvenementAudit.objects.filter(action="connexion").count() == 1
    compte_actif.refresh_from_db()
    assert compte_actif.active_le is not None


@pytest.mark.django_db
def test_jeton_reutilise_est_refuse(client, compte_actif):
    lien = "/connexion/lien/" + get_query_string(compte_actif)

    assert client.get(lien).status_code == 302
    client.post("/deconnexion/")

    seconde = client.get(lien)
    assert seconde.status_code == 403

    refus = EvenementAudit.objects.filter(action="connexion_refusee")
    assert refus.count() == 1
    assert refus.get().details == {"motif": "jeton_invalide"}
    # `lien_refuse` reste reserve aux refus d'envoi.
    assert not EvenementAudit.objects.filter(action="lien_refuse").exists()


@pytest.mark.django_db
def test_jeton_invente_est_refuse(client):
    reponse = client.get("/connexion/lien/?sesame=jeton-invente")
    assert reponse.status_code == 403
    assert EvenementAudit.objects.get(action="connexion_refusee").details == {
        "motif": "jeton_invalide"
    }


@pytest.mark.django_db
def test_deconnexion_journalisee(client, compte_actif):
    client.get("/connexion/lien/" + get_query_string(compte_actif))
    reponse = client.post("/deconnexion/")
    assert reponse.status_code == 302
    assert EvenementAudit.objects.filter(action="deconnexion").count() == 1


@pytest.mark.django_db
def test_admin_inaccessible_avant_connexion(client):
    reponse = client.get("/admin/")
    assert reponse.status_code == 302
    assert "/connexion/" in reponse["Location"] or "/admin/login/" in reponse["Location"]

    # La page de connexion native de l'administration renvoie vers la nôtre.
    redirection = client.get("/admin/login/")
    assert redirection.status_code == 302
    assert redirection["Location"] == "/connexion/?next=/admin/"


@pytest.mark.django_db
def test_admin_accessible_apres_connexion(client):
    cabinet = get_user_model().objects.create_superuser(email="cabinet@example.org")
    client.get("/connexion/lien/" + get_query_string(cabinet))

    reponse = client.get("/admin/")
    assert reponse.status_code == 200
