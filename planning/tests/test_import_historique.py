"""Recette de l'import d'un planning historique (brique 7a, C7.1).

Trois couches : la forme (`FormulaireImportHistorique`), l'analyse
(`historique.analyser`, qui n'écrit rien), l'écriture (`historique.executer`),
puis l'écran d'admin en deux temps (analyse, confirmation rejouée).

Décisions couvertes : C7.4 (colonne portée par une fiche close, non planifiée,
sans agenda — acceptée), D1 (les trois cas d'un mois déjà couvert), D2-a
(`verifications` sans `verifie_le`), D4 (un seul événement d'audit), D5
(`ActionImpossible` locale), C7.6 (aucun webhook, même avec l'URL posée).

Aucune donnée réelle : personnes et fichier de `planning/tests/fabrique.py` et
`fixtures/import_historique_fictif.json`, qui ne citent qu'elles.
"""

import copy
import io
import json
import logging
import pathlib
from unittest.mock import patch

import pytest

from audit.models import EvenementAudit
from planning import historique, services
from planning.admin import CLE_SESSION_IMPORT_HISTORIQUE, IMPORT_SESSION_MINUTES
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = "/admin/planning/planningversion/importer-historique/"
LISTE = "/admin/planning/planningversion/"
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "import_historique_fictif.json"
MOIS = fabrique.MOIS_HISTORIQUE
# Noms et codes qui ne doivent apparaître ni dans l'audit ni dans les logs.
INTERDITS = ("PRATICIEN", "ASSISTANTE", "SECRETAIRE", "test_pra", "test_ass", "test_sec")


@pytest.fixture
def fiches(db):
    """Les trois fiches fictives, dont la fiche praticien close (C7.4)."""
    return fabrique.personnes_historiques()


@pytest.fixture
def fichier_json():
    """Les octets de la fixture, tels qu'ils seraient téléversés."""
    return FIXTURE.read_bytes()


def _televerser(octets, nom="planning_2026-03.json"):
    """Un téléversement, comme `absences/tests/test_import.py`."""
    flux = io.BytesIO(octets)
    flux.name = nom
    return flux


def _analyse_de(affectations=None, mois=MOIS, **extra):
    return historique.analyser(
        fabrique.planning_exporte(
            mois=mois,
            affectations=(
                affectations
                if affectations is not None
                else fabrique.affectations_historiques()
            ),
            **extra,
        )
    )


def _confirmer(client, empreinte, nb_briques):
    return client.post(
        URL,
        {"confirmer": "1", "empreinte": empreinte, "nb_briques": str(nb_briques)},
    )


# --- Forme du fichier ---------------------------------------------------------


def test_fichier_trop_volumineux(client, cabinet, connecter):
    connecter(client, cabinet)
    gros = b'{"mois": "2026-03", "bourrage": "' + b"x" * (1024 * 1024) + b'"}'

    reponse = client.post(URL, {"fichier": _televerser(gros)})

    assert "trop volumineux" in reponse.content.decode()
    assert CLE_SESSION_IMPORT_HISTORIQUE not in client.session
    assert PlanningVersion.objects.count() == 0


def test_extension_encodage_et_json_illisibles(client, cabinet, connecter, fichier_json):
    connecter(client, cabinet)

    extension = client.post(URL, {"fichier": _televerser(fichier_json, "planning.txt")})
    assert "extension .json" in extension.content.decode()

    pas_utf8 = client.post(URL, {"fichier": _televerser("{}".encode("utf-16"))})
    assert "UTF-8" in pas_utf8.content.decode()

    casse = client.post(URL, {"fichier": _televerser(b"{ceci n'est pas du json")})
    assert "JSON illisible" in casse.content.decode()

    assert PlanningVersion.objects.count() == 0


@pytest.mark.parametrize(
    "fichier, attendu",
    [
        ([], "objet JSON"),
        ({"affectations": {}, "feries": {}, "feries_off": [], "notes": {}}, "« mois »"),
        ({"mois": "2026-13", "affectations": {}, "feries": {}, "feries_off": [], "notes": {}},
         "illisible"),
        ({"mois": "2026-03", "feries": {}, "feries_off": [], "notes": {}}, "« affectations »"),
    ],
)
def test_structure_racine_refusee(fichier, attendu, fiches):
    analyse = historique.analyser(fichier)

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert any(attendu in erreur for erreur in analyse.erreurs), analyse.erreurs


def test_brique_mal_formee_refusee(fiches):
    """`t` hors J | C, champ manquant, brique non-objet : trois refus de forme."""
    analyse = _analyse_de(
        {
            "2026-03-03": {
                "test_pra": [{"a": False, "s": "test_ass", "t": "X", "x": False}],
                "secretariat": [{"a": False, "t": "J", "x": False}],
                "sureffectif": ["pas un objet"],
            }
        }
    )

    assert analyse.verdict == historique.VERDICT_REFUSE
    texte = " | ".join(analyse.erreurs)
    assert "champ « t » hors J | C" in texte
    assert "« s » vide ou illisible" in texte
    assert "objet attendu" in texte


def test_numero_et_exporte_du_fichier_ignores(fiches):
    """La page exporte `numero` et `exporte` : ils ne doivent gêner en rien."""
    planning = fabrique.planning_exporte(affectations=fabrique.affectations_historiques())
    planning["numero"] = 7
    planning["exporte"] = "2026-09-08T17:57:00.000Z"

    analyse = historique.analyser(planning)

    assert analyse.verdict == historique.VERDICT_CREER
    assert set(analyse.state) == {"affectations", "feries", "feries_off", "notes"}


def test_aucun_message_de_forme_ne_cite_un_code(fiches):
    """Les refus structurels citent date, colonne et rang : jamais un code de personne."""
    analyse = _analyse_de(
        {"2026-03-03": {"test_pra": [{"a": False, "s": "test_ass", "t": "X", "x": False}]}}
    )

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert all("test_ass" not in erreur for erreur in analyse.erreurs), analyse.erreurs


# --- Analyse : elle n'écrit rien ----------------------------------------------


def test_analyse_nominale(fiches):
    analyse = _analyse_de()

    assert analyse.verdict == historique.VERDICT_CREER
    assert analyse.peut_confirmer is True
    assert analyse.mois == MOIS
    assert (analyse.debut, analyse.fin) == ("2026-02-23", "2026-04-05")
    assert (analyse.nb_jours, analyse.nb_briques) == (2, 3)
    assert analyse.numero_courant == 0
    assert analyse.erreurs == []
    assert len(analyse.empreinte) == 64
    assert {c["slot"] for c in analyse.colonnes} == {"test_pra", "secretariat"}
    assert {p["code"] for p in analyse.personnes} == {"test_ass", "test_sec"}
    # Rien n'a été écrit, ni version, ni audit.
    assert PlanningVersion.objects.count() == 0
    assert EvenementAudit.objects.count() == 0


def test_colonne_sur_fiche_close_acceptee(fiches):
    """C7.4 : `test_pra` est close, non planifiée et sans agenda — elle garde sa colonne."""
    analyse = _analyse_de()

    colonne = next(c for c in analyse.colonnes if c["slot"] == "test_pra")
    assert analyse.verdict == historique.VERDICT_CREER
    assert colonne["genre"] == "praticien"
    assert colonne["libelle"] == "Test PRATICIEN"
    assert (colonne["inactive"], colonne["non_planifiee"], colonne["sans_agenda"]) == (
        True,
        True,
        True,
    )
    assert any("close" in a for a in analyse.avertissements), analyse.avertissements


def test_code_inconnu_bloquant(fiches):
    """Une colonne et une brique dont le code n'existe pas : deux refus."""
    analyse = _analyse_de(
        {
            "2026-03-03": {"test_inc": [fabrique.brique("test_ass")]},
            "2026-03-04": {"secretariat": [fabrique.brique("autre_inc")]},
        }
    )

    assert analyse.verdict == historique.VERDICT_REFUSE
    texte = " | ".join(analyse.erreurs)
    assert "Colonne « test_inc »" in texte and "Brique « autre_inc »" in texte
    assert PlanningVersion.objects.count() == 0


def test_doublon_personne_jour_bloquant(fiches):
    """Deux postes le même jour pour la même personne : refus, la journée est fausse."""
    analyse = _analyse_de(
        {
            "2026-03-03": {
                "test_pra": [fabrique.brique("test_ass")],
                "secretariat": [fabrique.brique("test_ass", "C")],
            }
        }
    )

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert any("posé 2 fois" in e and "test_ass" in e for e in analyse.erreurs)


def test_jour_hors_plage_bloquant(fiches):
    """La borne est la PLAGE (semaines complètes), pas le mois calendaire."""
    analyse = _analyse_de(
        {
            "2026-02-23": {"test_pra": [fabrique.brique("test_ass")]},   # lundi de bord : accepté
            "2026-04-05": {"secretariat": [fabrique.brique("test_sec")]},  # dimanche de bord : accepté
            "2026-04-06": {"test_pra": [fabrique.brique("test_ass")]},   # hors plage
        }
    )

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert [e for e in analyse.erreurs if "hors de la plage" in e] == [
        "2026-04-06 : jour hors de la plage du mois (2026-02-23 au 2026-04-05)."
    ]


def test_jours_de_bord_seuls_acceptes(fiches):
    """Sans le jour fautif, les deux jours de bord passent : ils sont dans la plage."""
    analyse = _analyse_de(
        {
            "2026-02-23": {"test_pra": [fabrique.brique("test_ass")]},
            "2026-04-05": {"secretariat": [fabrique.brique("test_sec")]},
        }
    )

    assert analyse.verdict == historique.VERDICT_CREER
    assert analyse.erreurs == []


def test_jour_ferie_porteur_avertit_sans_bloquer(fiches):
    """Le 1er janvier 2026 est férié : le cabinet a pu ouvrir, ce n'est pas un refus."""
    analyse = _analyse_de(
        {"2026-01-01": {"test_pra": [fabrique.brique("test_ass")]}},
        mois=fabrique.MOIS_FERIE,
    )

    assert analyse.verdict == historique.VERDICT_CREER
    assert analyse.erreurs == []
    assert any("jour fermé ou férié" in a for a in analyse.avertissements)


def test_fichier_sans_brique_refuse(fiches):
    analyse = _analyse_de({})

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert any("aucune brique" in e for e in analyse.erreurs)


# --- Décision D1 : le mois porte déjà une version -----------------------------


def test_d1_version_vivante_refuse(client, cabinet, fiches):
    """D1-(1) : une version enregistrée par l'application interdit l'import."""
    services.enregistrer(MOIS, 0, fabrique.etat(), cabinet)

    analyse = _analyse_de()

    assert analyse.verdict == historique.VERDICT_REFUSE
    assert any("porte déjà une version enregistrée" in e for e in analyse.erreurs)


def test_d1_meme_fichier_deja_presente(cabinet, fiches):
    """D1-(2) : même état → « déjà présente », et `executer` n'écrit rien."""
    historique.executer(_analyse_de(), cabinet)
    EvenementAudit.objects.all().delete()

    analyse = _analyse_de()
    assert analyse.verdict == historique.VERDICT_DEJA_PRESENTE
    assert analyse.peut_confirmer is False

    assert historique.executer(analyse, cabinet) is None
    assert PlanningVersion.objects.count() == 1
    assert EvenementAudit.objects.count() == 0


def test_d1_reexport_du_meme_contenu_deja_presente(cabinet, fiches):
    """L'empreinte porte sur l'état, pas sur les octets : `exporte` peut changer."""
    historique.executer(_analyse_de(), cabinet)

    planning = fabrique.planning_exporte(affectations=fabrique.affectations_historiques())
    planning["exporte"] = "2026-12-31T23:59:59.000Z"
    planning["numero"] = 42

    assert historique.analyser(planning).verdict == historique.VERDICT_DEJA_PRESENTE


def test_d1_fichier_different_donne_une_version_suivante(cabinet, fiches):
    """D1-(3) : la correction d'un mois historique est une version de plus."""
    historique.executer(_analyse_de(), cabinet)

    corrige = copy.deepcopy(fabrique.affectations_historiques())
    corrige["2026-03-04"]["secretariat"] = [fabrique.brique("test_sec", "C")]
    analyse = _analyse_de(corrige)
    assert analyse.verdict == historique.VERDICT_CREER
    assert analyse.numero_courant == 1

    version = historique.executer(analyse, cabinet)

    assert (version.numero, version.version_de_base) == (2, 1)
    assert services.version_publiee(MOIS).numero == 2
    assert PlanningVersion.objects.filter(mois=MOIS).count() == 2


# --- Écriture -----------------------------------------------------------------


def test_executer_cree_une_version_publiee_historique(cabinet, fiches, caplog):
    analyse = _analyse_de()

    with caplog.at_level(logging.INFO, logger="planning.historique"):
        version = historique.executer(analyse, cabinet)

    assert (version.mois, version.numero, version.version_de_base) == (MOIS, 1, 0)
    assert version.publiee is True
    assert version.publie_par == cabinet and version.auteur == cabinet
    assert version.publie_le is not None
    assert version.state == analyse.state
    assert set(version.state) == {"affectations", "feries", "feries_off", "notes"}
    assert services.est_historique(version) is True
    assert services.version_publiee(MOIS) == version
    assert "planning historique 2026-03 : version 1 importee (3 briques, 2 jours)" in caplog.text


def test_verifications_sans_verifie_le(cabinet, fiches):
    """D2-a : le marqueur remplace `verifie_le` — rien n'a été vérifié."""
    version = historique.executer(_analyse_de(), cabinet)

    assert set(version.verifications) == {
        "historique",
        "importe_le",
        "empreinte",
        "imports",
        "nb_briques",
        "nb_jours",
    }
    assert version.verifications["historique"] is True
    assert version.verifications["imports"] == []      # C6.9 : aucun effectif calculable
    assert version.verifications["nb_briques"] == 3
    assert version.verifications["nb_jours"] == 2
    assert len(version.verifications["empreinte"]) == 64
    assert "verifie_le" not in version.verifications


def test_aucune_reverification_des_regles(cabinet, fiches):
    """Un état que `verifier` refuserait passe : sans présences, la règle est sans objet."""
    from planning import donnees, verification

    analyse = _analyse_de()
    version = historique.executer(analyse, cabinet)

    violations = verification.verifier(donnees.construire(MOIS), version.state)
    assert violations, "le jeu doit bien être invalide au sens des règles"
    assert version.publiee is True


def test_aucun_webhook_meme_avec_l_url_posee(cabinet, fiches, settings):
    """C7.6 : publier un mois de 2026 ne prévient personne. Sans URL, le test serait faux."""
    settings.N8N_PLANNING_WEBHOOK_URL = "http://n8n.example.org/webhook/planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"

    with patch("socle.client_n8n.requests.post") as poste:
        version = historique.executer(_analyse_de(), cabinet)

    poste.assert_not_called()
    assert version.publiee is True


def test_un_seul_evenement_d_audit_sans_nom(cabinet, fiches):
    """D4 : un fichier = une version = un événement."""
    analyse = _analyse_de()

    version = historique.executer(analyse, cabinet)

    evenement = EvenementAudit.objects.get(action="planning_historique_importe")
    assert EvenementAudit.objects.count() == 1
    assert evenement.qui == cabinet
    assert evenement.type_objet == "PlanningVersion"
    assert evenement.id_objet == str(version.pk)
    assert evenement.details == {
        "mois": MOIS,
        "numero": 1,
        "nb_briques": 3,
        "nb_jours": 2,
        "empreinte": analyse.empreinte,
    }
    texte = json.dumps(evenement.details) + json.dumps(version.verifications)
    for interdit in INTERDITS:
        assert interdit not in texte, interdit


def test_executer_refuse_un_rapport_en_erreur(cabinet, fiches):
    analyse = _analyse_de({"2026-03-03": {"test_inc": [fabrique.brique("test_ass")]}})

    with pytest.raises(historique.ActionImpossible):
        historique.executer(analyse, cabinet)

    assert PlanningVersion.objects.count() == 0
    assert EvenementAudit.objects.count() == 0


def test_version_apparue_entre_l_analyse_et_l_ecriture(cabinet, fiches):
    """La contrainte unique `(mois, numero)` sérialise : refus net, jamais un 500."""
    analyse = _analyse_de()
    PlanningVersion.objects.create(mois=MOIS, numero=1, state=fabrique.etat())

    with pytest.raises(historique.ActionImpossible) as refus:
        historique.executer(analyse, cabinet)

    assert "entre-temps" in str(refus.value)
    assert PlanningVersion.objects.filter(publiee=True).count() == 0


# --- Écran d'admin ------------------------------------------------------------


def test_vue_refusee_aux_autres_roles(client, principale, salariee, connecter):
    connecter(client, principale)
    assert client.get(URL).status_code == 403
    refus = EvenementAudit.objects.get(action="acces_refuse")
    assert refus.qui_id == principale.pk
    assert refus.details == {"vue": "vue_import_historique"}

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
    session[CLE_SESSION_IMPORT_HISTORIQUE] = {"empreinte": "x", "depuis": "", "planning": {}}
    session.save()

    reponse = client.get(URL)

    assert reponse.status_code == 200
    assert 'name="fichier"' in reponse.content.decode()
    assert CLE_SESSION_IMPORT_HISTORIQUE not in client.session


def test_bouton_dans_la_liste(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = client.get(LISTE)

    assert reponse.status_code == 200
    assert URL in reponse.content.decode()


def test_analyse_rend_le_rapport_sans_ecrire(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)

    reponse = client.post(URL, {"fichier": _televerser(fichier_json)})

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert "Rapport d'analyse" in contenu and "à importer" in contenu
    assert 'name="confirmer"' in contenu and 'name="nb_briques" value="3"' in contenu
    assert "Test PRATICIEN" in contenu and "close" in contenu   # la colonne C7.4
    assert PlanningVersion.objects.count() == 0
    assert EvenementAudit.objects.filter(action__startswith="planning").count() == 0
    etat = client.session[CLE_SESSION_IMPORT_HISTORIQUE]
    assert etat["planning"]["mois"] == MOIS
    assert len(etat["empreinte"]) == 64


def test_confirmation_ecrit_la_version(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    empreinte = client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"]

    reponse = _confirmer(client, empreinte, nb_briques=3)

    assert reponse.status_code == 200
    assert "Import terminé" in reponse.content.decode()
    version = PlanningVersion.objects.get()
    assert (version.mois, version.numero) == (MOIS, 1)
    assert version.publiee is True and services.est_historique(version)
    assert version.state["affectations"]["2026-03-03"]["test_pra"] == [
        {"a": False, "s": "test_ass", "t": "J", "x": False}
    ]
    assert EvenementAudit.objects.filter(action="planning_historique_importe").count() == 1
    assert CLE_SESSION_IMPORT_HISTORIQUE not in client.session


def test_rejouer_le_fichier_n_ecrit_rien(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    _confirmer(client, client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"], 3)

    reponse = client.post(URL, {"fichier": _televerser(fichier_json)})

    contenu = reponse.content.decode()
    assert "Déjà présente" in contenu
    assert 'name="confirmer"' not in contenu
    assert PlanningVersion.objects.count() == 1


def test_mauvaise_empreinte_refusee(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})

    reponse = _confirmer(client, "0" * 64, nb_briques=3)

    assert reponse.status_code == 200
    assert "Aucune analyse en cours" in reponse.content.decode()
    assert PlanningVersion.objects.count() == 0
    assert CLE_SESSION_IMPORT_HISTORIQUE not in client.session


def test_confirmation_sans_analyse_refusee(client, cabinet, connecter):
    connecter(client, cabinet)

    reponse = _confirmer(client, "abc", nb_briques=1)

    assert reponse.status_code == 200
    assert "Aucune analyse en cours" in reponse.content.decode()
    assert PlanningVersion.objects.count() == 0


def test_session_perimee_refusee(client, cabinet, connecter, fiches, fichier_json):
    import datetime

    from django.utils import timezone

    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    session = client.session
    etat = session[CLE_SESSION_IMPORT_HISTORIQUE]
    empreinte = etat["empreinte"]
    etat["depuis"] = (
        timezone.now() - datetime.timedelta(minutes=IMPORT_SESSION_MINUTES + 1)
    ).isoformat()
    session[CLE_SESSION_IMPORT_HISTORIQUE] = etat
    session.save()

    reponse = _confirmer(client, empreinte, nb_briques=3)

    assert f"plus de {IMPORT_SESSION_MINUTES} minutes" in reponse.content.decode()
    assert PlanningVersion.objects.count() == 0
    assert CLE_SESSION_IMPORT_HISTORIQUE not in client.session


def test_comptage_cache_divergent_refuse(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    empreinte = client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"]

    reponse = _confirmer(client, empreinte, nb_briques=99)

    assert "La base a changé depuis" in reponse.content.decode()
    assert PlanningVersion.objects.count() == 0


def test_base_changee_entre_les_deux_post(client, cabinet, connecter, fiches, fichier_json):
    """Une version enregistrée depuis un autre onglet : l'analyse rejouée refuse."""
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    empreinte = client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"]
    services.enregistrer(MOIS, 0, fabrique.etat(), cabinet)

    reponse = _confirmer(client, empreinte, nb_briques=3)

    contenu = reponse.content.decode()
    assert "La base a changé depuis" in contenu
    assert "porte déjà une version enregistrée" in contenu
    assert PlanningVersion.objects.filter(publiee=True).count() == 0


def test_action_impossible_devient_un_message(client, cabinet, connecter, fiches, fichier_json):
    connecter(client, cabinet)
    client.post(URL, {"fichier": _televerser(fichier_json)})
    empreinte = client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"]

    with patch(
        "planning.historique.executer",
        side_effect=historique.ActionImpossible("Refus de test : rien importé."),
    ):
        reponse = _confirmer(client, empreinte, nb_briques=3)

    assert reponse.status_code == 200
    assert "Refus de test : rien importé." in reponse.content.decode()
    assert PlanningVersion.objects.count() == 0


def test_les_logs_de_l_ecran_restent_muets(client, cabinet, connecter, fiches, fichier_json, caplog):
    connecter(client, cabinet)

    with caplog.at_level(logging.INFO):
        client.post(URL, {"fichier": _televerser(fichier_json)})
        _confirmer(client, client.session[CLE_SESSION_IMPORT_HISTORIQUE]["empreinte"], 3)

    assert "import planning historique : analyse 2026-03, verdict creer, 0 refus" in caplog.text
    assert "planning historique 2026-03 : version 1 importee" in caplog.text
    for interdit in INTERDITS:
        assert interdit not in caplog.text, interdit
