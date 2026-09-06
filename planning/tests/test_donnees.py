"""Recette de `planning.donnees.construire` sur le jeu fictif.

Le jeu construit en base (`fabrique.jeu_complet`) reproduit le fichier
`planning/tests_js/fixtures/data_fictif.json`, à deux exceptions près, dites
dans `test_reproduit_le_jeu_fictif` : le férié de test du samedi 17, que le
calendrier réel ne produit pas, et les clés que le skill n'avait pas.
"""

import datetime
import json
from pathlib import Path

import pytest

from comptes.models import Personne
from planning import donnees
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).resolve().parent.parent / "tests_js" / "fixtures" / "data_fictif.json"


def fictif():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def construire():
    return donnees.construire(fabrique.MOIS, regles=fabrique.regles())


def par_id(liste):
    return {entree["id"]: entree for entree in liste}


# --- Le jeu fictif entier ------------------------------------------------------


def test_reproduit_le_jeu_fictif(cabinet):
    fabrique.jeu_complet(cabinet)
    data = construire()
    attendu = fictif()

    assert data["praticiens"] == attendu["praticiens"]
    assert par_id(data["salaries"]) == par_id(attendu["salaries"])
    assert data["jours"] == attendu["jours"]
    assert data["conges"] == attendu["conges"]
    assert data["cours"] == attendu["cours"]
    assert data["attentes"] == []
    # Le férié de test du samedi 17 n'existe pas dans le calendrier réel.
    assert data["feries"] == {"2026-11-01": "Toussaint"}
    for cle in ("mois", "libelle", "debut", "fin", "heures", "seuils"):
        assert data["meta"][cle] == attendu["meta"][cle], cle
    assert data["meta"]["source"] == "app"
    assert data["meta"]["non_couverts"] == []
    assert data["meta"]["alertes"] == []
    assert len(data["meta"]["enveloppes"]) == 2


def test_contrat_data_complet(cabinet):
    fabrique.jeu_complet(cabinet)
    data = construire()

    assert set(data) == {"meta", "praticiens", "salaries", "jours", "conges", "feries", "cours", "attentes"}
    assert set(data["meta"]) == {
        "mois", "libelle", "debut", "fin", "genere", "source", "heures", "seuils",
        "enveloppes", "imports", "non_couverts", "alertes",
    }
    for p in data["praticiens"]:
        assert set(p) == {"id", "label", "nom", "agenda", "couleur", "fixes", "attendues", "exclusif", "binomes", "a_part", "etiquette"}
    for s in data["salaries"]:
        assert set(s) >= {"id", "label", "nom", "role", "heures", "heures_supposees", "heures_fixes", "gabarit", "fixes", "couleur", "binomes", "exclusif", "admin"}
        assert s["heures_supposees"] is False
    # Le format est du JSON pur.
    json.dumps(data)


def test_regles_resolues(cabinet):
    fabrique.jeu_complet(cabinet)
    data = construire()
    prat, sal = par_id(data["praticiens"]), par_id(data["salaries"])

    assert prat["chloe_ler"]["exclusif"] and prat["chloe_ler"]["attendues"] == 2
    assert prat["chloe_ler"]["binomes"] == ["zoe_gir", "ines_lam"]
    assert prat["chloe_ler"]["a_part"] and prat["chloe_ler"]["etiquette"] == "ortho"
    assert [p["id"] for p in data["praticiens"]] == ["alice_dup", "bob_mar", "chloe_ler"]
    assert sal["zoe_gir"]["exclusif"] and sal["zoe_gir"]["binomes"] == ["chloe_ler"]
    assert sal["nora_fon"]["admin"] == "C"
    assert sal["lea_mor"]["etudiante"] is True
    assert sal["lea_mor"]["gabarit"] == ["J", "J", "J", "C"]   # gabarit_sans_cours, pas celui des 27 h
    assert "etudiante" not in sal["emma_ber"]


def test_secretaire_a_jours_fixes(cabinet):
    fabrique.jeu_complet(cabinet)
    sara = par_id(construire()["salaries"])["sara_pet"]

    assert sara["fixes"] == [1, 2, 3]
    assert sara["heures_fixes"] is True
    assert sara["heures"] == 29.25
    assert sara["gabarit"] == ["J", "J", "J"]
    assert sara["role"] == "secretaire"


def test_couleurs_par_la_palette(cabinet):
    fabrique.jeu_complet(cabinet)
    data = construire()

    assert par_id(data["praticiens"])["alice_dup"]["couleur"] == fabrique.PALETTE["yellow"]
    # Sara n'a pas de couleur : repli `default`.
    assert par_id(data["salaries"])["sara_pet"]["couleur"] == fabrique.PALETTE["default"]


# --- Praticiens et salariées hors contrat --------------------------------------


def test_praticien_sans_agenda_ni_jours_fixes_exclu_et_signale(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.praticien("LEFEVRE", "Marc")
    data = construire()

    assert "lefevre" not in " ".join(p["id"] for p in data["praticiens"])
    assert any("LEFEVRE Marc" in a and "exclu" in a for a in data["meta"]["alertes"])


def test_praticien_a_jours_fixes_sans_agenda(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.praticien("LEFEVRE", "Marc", jours_fixes=["Lundi", "Vendredi"])
    marc = par_id(construire()["praticiens"])["marc_lef"]

    assert marc["agenda"] is None
    assert marc["fixes"] == [0, 4]


def test_agenda_sans_ligne_signale(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.praticien("LEFEVRE", "Marc", agenda="LEFEVRE Marc")
    data = construire()

    assert "marc_lef" in par_id(data["praticiens"])
    assert any("LEFEVRE Marc" in a and "sans ligne" in a for a in data["meta"]["alertes"])


def test_salariee_sans_contrat_exclue(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.salariee("DURAND", "Ana", heures=None)
    data = construire()

    assert "ana_dur" not in par_id(data["salaries"])
    assert any("DURAND Ana" in a and "ni heures" in a for a in data["meta"]["alertes"])


def test_heures_hors_gabarits_exclue(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.salariee("DURAND", "Ana", heures=30)
    data = construire()

    assert "ana_dur" not in par_id(data["salaries"])
    assert any("DURAND Ana" in a and "hors gabarits" in a for a in data["meta"]["alertes"])


def test_regle_sur_une_personne_absente_ignoree_et_signalee(cabinet):
    fabrique.jeu_complet(cabinet)
    Personne.objects.filter(nom="GIRARD").update(planifiee=False)
    data = construire()

    assert par_id(data["praticiens"])["chloe_ler"]["binomes"] == ["ines_lam"]
    assert par_id(data["praticiens"])["chloe_ler"]["attendues"] == 1
    assert any("GIRARD Zoe" in a and "règle ignorée" in a for a in data["meta"]["alertes"])


def test_personnes_inactives_ou_non_planifiees_hors_planning(cabinet):
    fabrique.jeu_complet(cabinet)
    Personne.objects.filter(nom="ROUX").update(actif=False)
    Personne.objects.filter(nom="MARTIN").update(planifiee=False)
    data = construire()

    assert "lina_rou" not in par_id(data["salaries"])
    assert "bob_mar" not in par_id(data["praticiens"])


# --- Identifiants et libellés ---------------------------------------------------


def test_identifiant_de_repli_en_collision(cabinet):
    fabrique.jeu_complet(cabinet)
    doublon = fabrique.salariee("BERNARDIN", "Emma", 39)   # même prénom, mêmes trois lettres
    assert doublon.code is None
    data = construire()

    attendu = f"emma_ber{doublon.pk}"
    assert attendu in par_id(data["salaries"])
    assert any("BERNARDIN Emma" in a and "collision" in a for a in data["meta"]["alertes"])
    assert donnees.identifiant(doublon) == attendu
    doublon.refresh_from_db()
    assert doublon.code is None   # jamais écrit en base


def test_label_avec_initiale_en_cas_de_doublon_de_prenom(cabinet):
    fabrique.jeu_complet(cabinet)
    fabrique.praticien("MARTIN", "Alice", agenda="MARTIN Alice")
    data = construire()
    prat = par_id(data["praticiens"])

    assert prat["alice_dup"]["label"] == "Alice D"
    assert prat["alice_mar"]["label"] == "Alice M"
    assert par_id(data["salaries"])["emma_ber"]["label"] == "Emma"


# --- Présences -----------------------------------------------------------------


def test_jour_non_couvert_par_les_imports(cabinet):
    fabrique.personnes()
    premiere = fabrique.PLAGE.fenetres[0]
    fabrique.importer(cabinet, premiere[0], premiere[1])
    data = construire()

    assert data["meta"]["non_couverts"] == ["2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"]
    assert "2026-10-29" not in data["jours"]
    assert "2026-10-27" in data["jours"]


def test_le_plus_recent_des_imports_gagne(cabinet):
    fabrique.personnes()
    fabrique.importer_le_mois(cabinet)

    def bob_partout(jour, indice):   # un import plus récent où Bob est présent tous les jours ouvrés
        if fabrique.AGENDAS[indice] == "MARTIN Bob" and jour.weekday() < 6:
            return {"verdict": "ouvert", "presence": True, "creneaux": (("09:00", "12:00"),), "nb_rdv": 3, "duree_rdv": 90}
        return fabrique.regle_presences(jour, indice)

    premiere = fabrique.PLAGE.fenetres[0]
    fabrique.importer(cabinet, premiere[0], premiere[1], regle=bob_partout)
    data = construire()

    assert data["jours"]["2026-09-30"]["bob_mar"]["c"] == [["09:00", "12:00"]]
    assert data["jours"]["2026-09-30"]["bob_mar"]["fin"] == "12:00"
    # Seconde fenêtre inchangée : Bob y garde sa journée du premier import.
    assert data["jours"]["2026-10-29"]["bob_mar"]["fin"] == "19:00"
    assert "bob_mar" not in data["jours"].get("2026-10-28", {}) or data["jours"]["2026-10-28"]["bob_mar"]["fin"] == "12:00"


def test_creneaux_en_objets_du_payload_reel(cabinet):
    fabrique.personnes()

    def objets(jour, indice):
        base = fabrique.regle_presences(jour, indice)
        if base["presence"]:
            base["creneaux"] = ({"debut": "09:00", "fin": "13:00"}, {"debut": "14:00", "fin": "18:00"})
        return base

    premiere = fabrique.PLAGE.fenetres[0]
    # `ligne()` de la fabrique calcule les minutes sur des couples : on passe par
    # `_creneaux` directement pour la forme objet, la seule que le skill lisait.
    assert donnees._creneaux([{"debut": "09:00", "fin": "13:00"}, ["14:00", "18:00"], "x"]) == [
        ["09:00", "13:00"], ["14:00", "18:00"]
    ]


def test_seuils_par_defaut_si_absents_du_payload(cabinet):
    fabrique.personnes()
    premiere = fabrique.PLAGE.fenetres[0]
    import_ = fabrique.importer(cabinet, premiere[0], premiere[1])
    payload = import_.payload
    del payload["donnees"]["seuil_presence"]
    type(import_).objects.filter(pk=import_.pk).update(payload=payload)
    data = construire()

    assert data["meta"]["seuils"] == {"courte_h": 4.0, "presence_h": 5.0}
    assert any("seuils absents" in a for a in data["meta"]["alertes"])


def test_mois_couvert(cabinet):
    assert donnees.mois_couvert(fabrique.PLAGE) is False
    fabrique.importer_le_mois(cabinet)
    assert donnees.mois_couvert(fabrique.PLAGE) is True


# --- Absences ------------------------------------------------------------------


def test_absence_informative_presente_et_non_bloquante(cabinet):
    fabrique.jeu_complet(cabinet)
    conges = construire()["conges"]

    retard = [c for c in conges if c["s"] == "lina_rou"]
    assert retard == [{"s": "lina_rou", "date": "2026-10-22", "type": "Retard", "bloque": False}]
    assert all(c["bloque"] for c in conges if c["s"] == "emma_ber")


def test_ecole_d_une_etudiante_va_dans_cours_seulement(cabinet):
    fabrique.jeu_complet(cabinet)
    data = construire()

    assert data["cours"] == {"lea_mor": ["2026-10-06", "2026-10-20", "2026-10-27"]}
    assert not any(c["s"] == "lea_mor" for c in data["conges"])


def test_ecole_d_une_autre_personne_reste_un_conge_bloquant(cabinet):
    jeu = fabrique.jeu_complet(cabinet)
    fabrique.fabrique_absences.absence(
        jeu["personnes"]["Emma"], fabrique.type_absence("Ecole"),
        datetime.date(2026, 10, 20), datetime.date(2026, 10, 20),
        statut="declaree",
    )
    data = construire()

    assert {"s": "emma_ber", "date": "2026-10-20", "type": "Ecole", "bloque": True} in data["conges"]
    assert "emma_ber" not in data["cours"]


def test_demande_en_attente_informe_sans_bloquer(cabinet):
    jeu = fabrique.jeu_complet(cabinet)
    fabrique.fabrique_absences.absence(
        jeu["personnes"]["Nora"], fabrique.type_absence("Congé payé"),
        datetime.date(2026, 10, 27), datetime.date(2026, 10, 28),
    )   # statut par défaut : en attente
    data = construire()

    assert data["attentes"] == [{"s": "nora_fon", "date": "2026-10-27"}, {"s": "nora_fon", "date": "2026-10-28"}]
    assert not any(c["s"] == "nora_fon" for c in data["conges"])


def test_absence_a_cheval_bornee_a_la_plage(cabinet):
    jeu = fabrique.jeu_complet(cabinet)
    fabrique.fabrique_absences.absence(
        jeu["personnes"]["Nora"], fabrique.type_absence("Maladie"),
        datetime.date(2026, 10, 30), datetime.date(2026, 11, 3),
        statut="declaree",
    )
    dates = [c["date"] for c in construire()["conges"] if c["s"] == "nora_fon"]

    assert dates == ["2026-10-30", "2026-10-31", "2026-11-01"]


def test_absence_d_une_personne_hors_perimetre_ecartee_sans_alerte(cabinet):
    fabrique.jeu_complet(cabinet)
    autre = fabrique.salariee("DURAND", "Ana", 39, planifiee=False)
    fabrique.fabrique_absences.absence(
        autre, fabrique.type_absence("Maladie"),
        datetime.date(2026, 10, 6), datetime.date(2026, 10, 7),
        statut="declaree",
    )
    data = construire()
    texte = json.dumps(data, ensure_ascii=False)

    assert "DURAND" not in texte and "Ana" not in texte
    assert not any(c["date"] == "2026-10-06" and c["type"] == "Maladie" for c in data["conges"])
    assert data["meta"]["alertes"] == []


def test_libelle_conge_est_l_unique_source_du_type(cabinet):
    jeu = fabrique.jeu_complet(cabinet)
    assert donnees.libelle_conge(jeu["absences"]["cp"]) == "Congé payé"


def test_meta_imports_identite_des_imports_retenus(cabinet):
    """Brique 4b : `meta.imports` = identifiants et empreintes des imports qui font foi."""
    jeu = fabrique.jeu_complet(cabinet)
    data = construire()
    assert [x["id"] for x in data["meta"]["imports"]] == sorted(i.pk for i in jeu["imports"])
    assert all(len(x["empreinte"]) == 64 for x in data["meta"]["imports"])
