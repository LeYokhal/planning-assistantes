"""Recette de « Mes jours » (brique 4b) : ses jours publiés, rien d'une autre, sans `DATA`.

Décisions D (page serveur minimale, sans `DATA`), P2 (plage entière, mois
calendaire prioritaire pour une date partagée), Q7 (libellé « Prénom Nom »),
P3 (praticiens sans filtre `actif`). La salariée du jeu est BERNARD Emma
(`emma_ber`, celle d'`etat_propre`) ; PETIT Sara est au secrétariat le même jour
et ne doit jamais apparaître.
"""

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from django.template.loader import get_template
from django.utils import timezone

from absences.models import AbsenceSalariee
from absences.tests import fabrique as fabrique_absences
from planning import historique, services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL = f"/mes-jours/{fabrique.MOIS}/"
TYPES = ("Maladie", "Congé payé", "Retard", "Ecole")
# Brique 6b : les noms de `test_confidentialite.py` moins ceux qui ont le droit d'être dans la
# page d'Emma (son prénom, dans la barre ; sa praticienne, dans la fiche), plus les autres
# personnes du jeu fictif.
AUTRES = (
    "ROUX", "Lina", "MOREL", "Lea", "LEROY", "Chloe", "PETIT", "Sara",
    "MARTIN", "Bob", "FONTAINE", "Nora", "GIRARD", "Zoe", "LAMBERT", "Ines",
)
INTERDITS_LEGENDE = TYPES + ("Secrétariat", "conges", "planning-data")
# Brique 6b : ses types ont leur place dans ses fiches ; ces trois-là, nulle part.
PARTOUT_INTERDITS = ("Secrétariat", "conges", "planning-data")
AUJOURD_HUI = datetime.date(2026, 10, 6)


@pytest.fixture
def jeu(cabinet):
    return fabrique.jeu_complet(cabinet)


@pytest.fixture
def emma(salariee, jeu):
    """Le compte salariée rattaché à BERNARD Emma."""
    return fabrique_absences.lier(salariee, jeu["personnes"]["Emma"])


def _publier(cabinet, state=None):
    version = services.enregistrer(fabrique.MOIS, 0, state or fabrique.etat_propre(), cabinet)
    return services.publier(fabrique.MOIS, version.numero, cabinet)


def _version_publiee(mois, numero, affectations):
    """Une version publiée posée directement en base : état non vérifié, voulu."""
    return PlanningVersion.objects.create(
        mois=mois, numero=numero, state=fabrique.etat(affectations), publiee=True
    )


# --- Accès --------------------------------------------------------------------


def test_anonyme_redirige(client, jeu):
    reponse = client.get(URL)
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_cabinet_refuse(client, cabinet, connecter, jeu):
    connecter(client, cabinet)
    assert client.get(URL).status_code == 403


def test_racine_redirige_vers_le_mois_courant(client, salariee, connecter):
    connecter(client, salariee)
    reponse = client.get("/mes-jours/")
    assert reponse.status_code == 302
    assert reponse.url.startswith("/mes-jours/20")


def test_mois_invalide_introuvable(client, salariee, connecter):
    connecter(client, salariee)
    assert client.get("/mes-jours/2026-13/").status_code == 404


def test_lien_dans_l_accueil(client, salariee, cabinet, connecter):
    """Brique 6a : `/` redirige la salariée vers ses jours ; le cabinet n'a pas ce lien."""
    connecter(client, salariee)
    reponse = client.get("/")
    assert reponse.status_code == 302 and reponse["Location"] == "/mes-jours/"
    assert 'href="/mes-jours/"' in client.get(URL).content.decode()
    client.logout()
    connecter(client, cabinet)
    assert 'href="/mes-jours/"' not in client.get("/").content.decode()


# --- Contenu ------------------------------------------------------------------


def test_compte_sans_personne_voit_un_message(client, salariee, connecter, jeu):
    connecter(client, salariee)
    reponse = client.get(URL)
    assert reponse.status_code == 200
    assert "pas encore rattaché" in reponse.content.decode()


def test_mois_non_publie(client, emma, connecter, cabinet):
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)   # enregistrée, pas publiée
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    assert "pas encore publié" in contenu
    assert "DUPONT" not in contenu


def test_ses_jours_et_rien_d_une_autre(client, emma, connecter, cabinet):
    _publier(cabinet)
    connecter(client, emma)
    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert "Version 1, publiée le" in contenu
    assert "29/09/2026" in contenu and "Alice DUPONT" in contenu and "journée" in contenu
    # Sara est au secrétariat le même jour : rien d'elle, ni de sa case, ni de DATA.
    for mot in ("Sara", "PETIT", "sara_pet", "Secrétariat", "planning-data", "conges"):
        assert mot not in contenu, mot
    # Le 29 septembre est dans la plage d'octobre (semaines complètes) mais hors du mois : marqué.
    jours = reponse.context["resultat"]["jours"]
    assert [(j["date"].isoformat(), j["t"], j["x"], j["slot_libelle"], j["hors_mois"]) for j in jours] == [
        ("2026-09-29", "J", False, "Alice DUPONT", True)
    ]
    assert 'class="voisin"' in contenu


def test_case_misc_journee_courte_et_hors_quota(client, emma, connecter, cabinet):
    state = fabrique.etat({"2026-09-29": {"sureffectif": [fabrique.brique("emma_ber", "C", x=True)]}})
    _publier(cabinet, state)
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    assert "Sureffectif" in contenu
    assert "journée courte (fin 16h30)" in contenu and "(heures sup)" in contenu


def test_principale_rattachee_voit_ses_jours(client, principale, connecter, cabinet, jeu):
    fabrique_absences.lier(principale, jeu["personnes"]["Emma"])
    _publier(cabinet)
    connecter(client, principale)
    assert "Alice DUPONT" in client.get(URL).content.decode()


def test_type_d_absence_dans_sa_fiche_seulement(client, emma, connecter, cabinet, jeu):
    """`DATA` n'est jamais servi : ses propres types ne vivent que dans ses fiches du jour, ceux des autres nulle part.

    Brique 6b (D6b.11 amendée) : la maladie du 6 et le congé payé du 7 sont à elle ; le retard et
    l'école du jeu fictif sont à d'autres.
    """
    for libelle, jour in (("Maladie", 6), ("Congé payé", 7)):
        fabrique_absences.absence(
            jeu["personnes"]["Emma"],
            fabrique.type_absence(libelle),
            datetime.date(2026, 10, jour),
            datetime.date(2026, 10, jour),
            statut=AbsenceSalariee.Statut.DECLAREE,
        )
    _publier(cabinet)
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    assert "Maladie — Déclarée" in _fiche(contenu, "2026-10-06")
    assert "Congé payé — Déclarée" in _fiche(contenu, "2026-10-07")
    hors_des_fiches = _hors_des_fiches(contenu)
    for mot in TYPES + ("planning-data", "planning-state", "planning-meta"):
        assert mot not in hors_des_fiches, mot
    for mot in ("Retard", "Ecole", "planning-data", "planning-state", "planning-meta"):
        assert mot not in contenu, mot


def test_slot_inconnu_reste_brut(client, emma, connecter):
    _version_publiee(fabrique.MOIS, 1, {"2026-10-06": {"praticien_parti": [fabrique.brique("emma_ber")]}})
    connecter(client, emma)
    assert "praticien_parti" in client.get(URL).content.decode()


def test_praticien_inactif_garde_son_libelle(client, emma, connecter, cabinet, jeu):
    _publier(cabinet)
    alice = jeu["personnes"]["Alice"]
    alice.actif = False
    alice.save(update_fields=["actif"])
    connecter(client, emma)
    assert "Alice DUPONT" in client.get(URL).content.decode()


def test_plage_entiere_et_mois_calendaire_prioritaire(client, emma, connecter):
    """P2 : les jours du mois voisin sont montrés ; pour une date partagée, le mois calendaire fait foi."""
    _version_publiee("2026-10", 1, {
        "2026-10-27": {"alice_dup": [fabrique.brique("emma_ber")]},
        "2026-11-01": {"sureffectif": [fabrique.brique("emma_ber")]},
    })
    _version_publiee("2026-11", 1, {
        "2026-10-27": {"sureffectif": [fabrique.brique("emma_ber")]},
        "2026-11-01": {"administratif": [fabrique.brique("emma_ber")]},
    })
    connecter(client, emma)
    reponse = client.get(URL)
    jours = [
        (j["date"].isoformat(), j["slot_libelle"], j["hors_mois"], j["source_numero"])
        for j in reponse.context["resultat"]["jours"]
    ]
    assert jours == [("2026-10-27", "Alice DUPONT", False, 1), ("2026-11-01", "Administratif", True, 1)]
    assert 'class="voisin"' in reponse.content.decode()


def test_service_sans_version_publiee(jeu):
    assert services.jours_publies(jeu["personnes"]["Emma"], fabrique.MOIS) is None


def test_mois_historique_importe(client, salariee, connecter, cabinet):
    """Brique 7a (C7.1) : « Mes jours » lit une version historique **sans changement**.

    Aucune présence Doctolib n'est importée pour ce mois : `jours_publies` ne lit
    que le `state` et les personnes, jamais `DATA`. La colonne d'une fiche close
    et non planifiée garde son libellé (P3, C7.4).
    """
    fiches = fabrique.personnes_historiques()
    fabrique_absences.lier(salariee, fiches["test_ass"])
    affectations = dict(fabrique.affectations_historiques())
    # Jeudi 2 avril : dans la plage de mars (semaines complètes), hors du mois.
    affectations["2026-04-02"] = {"secretariat": [fabrique.brique("test_ass", "C", x=True)]}
    version = historique.executer(
        historique.analyser(fabrique.planning_exporte(affectations=affectations)), cabinet
    )

    connecter(client, salariee)
    reponse = client.get(f"/mes-jours/{fabrique.MOIS_HISTORIQUE}/")
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert f"Version {version.numero}, publiée le" in contenu
    assert [
        (j["date"].isoformat(), j["t"], j["x"], j["slot_libelle"], j["hors_mois"])
        for j in reponse.context["resultat"]["jours"]
    ] == [
        ("2026-03-03", "J", False, "Test PRATICIEN", False),
        ("2026-03-04", "J", False, "Test PRATICIEN", False),
        ("2026-04-02", "C", True, "Secrétariat", True),
    ]
    assert 'class="voisin"' in contenu and "(heures sup)" in contenu
    # Rien de la secrétaire du même jour, et toujours pas de `DATA`.
    for mot in ("test_sec", "SECRETAIRE", "planning-data", "conges"):
        assert mot not in contenu, mot


# --- Brique 6b : grille, fiche du jour, marqueurs, légende (C6.8, C6.9) --------------


def _cases(reponse):
    """Les cases de la grille, par date ISO."""
    return {case["iso"]: case for semaine in reponse.context["grille"]["semaines"] for case in semaine}


def _fiche(contenu, iso):
    debut = contenu.index(f'id="fiche-{iso}"')
    return contenu[debut:contenu.index("</section>", debut)]


def _hors_des_fiches(contenu):
    """Le HTML de la page privé de ses blocs `<section class="fiche"` … `</section>`."""
    morceaux = contenu.split('<section class="fiche"')
    return morceaux[0] + "".join(m.split("</section>", 1)[1] for m in morceaux[1:])


def _bouton(contenu, iso):
    debut = contenu.index(f'aria-controls="fiche-{iso}"')
    return contenu[debut:contenu.index("</button>", debut)]


def _version_marquee(mois, numero, affectations, jours):
    """Une version publiée dont le compte-rendu d'effectif est posé à la main."""
    return PlanningVersion.objects.create(
        mois=mois,
        numero=numero,
        state=fabrique.etat(affectations),
        publiee=True,
        publie_le=timezone.now(),
        verifications={
            "verifie_le": "2026-09-12T20:00:00+00:00",
            "imports": [],
            "nb_briques": 0,
            "effectif": {"jours": jours, "calcule_le": "2026-09-12T20:00:00+00:00"},
        },
    )


def _absence(personne, libelle, jour, statut):
    return fabrique_absences.absence(
        personne, fabrique.type_absence(libelle), jour, jour, statut=statut
    )


def test_grille_sept_colonnes_et_semaines_completes(client, emma, connecter, cabinet):
    _publier(cabinet)
    connecter(client, emma)
    reponse = client.get(URL)
    contenu = reponse.content.decode()
    semaines = reponse.context["grille"]["semaines"]
    assert len(semaines) == 5 and all(len(semaine) == 7 for semaine in semaines)  # 2026-09-28 → 2026-11-01
    assert semaines[0][0]["iso"] == "2026-09-28" and semaines[4][6]["iso"] == "2026-11-01"
    assert contenu.count('<th scope="col"') == 7
    assert contenu.count('aria-controls="fiche-') == 35
    assert contenu.count('<section class="fiche"') == 35


def test_case_du_jour_et_jours_du_mois_voisin(client, emma, connecter, cabinet):
    _publier(cabinet)
    connecter(client, emma)
    with patch("planning.views.timezone.localdate", return_value=AUJOURD_HUI):
        reponse = client.get(URL)
    contenu = reponse.content.decode()
    assert contenu.count('aria-current="date"') == 1
    assert 'aria-controls="fiche-2026-10-06" aria-expanded="false" aria-current="date"' in contenu
    assert contenu.count('<td class="voisin">') == 4  # 28, 29, 30 septembre et 1er novembre
    cases = _cases(reponse)
    assert cases["2026-10-06"]["aujourd_hui"] is True and cases["2026-10-07"]["aujourd_hui"] is False
    assert cases["2026-09-29"]["hors_mois"] is True and cases["2026-10-01"]["hors_mois"] is False


def test_codes_de_la_grille_et_priorite(client, emma, connecter, cabinet, jeu):
    """D6b.3 + D6b.15 : F > A > A ? > E > brique ; « A » rouge si le type est bloquant, orange sinon."""
    state = fabrique.etat({
        "2026-10-06": {"alice_dup": [fabrique.brique("emma_ber")]},        # journée + congé payé validé → A
        "2026-10-07": {"alice_dup": [fabrique.brique("emma_ber", "C")]},   # journée courte → JC
        "2026-10-20": {"alice_dup": [fabrique.brique("emma_ber")]},        # journée + école → E
        "2026-10-27": {"alice_dup": [fabrique.brique("emma_ber")]},        # journée → J
    })
    _publier(cabinet, state)
    personne = jeu["personnes"]["Emma"]
    _absence(personne, "Congé payé", datetime.date(2026, 10, 6), AbsenceSalariee.Statut.VALIDEE)
    _absence(personne, "Retard", datetime.date(2026, 10, 8), AbsenceSalariee.Statut.DECLAREE)
    _absence(personne, "Congé sans solde", datetime.date(2026, 10, 9), AbsenceSalariee.Statut.EN_ATTENTE)
    _absence(personne, "Ecole", datetime.date(2026, 10, 20), AbsenceSalariee.Statut.DECLAREE)
    _absence(personne, "Maladie", datetime.date(2026, 10, 21), AbsenceSalariee.Statut.REFUSEE)  # ni case, ni fiche
    connecter(client, emma)
    reponse = client.get(URL)
    cases = _cases(reponse)
    attendu = {
        "2026-10-06": ("A", "absence-bloquante"),
        "2026-10-07": ("JC", "brique"),
        "2026-10-08": ("A", "absence-partielle"),
        "2026-10-09": ("A ?", "attente"),
        "2026-10-13": ("A", "absence-bloquante"),  # congé payé validé du jeu fictif (13 → 15)
        "2026-10-20": ("E", "ecole"),
        "2026-10-21": ("", "vide"),
        "2026-10-27": ("J", "brique"),
        "2026-11-01": ("F", "ferie"),
    }
    assert {iso: (cases[iso]["code"], cases[iso]["classe"]) for iso in attendu} == attendu
    # La fiche du 6 garde la brique ET l'absence ; celle du 21 ne sait rien de la demande refusée.
    fiche = cases["2026-10-06"]["fiche"]
    assert fiche["brique"] == {"slot_libelle": "Alice DUPONT", "courte": False, "sup": False}
    assert [(a["type"], a["statut"], a["bloquant"]) for a in fiche["absences"]] == [("Congé payé", "Validée", True)]
    assert cases["2026-10-21"]["fiche"]["absences"] == []
    contenu = reponse.content.decode()
    assert '<span class="code">A ?</span>' in contenu and '<span class="code">JC</span>' in contenu
    assert "journée courte (fin 16h30) avec Alice DUPONT" in _fiche(contenu, "2026-10-07")
    assert "Maladie" not in contenu


def test_marqueurs_d_une_version_marquee_par_la_publication(client, emma, connecter, cabinet, jeu):
    """C6.9 : « − » où un praticien présent n'a personne, « + » sur une brique en sureffectif ;
    le samedi ouvert est une case normale (D6b.13)."""
    state = fabrique.etat({
        "2026-09-29": {"alice_dup": [fabrique.brique("emma_ber")], "secretariat": [fabrique.brique("sara_pet")]},
        "2026-10-06": {
            "alice_dup": [fabrique.brique("emma_ber")],
            "bob_mar": [fabrique.brique("lina_rou")],
            "chloe_ler": [fabrique.brique("zoe_gir")],
            "sureffectif": [fabrique.brique("nora_fon")],
        },
    })
    _publier(cabinet, state)
    connecter(client, emma)
    reponse = client.get(URL)
    cases = _cases(reponse)
    assert cases["2026-09-29"]["moins"] is True and cases["2026-09-29"]["plus"] is False  # Bob et Chloe sans personne
    assert cases["2026-10-06"]["moins"] is False and cases["2026-10-06"]["plus"] is True
    assert cases["2026-10-03"]["moins"] is True and cases["2026-10-03"]["classe"] == "vide"  # samedi ouvert
    assert cases["2026-10-04"]["classe"] == "ferme" and cases["2026-10-05"]["classe"] == "ferme"
    contenu = reponse.content.decode()
    assert 'aria-label="effectif insuffisant"' in _bouton(contenu, "2026-09-29")
    assert 'aria-label="sureffectif"' in _bouton(contenu, "2026-10-06")
    assert 'aria-label="sureffectif"' not in _bouton(contenu, "2026-09-29")
    assert reponse.context["resultat"]["sans_effectif"] is False
    assert '<p class="note">' not in contenu


def test_aucun_marqueur_sur_une_version_sans_compte_rendu(client, emma, connecter):
    """Version publiée avant la 6b (`verifications=[]`) : grille sans marqueur, phrase unique, aucune erreur."""
    _version_publiee(fabrique.MOIS, 1, {"2026-10-06": {"alice_dup": [fabrique.brique("emma_ber")]}})
    connecter(client, emma)
    reponse = client.get(URL)
    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert '<p class="note">Effectif non renseigné pour ce mois.</p>' in contenu
    assert 'aria-label="effectif insuffisant"' not in contenu and 'aria-label="sureffectif"' not in contenu
    cases = _cases(reponse)
    assert not any(case["moins"] or case["plus"] for case in cases.values())
    assert all(case["fiche"]["raison"] is None for case in cases.values())
    assert cases["2026-10-06"]["code"] == "J" and cases["2026-10-04"]["classe"] == "vide"
    assert reponse.context["resultat"]["sans_effectif"] is True
    assert reponse.context["resultat"]["effectif"] == {}


def test_mois_historique_sans_marqueur_ni_erreur(client, salariee, connecter, cabinet):
    """C7.8 : une version historique se rend en grille, sans marqueur, avec la phrase unique."""
    fiches = fabrique.personnes_historiques()
    fabrique_absences.lier(salariee, fiches["test_ass"])
    historique.executer(
        historique.analyser(fabrique.planning_exporte(affectations=fabrique.affectations_historiques())), cabinet
    )
    connecter(client, salariee)
    reponse = client.get(f"/mes-jours/{fabrique.MOIS_HISTORIQUE}/")
    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert '<p class="note">Effectif non renseigné pour ce mois.</p>' in contenu
    assert 'aria-label="effectif insuffisant"' not in contenu and 'aria-label="sureffectif"' not in contenu
    cases = _cases(reponse)
    assert cases["2026-03-03"]["code"] == "J" and cases["2026-03-03"]["fiche"]["brique"]["slot_libelle"] == "Test PRATICIEN"


def test_raisons_dans_la_fiche(client, emma, connecter):
    """D6b.13 et revue 4.6 : la fiche dit pourquoi une case n'a pas de marqueur."""
    jours = {
        "2026-10-04": {"moins": False, "plus": False, "ouvert": False},  # dimanche
        "2026-10-05": {"moins": False, "plus": False, "ouvert": False},  # lundi fermé
        "2026-10-06": {"moins": True, "plus": False, "ouvert": True},
        "2026-11-01": {"moins": False, "plus": False, "ouvert": False},  # Toussaint
    }
    _version_marquee(fabrique.MOIS, 1, {}, jours)  # le 7 octobre n'a pas d'entrée : présences non importées
    _version_publiee("2026-09", 1, {})  # septembre sans compte-rendu : ses jours de la plage d'octobre
    connecter(client, emma)
    reponse = client.get(URL)
    cases = _cases(reponse)
    assert cases["2026-10-04"]["fiche"]["raison"] == "Week-end"
    assert cases["2026-10-05"]["fiche"]["raison"] == "Cabinet fermé ce jour"
    assert cases["2026-10-06"]["fiche"]["raison"] is None and cases["2026-10-06"]["moins"] is True
    assert cases["2026-10-07"]["fiche"]["raison"] == "Présences non importées ce jour"
    assert cases["2026-11-01"]["fiche"]["raison"] == "Jour férié : Toussaint"
    assert cases["2026-09-29"]["fiche"]["raison"] == "Effectif non renseigné pour ce mois"
    assert reponse.context["resultat"]["sans_effectif"] is False
    contenu = reponse.content.decode()
    assert '<p class="note">' not in contenu
    assert "Jour férié : Toussaint" in _fiche(contenu, "2026-11-01")
    assert "Cabinet fermé ce jour" in _fiche(contenu, "2026-10-05")


def test_absences_de_la_salariee_dans_sa_fiche_seulement_et_aucun_autre_nom(client, emma, connecter, cabinet, jeu):
    """D6b.3 / Q18 : ses absences dans ses fiches ; rien d'une autre personne — ni nom, ni absence, ni type."""
    state = fabrique.etat({
        "2026-10-06": {
            "alice_dup": [fabrique.brique("emma_ber")],
            "bob_mar": [fabrique.brique("lina_rou")],
            "chloe_ler": [fabrique.brique("zoe_gir")],
            "secretariat": [fabrique.brique("sara_pet")],
            "sureffectif": [fabrique.brique("nora_fon")],
        },
    })
    _publier(cabinet, state)
    personnes = jeu["personnes"]
    _absence(personnes["Emma"], "Congé payé", datetime.date(2026, 10, 20), AbsenceSalariee.Statut.VALIDEE)
    _absence(personnes["Lina"], "Maladie", datetime.date(2026, 10, 6), AbsenceSalariee.Statut.DECLAREE)
    _absence(personnes["Sara"], "Retard", datetime.date(2026, 10, 20), AbsenceSalariee.Statut.DECLAREE)
    connecter(client, emma)
    reponse = client.get(URL)
    contenu = reponse.content.decode()
    cases = _cases(reponse)
    assert [(a["type"], a["statut"]) for a in cases["2026-10-20"]["fiche"]["absences"]] == [("Congé payé", "Validée")]
    assert cases["2026-10-06"]["fiche"]["absences"] == []  # la maladie de Lina n'existe pas ici
    assert "Congé payé — Validée" in _fiche(contenu, "2026-10-20")  # son type, dans sa fiche (D6b.11 amendée)
    assert 'class="absence' not in _fiche(contenu, "2026-10-06")
    assert "Congé payé" not in _hors_des_fiches(contenu)
    assert "Alice DUPONT" in contenu
    for mot in AUTRES + ("Maladie", "Retard", "Ecole") + (
        "sara_pet", "lina_rou", "Secrétariat", "Sureffectif", "conges", "planning-data",
    ):
        assert mot not in contenu, mot


def test_legende_a_huit_entrees_sans_chaine_interdite(client, emma, connecter, cabinet):
    _publier(cabinet)
    connecter(client, emma)
    contenu = client.get(URL).content.decode()
    legende = contenu[contenu.index('<dl class="legende"'):contenu.index("</dl>")]
    for libelle in (
        "journée", "journée courte", "absence", "absence en attente", "école", "férié",
        "effectif insuffisant", "sureffectif",
    ):
        assert f"<dd>{libelle}</dd>" in legende, libelle
    assert legende.count("<dt>") == 8
    assert "aria-label" not in legende
    for mot in INTERDITS_LEGENDE:  # hors des fiches : son congé payé du jeu (13 → 15) y a sa place
        assert mot not in _hors_des_fiches(contenu), mot
    for mot in PARTOUT_INTERDITS:
        assert mot not in contenu, mot


def test_cout_fige_a_huit_requetes(client, emma, connecter, cabinet, django_assert_num_queries):
    """Brique 6b : 7 (session, compte, personne, trois versions, praticiens) + 1 (ses absences)."""
    _publier(cabinet)
    connecter(client, emma)
    with django_assert_num_queries(8):
        assert client.get(URL).status_code == 200


def test_garde_de_source_du_gabarit():
    """F-2 : un seul `<script` inline, aucun appel réseau, aucun bloc JSON, aucun `DATA`."""
    source = Path(get_template("planning/mes_jours.html").origin.name).read_text(encoding="utf-8")
    assert source.count("<script") == 1
    for mot in ("fetch(", "planning-data", "DATA", "json_script"):
        assert mot not in source, mot
