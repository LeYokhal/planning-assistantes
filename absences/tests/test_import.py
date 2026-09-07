"""Recette de la reprise exceptionnelle de l'existant Notion (brique 3-quater, C3.9).

Trois couches : le service `importer` (une absence effective, sans webhook ni
crochet de conflit), l'analyse `analyser_import` (verdicts, sans écrire),
l'écriture `executer_import` (tout ou rien), puis l'écran d'admin en deux temps
(analyse, confirmation rejouée).

Aucune donnée réelle : personnes de la fabrique, fichier `import_fictif.json`
qui ne cite qu'elles.
"""

import datetime
import hashlib
import io
import logging
import pathlib
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from absences import services
from absences.admin import CLE_SESSION_IMPORT, IMPORT_SESSION_MINUTES
from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique
from audit.models import EvenementAudit
from planning import services as planning_services
from planning.models import PlanningVersion

pytestmark = pytest.mark.django_db

URL = "/admin/absences/absencesalariee/importer/"
LISTE = "/admin/absences/absencesalariee/"
FIXTURE = pathlib.Path(__file__).with_name("import_fictif.json")
DEBUT = datetime.date(2026, 5, 26)
FIN = datetime.date(2026, 5, 30)
DEMANDE = TypeAbsence.Categorie.DEMANDE
DECLARE = TypeAbsence.Categorie.DECLARE
VALIDEE = AbsenceSalariee.Statut.VALIDEE
DECLAREE = AbsenceSalariee.Statut.DECLAREE
EN_ATTENTE = AbsenceSalariee.Statut.EN_ATTENTE


def _fichier(octets, nom="absences.json"):
    """Un téléversement, comme `personnes/tests/test_pages.py`."""
    flux = io.BytesIO(octets)
    flux.name = nom
    return flux


def _ligne(
    nom="DUPONT",
    prenom="Alice",
    type_="Congé payé",
    debut="2026-05-26",
    fin="2026-05-30",
    ref="notion:a1",
):
    """Une ligne du fichier, telle que le formulaire la normalise."""
    return {
        "ref": ref,
        "nom": nom,
        "prenom": prenom,
        "type": type_,
        "debut": debut,
        "fin": fin,
    }


def _version_publiee(personne, iso="2026-05-26", mois="2026-05"):
    """Un planning publié posant une brique de la personne ce jour-là (patron 4b)."""
    return PlanningVersion.objects.create(
        mois=mois,
        numero=1,
        publiee=True,
        state={
            "affectations": {
                iso: {"secretariat": [{"s": personne.code, "t": "J", "x": False, "a": False}]}
            },
            "feries": {},
            "feries_off": [],
            "notes": {},
        },
    )


def _confirmer(client, empreinte, creer, deja_presente=0):
    return client.post(
        URL,
        {
            "confirmer": "1",
            "empreinte": empreinte,
            "nb_creer": str(creer),
            "nb_deja_presente": str(deja_presente),
        },
    )


@pytest.fixture
def alice(db):
    return fabrique.personne(nom="DUPONT", prenom="Alice")


@pytest.fixture
def conge(db):
    return fabrique.type_absence(
        libelle="Congé payé", categorie=DEMANDE, bloquant=True, paie=True
    )


@pytest.fixture
def maladie(db):
    return fabrique.type_absence(
        libelle="Maladie", categorie=DECLARE, bloquant=True, paie=True
    )


@pytest.fixture
def jeu(alice, conge, maladie):
    """Les octets de la fixture, et tout ce qu'elle cite : deux salariées, trois types."""
    fabrique.personne(nom="MARTIN", prenom="Bob")
    fabrique.type_absence(libelle="Retard", categorie=DECLARE, bloquant=False, paie=False)
    return FIXTURE.read_bytes()


@pytest.fixture
def webhook_actif(settings):
    settings.N8N_ABSENCE_WEBHOOK_URL = "http://n8n.example.org/webhook/absence"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"
    settings.APP_URL = "http://testserver"


# --- importer ----------------------------------------------------------------


def test_importer_type_demande_nait_validee(cabinet, alice, conge):
    absence, signal = services.importer(alice, conge, DEBUT, FIN, cabinet, ref="notion:a1")

    absence.refresh_from_db()
    assert absence.statut == VALIDEE
    assert absence.effective is True
    assert absence.auteur == cabinet
    assert absence.decide_par == cabinet
    assert absence.decide_le is not None
    assert absence.precision == ""
    assert absence.jours_comptes == Decimal("4.0")
    assert absence.jours_comptes_calcules == Decimal("4.0")
    assert len(absence.jours_retenus) == 4
    assert signal == ""


def test_importer_type_declare_nait_declaree(cabinet, alice, maladie):
    absence, _ = services.importer(alice, maladie, DEBUT, FIN, cabinet)

    absence.refresh_from_db()
    assert absence.statut == DECLAREE
    assert absence.decide_par is None
    assert absence.decide_le is None
    assert absence.jours_comptes == Decimal("4.0")


def test_importer_un_seul_save(cabinet, alice, conge):
    with patch.object(
        AbsenceSalariee, "save", autospec=True, side_effect=AbsenceSalariee.save
    ) as save:
        services.importer(alice, conge, DEBUT, FIN, cabinet)

    assert save.call_count == 1


def test_importer_pose_l_echeance_de_retention(cabinet, alice, conge, settings):
    settings.RETENTION_ABSENCES_JOURS = "30"

    absence, _ = services.importer(alice, conge, DEBUT, FIN, cabinet)

    assert absence.a_effacer_le == timezone.localdate() + datetime.timedelta(days=30)


def test_importer_signale_un_contrat_incomplet(cabinet, conge):
    sans_contrat = fabrique.personne(nom="BERNARD", prenom="Chloe", heures_hebdo=None)

    absence, signal = services.importer(sans_contrat, conge, DEBUT, FIN, cabinet)

    assert signal == "sans_contrat"
    assert absence.jours_comptes == Decimal("0.0")


def test_importer_sans_webhook_ni_signalement_de_conflit(
    cabinet, alice, maladie, webhook_actif
):
    _version_publiee(alice)

    with patch("socle.client_n8n.poster") as poster:
        services.importer(alice, maladie, DEBUT, FIN, cabinet)

    poster.assert_not_called()
    assert not EvenementAudit.objects.filter(action="absence_conflit_publication").exists()


def test_importer_journalise_identifiants_et_reference(cabinet, alice, conge):
    absence, _ = services.importer(alice, conge, DEBUT, FIN, cabinet, ref="notion:a1,a2")

    evenement = EvenementAudit.objects.get(action="absence_importee")
    assert evenement.qui_id == cabinet.pk
    assert evenement.type_objet == "AbsenceSalariee"
    assert evenement.id_objet == str(absence.pk)
    assert evenement.details == {
        "personne_id": alice.pk,
        "statut": "validee",
        "jours_comptes": "4.0",
        "ref": "notion:a1,a2",
    }


def test_importer_refuse_un_praticien(cabinet, conge):
    with pytest.raises(services.ActionImpossible):
        services.importer(fabrique.praticien(), conge, DEBUT, FIN, cabinet)


def test_importer_refuse_des_dates_inversees(cabinet, alice, conge):
    with pytest.raises(services.ActionImpossible):
        services.importer(alice, conge, FIN, DEBUT, cabinet)


# --- analyser_import ---------------------------------------------------------


def test_analyse_ligne_a_creer(alice, conge):
    [ligne] = services.analyser_import([_ligne(ref="notion:a1")])

    assert ligne["verdict"] == "creer"
    assert ligne["motif"] == ""
    assert ligne["personne"] == alice
    assert ligne["type"] == conge
    assert ligne["debut"] == DEBUT
    assert ligne["fin"] == FIN
    assert ligne["statut"] == "validee"
    assert ligne["statut_libelle"] == "Validée"
    assert ligne["jours"] == Decimal("4.0")
    assert ligne["signal"] == ""
    assert ligne["conflits"] == []
    assert ligne["ref"] == "notion:a1"
    assert ligne["verdict_libelle"] == "à créer"


def test_analyse_n_ecrit_rien(alice, conge):
    services.analyser_import([_ligne()])

    assert AbsenceSalariee.objects.count() == 0
    assert EvenementAudit.objects.count() == 0


def test_analyse_statut_prevu_selon_la_categorie(alice, maladie):
    [ligne] = services.analyser_import([_ligne(type_="Maladie")])

    assert ligne["statut"] == "declaree"


def test_analyse_personne_inconnue(conge):
    [ligne] = services.analyser_import([_ligne(nom="INCONNUE", prenom="Zoe")])

    assert ligne["verdict"] == "erreur"
    assert "personne inconnue" in ligne["motif"]
    assert ligne["personne"] is None
    assert ligne["jours"] is None


def test_analyse_personne_strippee_mais_casse_exacte(alice, conge):
    strippee, casse = services.analyser_import(
        [_ligne(nom=" DUPONT ", prenom="Alice "), _ligne(nom="Dupont", prenom="Alice")]
    )

    assert strippee["verdict"] == "creer"
    assert casse["verdict"] == "erreur"
    assert "personne inconnue" in casse["motif"]


def test_analyse_praticien(conge):
    praticien = fabrique.praticien()

    [ligne] = services.analyser_import([_ligne(nom=praticien.nom, prenom=praticien.prenom)])

    assert ligne["verdict"] == "erreur"
    assert "non salariée" in ligne["motif"]


def test_analyse_type_inconnu_vide_ou_inactif(alice, conge):
    fabrique.type_absence(libelle="Type éteint", categorie=DECLARE, actif=False)

    inconnu, vide, inactif = services.analyser_import(
        [_ligne(type_="Type inexistant"), _ligne(type_=""), _ligne(type_="Type éteint")]
    )

    assert "type inconnu" in inconnu["motif"]
    assert "type vide" in vide["motif"]
    assert "type inactif" in inactif["motif"]
    assert {inconnu["verdict"], vide["verdict"], inactif["verdict"]} == {"erreur"}


def test_analyse_dates_illisibles_ou_inversees(alice, conge):
    illisible, inversee = services.analyser_import(
        [_ligne(debut="26/05/2026"), _ligne(debut="2026-05-30", fin="2026-05-26")]
    )

    assert "date illisible" in illisible["motif"]
    assert "précède" in inversee["motif"]
    assert {illisible["verdict"], inversee["verdict"]} == {"erreur"}
    assert illisible["jours"] is None


def test_analyse_signale_un_contrat_incomplet_sans_bloquer(conge):
    fabrique.personne(nom="BERNARD", prenom="Chloe", heures_hebdo=None)

    [ligne] = services.analyser_import([_ligne(nom="BERNARD", prenom="Chloe")])

    assert ligne["verdict"] == "creer"
    assert ligne["jours"] == Decimal("0.0")
    assert ligne["signal"] == "sans_contrat"
    assert "Contrat incomplet" in ligne["message"]


def test_analyse_identique_deja_presente(alice, conge):
    fabrique.absence(alice, conge, DEBUT, FIN, statut=VALIDEE)

    [ligne] = services.analyser_import([_ligne()])

    assert ligne["verdict"] == "deja_presente"
    assert ligne["motif"] == ""
    assert ligne["conflits"] == []


def test_analyse_chevauchement_effectif_non_identique(alice, conge, maladie):
    fabrique.absence(
        alice, conge, datetime.date(2026, 5, 27), datetime.date(2026, 5, 28), statut=VALIDEE
    )
    fabrique.absence(
        alice, maladie, datetime.date(2026, 6, 2), datetime.date(2026, 6, 2), statut=DECLAREE
    )

    partiel, autre_type = services.analyser_import(
        [_ligne(), _ligne(type_="Congé payé", debut="2026-06-02", fin="2026-06-02")]
    )

    assert partiel["verdict"] == "erreur"
    assert "absence effective" in partiel["motif"]
    assert autre_type["verdict"] == "erreur"
    assert "absence effective" in autre_type["motif"]


def test_analyse_chevauchement_en_attente(alice, conge):
    demande = fabrique.absence(alice, conge, DEBUT, FIN, statut=EN_ATTENTE)

    [ligne] = services.analyser_import([_ligne()])

    assert ligne["verdict"] == "erreur"
    assert ligne["motif"] == f"chevauche la demande en attente #{demande.pk}"


def test_analyse_refusee_et_annulee_ignorees(alice, conge):
    fabrique.absence(alice, conge, DEBUT, FIN, statut=AbsenceSalariee.Statut.REFUSEE)
    fabrique.absence(alice, conge, DEBUT, FIN, statut=AbsenceSalariee.Statut.ANNULEE)

    [ligne] = services.analyser_import([_ligne()])

    assert ligne["verdict"] == "creer"


def test_analyse_doublon_dans_le_fichier(alice, conge, maladie):
    premiere, seconde, autre = services.analyser_import(
        [
            _ligne(),
            _ligne(type_="Maladie", debut="2026-05-28", fin="2026-05-29", ref="notion:a2"),
            _ligne(debut="2026-06-02", fin="2026-06-03", ref="notion:a3"),
        ]
    )

    assert premiere["verdict"] == "erreur"
    assert premiere["motif"] == "chevauche la ligne 2 du fichier"
    assert seconde["verdict"] == "erreur"
    assert seconde["motif"] == "chevauche la ligne 1 du fichier"
    assert autre["verdict"] == "creer"


def test_analyse_conflit_publie_liste(alice, conge):
    _version_publiee(alice)

    [ligne] = services.analyser_import([_ligne()])

    assert ligne["verdict"] == "creer"
    assert ligne["conflits"] == [{"mois": "2026-05", "numero": 1, "dates": ["2026-05-26"]}]


def test_analyse_conflit_ignore_pour_un_type_non_bloquant(alice):
    fabrique.type_absence(libelle="Retard", categorie=DECLARE, bloquant=False, paie=False)
    _version_publiee(alice)

    [ligne] = services.analyser_import([_ligne(type_="Retard")])

    assert ligne["verdict"] == "creer"
    assert ligne["conflits"] == []


def test_analyse_conflit_non_calcule_pour_une_ligne_deja_presente(alice, conge):
    _version_publiee(alice)
    fabrique.absence(alice, conge, DEBUT, FIN, statut=VALIDEE)

    [ligne] = services.analyser_import([_ligne()])

    assert ligne["verdict"] == "deja_presente"
    assert ligne["conflits"] == []


def test_analyse_partage_un_seul_cache_de_versions(alice, conge):
    bob = fabrique.personne(nom="MARTIN", prenom="Bob")
    _version_publiee(alice)

    with patch(
        "planning.services.version_publiee", wraps=planning_services.version_publiee
    ) as lecture:
        pour_alice, pour_bob = services.analyser_import(
            [_ligne(), _ligne(nom=bob.nom, prenom=bob.prenom, ref="notion:b1")]
        )

    assert lecture.call_count == 1
    assert pour_alice["conflits"]
    assert pour_bob["conflits"] == []


def test_compter_verdicts(alice, conge):
    fabrique.absence(alice, conge, DEBUT, FIN, statut=VALIDEE)
    lignes = services.analyser_import(
        [_ligne(), _ligne(debut="2026-06-02", fin="2026-06-03"), _ligne(nom="X", prenom="Y")]
    )

    assert services.compter_verdicts(lignes) == {
        "creer": 1,
        "deja_presente": 1,
        "erreur": 1,
    }


# --- executer_import ---------------------------------------------------------


def test_execution_refuse_s_il_reste_une_erreur(cabinet, alice, conge):
    lignes = services.analyser_import([_ligne(), _ligne(nom="INCONNUE", prenom="Zoe")])

    with pytest.raises(services.ActionImpossible):
        services.executer_import(lignes, cabinet, "empreinte")

    assert AbsenceSalariee.objects.count() == 0
    assert EvenementAudit.objects.count() == 0


def test_execution_tout_ou_rien(cabinet, alice, conge, maladie):
    lignes = services.analyser_import(
        [_ligne(), _ligne(type_="Maladie", debut="2026-06-02", fin="2026-06-03", ref="notion:a2")]
    )
    original = services.importer
    appels = []

    def bancal(*args, **kwargs):
        appels.append(1)
        if len(appels) == 2:
            raise RuntimeError("panne au milieu")
        return original(*args, **kwargs)

    with patch("absences.services.importer", side_effect=bancal), pytest.raises(RuntimeError):
        services.executer_import(lignes, cabinet, "empreinte")

    assert AbsenceSalariee.objects.count() == 0
    assert not EvenementAudit.objects.filter(
        action__in=["absence_importee", "import_absences"]
    ).exists()


def test_execution_ecrit_ignore_et_journalise(cabinet, alice, conge, maladie):
    fabrique.absence(
        alice, maladie, datetime.date(2026, 6, 2), datetime.date(2026, 6, 3), statut=DECLAREE
    )
    lignes = services.analyser_import(
        [_ligne(), _ligne(type_="Maladie", debut="2026-06-02", fin="2026-06-03", ref="notion:a2")]
    )

    resultat = services.executer_import(lignes, cabinet, "abc123")

    assert resultat == {"nb_creees": 1, "nb_ignorees": 1}
    assert AbsenceSalariee.objects.count() == 2
    assert AbsenceSalariee.objects.filter(type=conge, statut=VALIDEE).count() == 1
    assert EvenementAudit.objects.filter(action="absence_importee").count() == 1
    evenement = EvenementAudit.objects.get(action="import_absences")
    assert evenement.qui_id == cabinet.pk
    assert evenement.details == {"nb_creees": 1, "nb_ignorees": 1, "empreinte": "abc123"}


# --- Écran d'admin -----------------------------------------------------------


def test_vue_refusee_aux_autres_roles(client, principale, salariee, connecter):
    connecter(client, principale)
    assert client.get(URL).status_code == 403
    refus = EvenementAudit.objects.get(action="acces_refuse")
    assert refus.qui_id == principale.pk
    assert refus.details == {"vue": "vue_import"}

    client.logout()
    connecter(client, salariee)
    assert client.get(URL).status_code == 403
    assert client.post(URL, {"confirmer": "1"}).status_code == 403


def test_vue_redirige_un_anonyme(client, db):
    reponse = client.get(URL)

    assert reponse.status_code == 302
    assert reponse["Location"].startswith("/connexion/")


def test_get_affiche_le_formulaire_et_vide_la_session(client, cabinet, connecter):
    connecter(client, cabinet)
    session = client.session
    session[CLE_SESSION_IMPORT] = {"empreinte": "x", "depuis": "", "absences": []}
    session.save()

    reponse = client.get(URL)

    assert reponse.status_code == 200
    assert 'name="fichier"' in reponse.content.decode()
    assert CLE_SESSION_IMPORT not in client.session


def test_bouton_dans_la_liste(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = client.get(LISTE)

    assert reponse.status_code == 200
    assert URL in reponse.content.decode()


def test_analyse_rend_le_rapport_sans_ecrire(client, cabinet, connecter, jeu):
    connecter(client, cabinet)

    reponse = client.post(URL, {"fichier": _fichier(jeu)})

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert contenu.count("à créer") >= 3
    assert 'name="confirmer"' in contenu
    assert 'name="nb_creer" value="3"' in contenu
    assert AbsenceSalariee.objects.count() == 0
    assert EvenementAudit.objects.filter(action__startswith="absence").count() == 0
    etat = client.session[CLE_SESSION_IMPORT]
    assert etat["empreinte"] == hashlib.sha256(jeu).hexdigest()
    assert len(etat["absences"]) == 3
    assert etat["absences"][0]["nom"] == "DUPONT"


def test_confirmation_ecrit_tout(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    empreinte = client.session[CLE_SESSION_IMPORT]["empreinte"]

    reponse = _confirmer(client, empreinte, creer=3)

    assert reponse.status_code == 200
    assert "Import terminé" in reponse.content.decode()
    assert AbsenceSalariee.objects.count() == 3
    conge = AbsenceSalariee.objects.get(type__libelle="Congé payé")
    assert conge.statut == VALIDEE
    assert conge.decide_par == cabinet
    assert conge.jours_comptes == Decimal("4.0")
    maladie = AbsenceSalariee.objects.get(type__libelle="Maladie")
    assert maladie.statut == DECLAREE
    assert maladie.personne.nom == "MARTIN"
    assert maladie.jours_comptes == Decimal("2.0")
    retard = AbsenceSalariee.objects.get(type__libelle="Retard")
    assert retard.statut == DECLAREE
    assert retard.jours_comptes == Decimal("1.0")
    assert EvenementAudit.objects.filter(action="absence_importee").count() == 3
    bilan = EvenementAudit.objects.get(action="import_absences")
    assert bilan.details == {"nb_creees": 3, "nb_ignorees": 0, "empreinte": empreinte}
    assert CLE_SESSION_IMPORT not in client.session


def test_rejouer_le_fichier_ne_cree_rien(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    _confirmer(client, client.session[CLE_SESSION_IMPORT]["empreinte"], creer=3)

    reponse = client.post(URL, {"fichier": _fichier(jeu)})

    contenu = reponse.content.decode()
    assert contenu.count("déjà présente") >= 3
    assert 'name="confirmer"' not in contenu
    assert "Aucune absence à créer" in contenu
    assert AbsenceSalariee.objects.count() == 3


def test_mauvaise_empreinte_refusee(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})

    reponse = _confirmer(client, "0" * 64, creer=3)

    assert reponse.status_code == 200
    assert "Aucune analyse en cours" in reponse.content.decode()
    assert AbsenceSalariee.objects.count() == 0
    assert CLE_SESSION_IMPORT not in client.session


def test_confirmation_sans_analyse_refusee(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = _confirmer(client, "abc", creer=1)

    assert reponse.status_code == 200
    assert "Aucune analyse en cours" in reponse.content.decode()


def test_session_perimee_refusee(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    session = client.session
    etat = session[CLE_SESSION_IMPORT]
    etat["depuis"] = (
        timezone.now() - datetime.timedelta(minutes=IMPORT_SESSION_MINUTES + 5)
    ).isoformat()
    session[CLE_SESSION_IMPORT] = etat
    session.save()

    reponse = _confirmer(client, etat["empreinte"], creer=3)

    assert reponse.status_code == 200
    assert "minutes" in reponse.content.decode()
    assert AbsenceSalariee.objects.count() == 0
    assert CLE_SESSION_IMPORT not in client.session


def test_base_changee_entre_les_deux_post(client, cabinet, connecter, jeu, alice, maladie):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    empreinte = client.session[CLE_SESSION_IMPORT]["empreinte"]
    # Une déclaration saisie entre-temps chevauche la première ligne du fichier.
    fabrique.absence(
        alice, maladie, datetime.date(2026, 5, 27), datetime.date(2026, 5, 27), statut=DECLAREE
    )

    reponse = _confirmer(client, empreinte, creer=3)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "La base a changé" in contenu
    assert "absence effective" in contenu
    assert AbsenceSalariee.objects.count() == 1
    assert not EvenementAudit.objects.filter(action="import_absences").exists()
    assert CLE_SESSION_IMPORT in client.session


def test_compteurs_differents_refuses(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    empreinte = client.session[CLE_SESSION_IMPORT]["empreinte"]

    reponse = _confirmer(client, empreinte, creer=2)

    assert "La base a changé" in reponse.content.decode()
    assert AbsenceSalariee.objects.count() == 0
    assert 'name="nb_creer" value="3"' in reponse.content.decode()


def test_fichier_trop_volumineux(client, cabinet, connecter):
    connecter(client, cabinet)
    enorme = b'{"absences": [' + b" " * (1024 * 1024) + b"]}"

    reponse = client.post(URL, {"fichier": _fichier(enorme)})

    assert reponse.status_code == 200
    assert "trop volumineux" in reponse.content.decode()
    assert CLE_SESSION_IMPORT not in client.session


def test_fichier_illisible_ou_mal_forme(client, cabinet, connecter):
    connecter(client, cabinet)

    illisible = client.post(URL, {"fichier": _fichier(b"pas du json")})
    assert "JSON illisible" in illisible.content.decode()

    sans_liste = client.post(URL, {"fichier": _fichier(b'{"source": "x"}')})
    assert "absences" in sans_liste.content.decode()

    champ_manquant = client.post(
        URL, {"fichier": _fichier(b'{"absences": [{"nom": "DUPONT"}]}')}
    )
    contenu = champ_manquant.content.decode()
    assert "Ligne 1" in contenu and "prenom" in contenu

    extension = client.post(URL, {"fichier": _fichier(b"{}", nom="absences.txt")})
    assert "extension .json" in extension.content.decode()

    pas_utf8 = client.post(URL, {"fichier": _fichier("{}".encode("utf-16"))})
    assert "UTF-8" in pas_utf8.content.decode()

    assert AbsenceSalariee.objects.count() == 0


def test_action_impossible_devient_un_message(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _fichier(jeu)})
    empreinte = client.session[CLE_SESSION_IMPORT]["empreinte"]

    with patch(
        "absences.services.executer_import",
        side_effect=services.ActionImpossible("Refus de test : rien importé."),
    ):
        reponse = _confirmer(client, empreinte, creer=3)

    assert reponse.status_code == 200
    # L'admin rend les messages par `capfirst` : l'attendu commence en capitale.
    assert "Refus de test : rien importé." in reponse.content.decode()
    assert AbsenceSalariee.objects.count() == 0


def test_les_logs_de_l_ecran_restent_muets(client, cabinet, connecter, jeu, caplog):
    connecter(client, cabinet)

    with caplog.at_level(logging.INFO):
        client.post(URL, {"fichier": _fichier(jeu)})
        _confirmer(client, client.session[CLE_SESSION_IMPORT]["empreinte"], creer=3)

    assert "import absences : analyse, 3 ligne(s), 0 erreur(s)" in caplog.text
    assert "import absences : 3 creee(s), 0 ignoree(s)" in caplog.text
    for interdit in ("DUPONT", "Alice", "MARTIN", "Bob", "Congé", "Maladie", "Retard", "notion:"):
        assert interdit not in caplog.text
