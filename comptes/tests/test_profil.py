"""Recette du changement d'adresse de connexion (décisions L et P du plan v3)."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from audit.models import EvenementAudit
from comptes import profil
from comptes.models import Personne

pytestmark = pytest.mark.django_db

PROFIL = "/mon-profil/"
NOUVELLE = "nouvelle@example.org"


@pytest.fixture
def personne():
    return Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.ASSISTANTE,
        email_contact="ancienne@example.org",
    )


def _sans_csrf(reponse):
    """Contenu de la page, jeton CSRF neutralisé (il change à chaque requête)."""
    import re

    return re.sub(
        r'value="[^"]{32,}"', 'value="JETON"', reponse.content.decode()
    )


def _confirmer(client, compte, adresse=NOUVELLE):
    jeton = profil.fabriquer_jeton(compte, adresse)
    return client.get(f"/mon-profil/confirmer/{jeton}/")


# --- Accès ------------------------------------------------------------------


def test_anonyme_redirige(client):
    reponse = client.get(PROFIL)
    assert reponse.status_code == 302
    assert reponse.url == f"/connexion/?next={PROFIL}"


def test_profil_interdit_au_cabinet(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.get(PROFIL).status_code == 403


def test_profil_ouvert_a_la_salariee(client, salariee, connecter):
    connecter(client, salariee)
    assert client.get(PROFIL).status_code == 200


# --- Demande ----------------------------------------------------------------


def test_demande_envoie_un_lien_a_la_nouvelle_adresse(client, salariee, connecter):
    connecter(client, salariee)

    with patch("comptes.views.envoyer_mail", return_value=True) as envoi:
        reponse = client.post(PROFIL, {"email": NOUVELLE})

    assert reponse.status_code == 200
    destinataire, objet, texte = envoi.call_args[0]
    assert destinataire == NOUVELLE
    assert "/mon-profil/confirmer/" in texte

    salariee.refresh_from_db()
    assert salariee.email_en_attente == NOUVELLE
    # Rien n'a changé tant que le lien n'est pas ouvert.
    assert salariee.email == "salariee@example.org"


def test_adresse_deja_prise_reponse_neutre_et_aucun_mail(
    client, salariee, cabinet, connecter
):
    """Le formulaire ne doit pas devenir un oracle d'existence de comptes."""
    connecter(client, salariee)

    with patch("comptes.views.envoyer_mail") as envoi:
        libre = client.post(PROFIL, {"email": NOUVELLE})
    with patch("comptes.views.envoyer_mail") as envoi_prise:
        prise = client.post(PROFIL, {"email": cabinet.email})

    assert envoi.call_count == 1
    assert envoi_prise.call_count == 0
    assert libre.status_code == prise.status_code == 200
    # Le jeton CSRF est régénéré à chaque requête : c'est le seul écart admis.
    assert _sans_csrf(libre) == _sans_csrf(prise)


def test_adresse_deja_prise_ne_pose_pas_l_attente(client, salariee, cabinet, connecter):
    connecter(client, salariee)

    with patch("comptes.views.envoyer_mail"):
        client.post(PROFIL, {"email": cabinet.email})

    salariee.refresh_from_db()
    assert salariee.email_en_attente == ""


def test_sa_propre_adresse_est_acceptee(client, salariee, connecter):
    """Redemander son adresse actuelle n'est pas une collision."""
    connecter(client, salariee)

    with patch("comptes.views.envoyer_mail") as envoi:
        client.post(PROFIL, {"email": salariee.email})

    assert envoi.call_count == 1


def test_adresse_mal_formee_refusee(client, salariee, connecter):
    connecter(client, salariee)

    with patch("comptes.views.envoyer_mail") as envoi:
        reponse = client.post(PROFIL, {"email": "pas-une-adresse"})

    assert reponse.status_code == 200
    assert envoi.call_count == 0


# --- Confirmation -----------------------------------------------------------


def test_confirmation_bascule_l_adresse(client, salariee, connecter, personne):
    salariee.personne = personne
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["personne", "email_en_attente"])
    connecter(client, salariee)

    reponse = _confirmer(client, salariee)

    assert reponse.status_code == 302
    salariee.refresh_from_db()
    assert salariee.email == NOUVELLE
    assert salariee.email_en_attente == ""


def test_l_adresse_de_contact_suit(client, salariee, connecter, personne):
    """Sinon la prochaine invitation repartirait sur l'ancienne."""
    salariee.personne = personne
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["personne", "email_en_attente"])
    connecter(client, salariee)

    _confirmer(client, salariee)

    personne.refresh_from_db()
    assert personne.email_contact == NOUVELLE


def test_confirmation_journalisee(client, salariee, connecter):
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)

    _confirmer(client, salariee)

    evenement = EvenementAudit.objects.get(action="adresse_changee")
    assert evenement.qui_id == salariee.pk
    # Le garde-fou « @ » masque toute adresse qui se glisserait dans `details`.
    assert "@" not in str(evenement.details)


def test_le_jeton_est_a_usage_unique(client, salariee, connecter):
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)
    jeton = profil.fabriquer_jeton(salariee, NOUVELLE)

    client.get(f"/mon-profil/confirmer/{jeton}/")
    # Le champ est vidé : le rejeu ne peut plus rien changer.
    seconde = client.get(f"/mon-profil/confirmer/{jeton}/")

    assert seconde.status_code == 302
    salariee.refresh_from_db()
    assert salariee.email == NOUVELLE


def test_jeton_falsifie_refuse(client, salariee, connecter):
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)

    client.get("/mon-profil/confirmer/jeton-bidon/")

    salariee.refresh_from_db()
    assert salariee.email == "salariee@example.org"


def test_jeton_d_un_autre_compte_refuse(client, salariee, principale, connecter):
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)

    jeton = profil.fabriquer_jeton(principale, NOUVELLE)
    client.get(f"/mon-profil/confirmer/{jeton}/")

    salariee.refresh_from_db()
    assert salariee.email == "salariee@example.org"


def test_jeton_pour_une_adresse_non_en_attente_refuse(client, salariee, connecter):
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)

    _confirmer(client, salariee, adresse="autre@example.org")

    salariee.refresh_from_db()
    assert salariee.email == "salariee@example.org"


def test_collision_apparue_entre_temps_refusee(client, salariee, connecter):
    """L'adresse a été prise par un autre compte pendant l'attente."""
    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    get_user_model().objects.create_user(email=NOUVELLE)
    connecter(client, salariee)

    _confirmer(client, salariee)

    salariee.refresh_from_db()
    assert salariee.email == "salariee@example.org"
    assert salariee.email_en_attente == ""


def test_confirmation_invalide_les_liens_magiques_en_circulation(
    client, salariee, connecter, settings
):
    """`SESAME_INVALIDATE_ON_EMAIL_CHANGE = True` : comportement voulu."""
    from sesame.utils import get_query_string

    assert settings.SESAME_INVALIDATE_ON_EMAIL_CHANGE is True
    lien_ancien = get_query_string(salariee)

    salariee.email_en_attente = NOUVELLE
    salariee.save(update_fields=["email_en_attente"])
    connecter(client, salariee)
    _confirmer(client, salariee)

    client.logout()
    reponse = client.get("/connexion/lien/" + lien_ancien)
    assert reponse.status_code == 403


# --- Jeton (unitaire) -------------------------------------------------------


def test_jeton_relu(salariee):
    jeton = profil.fabriquer_jeton(salariee, NOUVELLE)
    assert profil.lire_jeton(jeton) == (salariee.pk, NOUVELLE)


def test_jeton_perime(salariee):
    jeton = profil.fabriquer_jeton(salariee, NOUVELLE)
    with patch("comptes.profil.DUREE_SECONDES", -1):
        assert profil.lire_jeton(jeton) == (None, "")


def test_jeton_illisible():
    assert profil.lire_jeton("n-importe-quoi") == (None, "")
