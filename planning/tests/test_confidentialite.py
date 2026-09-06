"""Confidentialité de la brique 4a : sept surfaces, et les rôles sur `DATA`.

Le type d'absence (« Maladie ») est une donnée de santé. Décision C4.1 : son
libellé est servi dans `DATA.conges[].type` aux rôles cabinet et principale, à
l'écran et dans la copie HTML, et NULLE PART AILLEURS. Les sept surfaces :

1. le `state` reçu est nettoyé (ni congé, ni type) ;
2. `PlanningVersion.state` ne porte que quatre clés ;
3. l'export JSON (structure figée par `planning/tests_js/export.test.js`) ;
4. le journal d'audit ;
5. les logs des vues et du service ;
6. le corps de `/api/erreurs/` ;
7. les absences des personnes hors périmètre n'entrent pas dans `DATA`.
"""

import datetime
import json
import logging

import pytest

from audit.models import EvenementAudit
from planning import services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

URL_PAGE = f"/planning/{fabrique.MOIS}/"
URL_API = f"/api/planning/{fabrique.MOIS}/versions/"
NOMS = ("BERNARD", "Emma", "ROUX", "Lina", "MOREL", "Lea", "DUPONT", "Alice", "LEROY", "Chloe")
TYPES = ("Maladie", "Congé payé", "Retard", "Ecole")


def poster(client, corps):
    return client.post(URL_API, data=json.dumps(corps), content_type="application/json")


def data_de_la_page(contenu):
    """Le bloc `planning-data` de la page, décodé (`json_script` échappe les accents)."""
    balise = '<script id="planning-data" type="application/json">'
    debut = contenu.index(balise) + len(balise)
    return json.loads(contenu[debut:contenu.index("</script>", debut)])


def state_avec_congé():
    state = fabrique.etat_propre()
    state["conges"] = [{"s": "emma_ber", "date": "2026-10-13", "type": "Maladie", "bloque": True}]
    state["notes"] = {"2026-09-29": ["note sans nom"]}
    return state


def test_1_et_2_state_recu_nettoye_et_version_sans_type(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    assert poster(client, {"version_de_base": 0, "state": state_avec_congé()}).status_code == 201

    version = PlanningVersion.objects.get()
    assert set(version.state) == {"affectations", "feries", "feries_off", "notes"}
    texte = json.dumps(version.state, ensure_ascii=False)
    for mot in TYPES + NOMS:
        assert mot not in texte, mot


def test_4_audit_sans_nom_ni_type(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    poster(client, {"version_de_base": 0, "state": state_avec_congé()})
    poster(client, {"version_de_base": 0, "state": state_avec_congé()})   # 409
    poster(client, {"version_de_base": 1, "state": fabrique.etat({"2026-10-13": {"alice_dup": [fabrique.brique("emma_ber")]}})})   # 422

    for evenement in EvenementAudit.objects.all():
        texte = json.dumps(evenement.details, ensure_ascii=False)
        for mot in TYPES + NOMS:
            assert mot not in texte, (evenement.action, mot)
        assert "@" not in texte


def test_5_logs_sans_nom_ni_type(client, cabinet, connecter, caplog):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    with caplog.at_level(logging.DEBUG, logger="planning"):
        poster(client, {"version_de_base": 0, "state": state_avec_congé()})
        poster(client, {"version_de_base": 0, "state": state_avec_congé()})
        poster(client, {"version_de_base": 1, "state": fabrique.etat({"2026-10-13": {"alice_dup": [fabrique.brique("emma_ber")]}})})
        client.get(URL_PAGE)

    assert caplog.records, "les vues et le service journalisent bien"
    for mot in TYPES + NOMS + ("emma_ber",):
        assert mot not in caplog.text, mot


def test_6_rapport_d_erreur_sans_message(client, cabinet, connecter, caplog):
    connecter(client, cabinet)
    with caplog.at_level(logging.ERROR, logger="planning.views"):
        client.post("/api/erreurs/", data=json.dumps({"nom": "RangeError", "message": "Maladie de BERNARD Emma", "state": state_avec_congé()}), content_type="application/json")
    for mot in TYPES + NOMS:
        assert mot not in caplog.text, mot
    assert "RangeError" in caplog.text


def test_7_absence_hors_perimetre_absente_de_data(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    autre = fabrique.salariee("DURAND", "Ana", 39, planifiee=False)
    fabrique.fabrique_absences.absence(autre, fabrique.type_absence("Maladie"), datetime.date(2026, 10, 6), datetime.date(2026, 10, 7), statut="declaree")
    connecter(client, cabinet)
    contenu = client.get(URL_PAGE).content.decode()
    data = data_de_la_page(contenu)
    texte = json.dumps(data, ensure_ascii=False)

    assert "DURAND" not in contenu
    assert f"ana_dur" not in texte and "Maladie" not in texte
    assert not any(c["date"] in ("2026-10-06", "2026-10-07") and c["s"] != "lea_mor" for c in data["conges"])


def test_422_sans_texte_ni_type(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    connecter(client, cabinet)
    reponse = poster(client, {"version_de_base": 0, "state": fabrique.etat({"2026-10-13": {"alice_dup": [fabrique.brique("emma_ber")]}})})

    assert reponse.status_code == 422
    texte = reponse.content.decode()
    for mot in TYPES + NOMS + ("message",):
        assert mot not in texte, mot


# --- Rôles sur DATA.conges[].type ---------------------------------------------


def test_type_servi_au_cabinet_et_a_la_principale(client, cabinet, principale, connecter):
    fabrique.jeu_complet(cabinet)
    for compte in (cabinet, principale):
        connecter(client, compte)
        data = data_de_la_page(client.get(URL_PAGE).content.decode())
        assert {"Congé payé", "Retard"} <= {c["type"] for c in data["conges"]}
        client.logout()


def test_type_refuse_a_la_salariee_et_a_l_anonyme(client, cabinet, salariee, connecter):
    fabrique.jeu_complet(cabinet)
    reponse = client.get(URL_PAGE)
    assert reponse.status_code == 302 and "Congé payé" not in reponse.content.decode()
    connecter(client, salariee)
    reponse = client.get(URL_PAGE)
    assert reponse.status_code == 403 and "Congé payé" not in reponse.content.decode()


def test_copie_ne_porte_pas_le_state_d_un_autre_mois_ni_de_conge_dans_le_state(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, state_avec_congé(), cabinet)
    connecter(client, cabinet)
    contenu = client.get(f"/planning/{fabrique.MOIS}/copie/").content.decode()
    debut = contenu.index('<script id="planning-state"')
    fin = contenu.index("</script>", debut)
    state = contenu[debut:fin]
    assert "Maladie" not in state and "conges" not in state
