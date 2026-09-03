"""Recette des écrans : rôles, cloisonnement, et compte sans personne liée."""

import datetime

import pytest

from absences import services
from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique

pytestmark = pytest.mark.django_db

DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)

ESPACE_SALARIEE = "/mes-absences/"
NOUVELLE = "/mes-absences/nouvelle/"
DECISION = "/absences/"


# --- Contrôle de rôle -------------------------------------------------------


@pytest.mark.parametrize("url", [ESPACE_SALARIEE, NOUVELLE, DECISION])
def test_anonyme_redirige_vers_la_connexion(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 302
    assert reponse.url == f"/connexion/?next={url}"


@pytest.mark.parametrize("url", [ESPACE_SALARIEE, NOUVELLE])
def test_espace_salariee_interdit_au_cabinet(client, cabinet, connecter, url):
    connecter(client, cabinet)
    assert client.get(url).status_code == 403


def test_ecran_de_decision_interdit_a_la_salariee(client, salariee, connecter):
    connecter(client, salariee)
    assert client.get(DECISION).status_code == 403


def test_ecran_de_decision_ouvert_a_la_principale(client, principale, connecter):
    connecter(client, principale)
    assert client.get(DECISION).status_code == 200


def test_ecran_de_decision_ouvert_au_cabinet(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.get(DECISION).status_code == 200


# --- Décision H : compte sans personne liée ---------------------------------


def test_compte_sans_personne_voit_un_message_et_pas_un_500(
    client, salariee, connecter
):
    connecter(client, salariee)

    reponse = client.get(ESPACE_SALARIEE)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "pas encore rattaché" in contenu


def test_compte_sans_personne_ne_se_voit_pas_proposer_la_saisie(
    client, salariee, connecter
):
    connecter(client, salariee)

    reponse = client.get(NOUVELLE)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    # Le seul formulaire de la page de repli est celui de la déconnexion :
    # ni champ de motif, ni bouton d'envoi.
    assert 'name="date_debut"' not in contenu
    assert "pas encore rattaché" in contenu


def test_compte_sans_personne_ne_peut_pas_poster(client, salariee, connecter):
    connecter(client, salariee)
    type_ = fabrique.type_absence()

    reponse = client.post(
        NOUVELLE,
        {"type": type_.pk, "date_debut": "2026-05-26", "date_fin": "2026-05-30"},
    )

    assert reponse.status_code == 200
    assert AbsenceSalariee.objects.count() == 0


# --- Cloisonnement ----------------------------------------------------------


def test_une_salariee_ne_voit_que_ses_absences(client, salariee, connecter):
    mienne = fabrique.personne(nom="DUPONT", prenom="Alice")
    autre = fabrique.personne(nom="MARTIN", prenom="Bob")
    fabrique.lier(salariee, mienne)
    fabrique.absence(mienne, fabrique.type_absence(), DEBUT, FIN)
    fabrique.absence(autre, fabrique.type_absence(), DEBUT, FIN)

    connecter(client, salariee)
    contenu = client.get(ESPACE_SALARIEE).content.decode()

    assert "26/05/2026" in contenu
    assert "MARTIN" not in contenu


def test_une_salariee_ne_peut_pas_annuler_l_absence_d_une_autre(
    client, salariee, connecter
):
    fabrique.lier(salariee, fabrique.personne(nom="DUPONT", prenom="Alice"))
    autre = fabrique.absence(
        fabrique.personne(nom="MARTIN", prenom="Bob"), fabrique.type_absence()
    )

    connecter(client, salariee)
    reponse = client.post(f"/mes-absences/{autre.pk}/annuler/")

    assert reponse.status_code == 404
    autre.refresh_from_db()
    assert autre.statut == AbsenceSalariee.Statut.EN_ATTENTE


# --- Saisie -----------------------------------------------------------------


def test_saisie_d_une_demande(client, salariee, connecter):
    personne = fabrique.personne()
    fabrique.lier(salariee, personne)
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DEMANDE)

    connecter(client, salariee)
    reponse = client.post(
        NOUVELLE,
        {"type": type_.pk, "date_debut": "2026-05-26", "date_fin": "2026-05-30"},
    )

    assert reponse.status_code == 302
    absence = AbsenceSalariee.objects.get()
    assert absence.personne == personne
    assert absence.statut == AbsenceSalariee.Statut.EN_ATTENTE


def test_saisie_aux_dates_inversees_refusee(client, salariee, connecter):
    fabrique.lier(salariee, fabrique.personne())
    type_ = fabrique.type_absence()

    connecter(client, salariee)
    reponse = client.post(
        NOUVELLE,
        {"type": type_.pk, "date_debut": "2026-05-30", "date_fin": "2026-05-26"},
    )

    assert reponse.status_code == 200
    assert AbsenceSalariee.objects.count() == 0


def test_annulation_par_la_salariee(client, salariee, connecter):
    personne = fabrique.personne()
    fabrique.lier(salariee, personne)
    absence = fabrique.absence(personne, fabrique.type_absence())

    connecter(client, salariee)
    client.post(f"/mes-absences/{absence.pk}/annuler/")

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.ANNULEE


# --- Décision depuis l'écran ------------------------------------------------


def test_validation_depuis_l_ecran(client, principale, connecter):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)

    connecter(client, principale)
    client.post(f"/absences/{absence.pk}/decider/", {"decision": "valider"})

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.VALIDEE


def test_regle_k_refusee_cote_serveur(client, principale, connecter):
    """Même en postant à la main, la principale ne valide pas sa propre absence."""
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    absence = fabrique.absence(personne, fabrique.type_absence())

    connecter(client, principale)
    client.post(f"/absences/{absence.pk}/decider/", {"decision": "valider"})

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.EN_ATTENTE


def test_correction_depuis_l_ecran(client, principale, connecter):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence(), DEBUT, FIN)
    services.decider(absence, True, principale)

    connecter(client, principale)
    client.post(f"/absences/{absence.pk}/corriger/", {"jours_comptes": "0.5"})

    absence.refresh_from_db()
    assert str(absence.jours_comptes) == "0.5"


def test_les_methodes_get_sont_refusees_sur_les_actions(client, principale, connecter):
    absence = fabrique.absence(fabrique.personne(), fabrique.type_absence())
    connecter(client, principale)

    assert client.get(f"/absences/{absence.pk}/decider/").status_code == 404
    assert client.get(f"/absences/{absence.pk}/corriger/").status_code == 404


# --- Navigation -------------------------------------------------------------


def test_l_accueil_propose_ses_absences_a_la_salariee(client, salariee, connecter):
    connecter(client, salariee)
    contenu = client.get("/").content.decode()
    assert "/mes-absences/" in contenu


def test_l_accueil_propose_l_ecran_de_decision_a_la_principale(
    client, principale, connecter
):
    connecter(client, principale)
    contenu = client.get("/").content.decode()
    assert "/absences/" in contenu


def test_l_accueil_ne_propose_pas_l_ecran_de_decision_a_la_salariee(
    client, salariee, connecter
):
    connecter(client, salariee)
    contenu = client.get("/").content.decode()
    assert 'href="/absences/"' not in contenu
