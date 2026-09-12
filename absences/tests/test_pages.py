"""Recette des écrans : rôles, cloisonnement, et compte sans personne liée."""

import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.template.loader import get_template

from absences import services
from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique
from audit.models import EvenementAudit

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


def test_l_accueil_renvoie_la_salariee_vers_ses_jours(client, salariee, connecter):
    """Brique 6a (C6.5) : `/` n'est plus une page pour la salariée, mais une redirection."""
    connecter(client, salariee)
    reponse = client.get("/")
    assert reponse.status_code == 302
    assert reponse["Location"] == "/mes-jours/"
    # L'onglet bas de la coquille mène à ses absences depuis chacune de ses pages.
    assert 'href="/mes-absences/"' in client.get("/mes-absences/").content.decode()


def test_l_accueil_propose_l_ecran_de_decision_a_la_principale(
    client, principale, connecter
):
    connecter(client, principale)
    contenu = client.get("/").content.decode()
    assert "/absences/" in contenu


def test_la_coquille_ne_propose_pas_l_ecran_de_decision_a_la_salariee(
    client, salariee, connecter
):
    connecter(client, salariee)
    contenu = client.get("/mes-absences/").content.decode()
    assert 'href="/absences/"' not in contenu


# --- Brique 3-bis : la principale est aussi une salariée --------------------


def test_la_principale_accede_a_son_espace(client, principale, connecter):
    fabrique.lier(principale, fabrique.personne())
    connecter(client, principale)

    assert client.get(ESPACE_SALARIEE).status_code == 200
    assert client.get(NOUVELLE).status_code == 200


def test_la_principale_cree_une_demande(client, principale, connecter):
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DEMANDE)

    connecter(client, principale)
    reponse = client.post(
        NOUVELLE,
        {"type": type_.pk, "date_debut": "2026-05-26", "date_fin": "2026-05-30"},
    )

    assert reponse.status_code == 302
    absence = AbsenceSalariee.objects.get()
    assert absence.personne == personne
    assert absence.statut == AbsenceSalariee.Statut.EN_ATTENTE


def test_la_principale_ne_decide_pas_sa_propre_demande(
    client, principale, connecter
):
    """Règle K : la demande qu'elle vient de saisir n'est pas décidable par elle."""
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    type_ = fabrique.type_absence(categorie=TypeAbsence.Categorie.DEMANDE)
    connecter(client, principale)
    client.post(
        NOUVELLE,
        {"type": type_.pk, "date_debut": "2026-05-26", "date_fin": "2026-05-30"},
    )
    absence = AbsenceSalariee.objects.get()

    ecran = client.get(DECISION).content.decode()
    assert "seul le cabinet la tranche" in ecran

    reponse = client.post(
        f"/absences/{absence.pk}/decider/", {"decision": "valider"}, follow=True
    )

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.EN_ATTENTE
    assert (
        "Vous ne pouvez pas décider de votre propre absence"
        in reponse.content.decode()
    )


def test_le_cabinet_decide_la_demande_de_la_principale(
    client, principale, cabinet, connecter
):
    personne = fabrique.personne()
    fabrique.lier(principale, personne)
    absence = fabrique.absence(personne, fabrique.type_absence())

    connecter(client, cabinet)
    client.post(f"/absences/{absence.pk}/decider/", {"decision": "valider"})

    absence.refresh_from_db()
    assert absence.statut == AbsenceSalariee.Statut.VALIDEE
    assert absence.decide_par == cabinet


def test_le_cabinet_sans_personne_reste_exclu_de_l_espace(
    client, cabinet, connecter
):
    """403 par le rôle, pas la page de repli : le cabinet n'a pas d'espace personnel."""
    assert cabinet.personne_id is None
    connecter(client, cabinet)

    reponse = client.get(ESPACE_SALARIEE)

    assert reponse.status_code == 403
    assert EvenementAudit.objects.filter(action="acces_refuse", qui=cabinet).exists()


def test_la_principale_sans_personne_voit_la_page_de_repli(
    client, principale, connecter
):
    """Décision H, telle quelle : ni 500, ni 403."""
    assert principale.personne_id is None
    connecter(client, principale)

    reponse = client.get(ESPACE_SALARIEE)

    assert reponse.status_code == 200
    assert "pas encore rattaché" in reponse.content.decode()


def test_l_accueil_propose_son_espace_a_la_principale(
    client, principale, connecter
):
    connecter(client, principale)
    contenu = client.get("/").content.decode()
    assert 'href="/mes-absences/"' in contenu
    assert 'href="/mon-profil/"' in contenu


def test_l_accueil_ne_propose_pas_l_espace_au_cabinet(client, cabinet, connecter):
    connecter(client, cabinet)
    contenu = client.get("/").content.decode()
    assert 'href="/mes-absences/"' not in contenu
    assert 'href="/mon-profil/"' not in contenu


# --- Brique 6b : « Mes absences » par mois (C6.19), confirmation, formulaire en deux groupes ---

AUJOURD_HUI = datetime.date(2026, 9, 12)


def _connectee(client, salariee, connecter):
    personne = fabrique.personne()
    fabrique.lier(salariee, personne)
    connecter(client, salariee)
    return personne


def test_mes_absences_groupees_par_mois_du_plus_recent_au_plus_ancien(client, salariee, connecter):
    """C6.19 / D6b.6 : un groupe par mois de début, à venir et courant ouverts, passés repliés."""
    personne = _connectee(client, salariee, connecter)
    type_ = fabrique.type_absence()
    fabrique.absence(personne, type_, datetime.date(2026, 5, 26), datetime.date(2026, 5, 30))
    fabrique.absence(personne, type_, datetime.date(2026, 9, 15), datetime.date(2026, 9, 15))
    fabrique.absence(personne, type_, datetime.date(2026, 10, 6), datetime.date(2026, 10, 6))
    fabrique.absence(personne, type_, datetime.date(2026, 10, 20), datetime.date(2026, 10, 21))

    with patch("absences.views.timezone.localdate", return_value=AUJOURD_HUI):
        reponse = client.get(ESPACE_SALARIEE)
    contenu = reponse.content.decode()

    assert contenu.count('<details class="mois"') == 3
    octobre = '<details class="mois" open><summary>Octobre 2026 — 2 absences</summary>'
    septembre = '<details class="mois" open><summary>Septembre 2026 — 1 absence</summary>'
    mai = '<details class="mois"><summary>Mai 2026 — 1 absence</summary>'
    assert contenu.index(octobre) < contenu.index(septembre) < contenu.index(mai)
    assert [groupe["cle"] for groupe in reponse.context["groupes"]] == ["2026-10", "2026-09", "2026-05"]
    assert [groupe["ouvert"] for groupe in reponse.context["groupes"]] == [True, True, False]
    assert "Du 20/10/2026 au 21/10/2026" in contenu and "Le 06/10/2026" in contenu
    assert len(reponse.context["absences"]) == 4


def test_etat_vide_et_bouton_nouvelle_absence(client, salariee, connecter):
    _connectee(client, salariee, connecter)
    contenu = client.get(ESPACE_SALARIEE).content.decode()
    assert "Aucune absence pour l'instant." in contenu
    assert '<a class="bouton" href="/mes-absences/nouvelle/">Nouvelle absence</a>' in contenu
    assert '<details class="mois"' not in contenu and "Déclarer une absence" not in contenu


def test_pastilles_par_statut_et_jours_comptes(client, salariee, connecter):
    personne = _connectee(client, salariee, connecter)
    type_ = fabrique.type_absence()
    for statut in ("en_attente", "validee", "declaree", "refusee", "annulee"):
        fabrique.absence(personne, type_, DEBUT, FIN, statut=statut)
    validee = AbsenceSalariee.objects.get(statut="validee")
    validee.jours_comptes = Decimal("1.0")
    validee.save(update_fields=["jours_comptes"])

    contenu = client.get(ESPACE_SALARIEE).content.decode()

    for classe, libelle in (
        ("attente", "En attente"), ("ok", "Validée"), ("ok", "Déclarée"),
        ("refuse", "Refusée"), ("neutre", "Annulée"),
    ):
        assert f'<span class="pastille {classe}">{libelle}</span>' in contenu, libelle
    assert contenu.count('class="vide"') == 4 and ">1,0<" in contenu


def test_confirmation_par_dialog_pour_les_demandes_en_attente_seulement(client, salariee, connecter):
    """D6b.7 : un `<dialog>` par demande en attente, le `POST` d'annulation existant inchangé."""
    personne = _connectee(client, salariee, connecter)
    attente = fabrique.absence(personne, fabrique.type_absence(), DEBUT, FIN)
    validee = fabrique.absence(personne, fabrique.type_absence(), DEBUT, FIN, statut="validee")

    contenu = client.get(ESPACE_SALARIEE).content.decode()

    assert f'<dialog id="dialog-{attente.pk}">' in contenu
    assert f'dialog-{validee.pk}' not in contenu
    assert f'data-confirme="dialog-{attente.pk}"' in contenu
    assert contenu.count(f'action="/mes-absences/{attente.pk}/annuler/"') == 2  # le bouton et le dialog
    assert contenu.count("Annuler la demande") == 2 and "Garder la demande" in contenu
    assert "Annuler cette demande ?" in contenu
    assert f'action="/mes-absences/{validee.pk}/annuler/"' not in contenu


def test_formulaire_en_deux_groupes(client, salariee, connecter):
    """D6b.8 / E-3 : « Type » en deux `<optgroup>` par catégorie, `FormulaireAbsence` intouché."""
    _connectee(client, salariee, connecter)
    contenu = client.get(NOUVELLE).content.decode()

    assert contenu.count("<optgroup") == 2
    demande = contenu.index('<optgroup label="Soumis à décision">')
    declare = contenu.index('<optgroup label="Déclaration (effective immédiatement)">')
    assert demande < contenu.index(">Congé payé</option>") < declare < contenu.index(">Retard</option>")
    assert 'data-categorie="demande"' in contenu and 'data-categorie="declare"' in contenu
    assert '<option value="">— choisir —</option>' in contenu
    assert '<select name="type" id="id_type" required>' in contenu
    assert '<button type="submit" class="bouton" id="envoyer">Envoyer</button>' in contenu
    assert 'name="date_debut"' in contenu and 'name="date_fin"' in contenu and 'name="precision"' in contenu
    assert 'href="/mes-absences/"' in contenu  # retour à mes absences


def test_selection_conservee_apres_une_erreur_de_dates(client, salariee, connecter):
    _connectee(client, salariee, connecter)
    retard = TypeAbsence.objects.get(libelle="Retard")

    reponse = client.post(
        NOUVELLE, {"type": retard.pk, "date_debut": "2026-05-30", "date_fin": "2026-05-26"}
    )
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert f'<option value="{retard.pk}" data-categorie="declare" selected>' in contenu
    assert contenu.count(" selected>") == 1
    assert "Le dernier jour ne peut pas précéder le premier." in contenu
    assert AbsenceSalariee.objects.count() == 0


@pytest.mark.parametrize("gabarit", ["absences/mes_absences.html", "absences/nouvelle.html"])
def test_garde_de_source_des_gabarits(gabarit):
    """F-2 : un seul `<script` inline, aucun appel réseau, aucun bloc JSON, aucun `DATA`."""
    source = Path(get_template(gabarit).origin.name).read_text(encoding="utf-8")
    assert source.count("<script") == 1
    for mot in ("fetch(", "planning-data", "DATA", "json_script"):
        assert mot not in source, mot
