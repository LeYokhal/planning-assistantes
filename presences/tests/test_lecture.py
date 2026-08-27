"""Recette des gardes de lecture d'un payload S7.

Tous les payloads sont fictifs (voir `fabrique.py`) : aucun export réel n'est
ouvert par les tests.
"""

import copy
import datetime

import pytest

from presences.lecture import (
    FORME_DIRECT,
    FORME_WRAPPER_DICT,
    FORME_WRAPPER_LISTE,
    PayloadInvalide,
    lire,
    recompter,
)

from .fabrique import en_direct, en_wrapper_dict, en_wrapper_liste, fabriquer_payload

DEBUT = datetime.date(2026, 9, 28)
FIN = datetime.date(2026, 10, 28)


@pytest.fixture
def payload():
    return fabriquer_payload(DEBUT, FIN)


def test_wrapper_liste_lisible(payload):
    resultat = lire(en_wrapper_liste(payload))
    assert resultat.forme == FORME_WRAPPER_LISTE
    assert resultat.debut == DEBUT
    assert resultat.fin == FIN
    assert resultat.mode == "tous"


def test_wrapper_dict_lisible(payload):
    assert lire(en_wrapper_dict(payload)).forme == FORME_WRAPPER_DICT


def test_payload_direct_lisible(payload):
    assert lire(en_direct(payload)).forme == FORME_DIRECT


def test_invariant_verifie(payload):
    resultat = lire(en_direct(payload))
    assert resultat.attendu == resultat.obtenu
    assert resultat.nb_jours == 31
    assert resultat.nb_lignes == 62
    assert resultat.nb_presents == resultat.obtenu[4]


def test_recompte_independant_de_l_enveloppe(payload):
    """`recompter` lit le détail, jamais le message.

    31 jours × 2 agendas = 62 lignes : 23 jours ouvrés pour le premier agenda,
    14 lundis / mercredis / vendredis pour le second, le reste non planifié.
    """
    payload["message"] = "n'importe quoi"
    assert recompter(payload) == (37, 0, 0, 25, 37)


def test_ligne_praticien_retiree_refusee(payload):
    """Le cas de la recette : un fichier tronqué ou altéré ne passe pas."""
    del payload["donnees"]["jours"][3]["praticiens"][0]

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "écart enveloppe / recompte" in str(refus.value)


def test_message_sans_enveloppe_refuse(payload):
    """Durcissement par rapport au skill v1, qui laissait passer ce cas."""
    payload["message"] = "31 jour(s) du 2026-09-28 au 2026-10-28"

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "enveloppe absente du message" in str(refus.value)


def test_succes_faux_refuse(payload):
    payload["succes"] = False
    payload["message"] = "Doctolib indisponible"

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert str(refus.value) == "appel S7 en échec : Doctolib indisponible"


def test_mode_mono_refuse(payload):
    """Un payload mono-praticien afficherait un cabinet presque vide."""
    payload["donnees"]["mode"] = "mono"

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "seul le mode « tous » est accepté" in str(refus.value)


def test_json_illisible_refuse():
    with pytest.raises(PayloadInvalide) as refus:
        lire(b"pas du json du tout")
    assert str(refus.value) == "JSON illisible"


def test_bom_utf8_tolere(payload):
    """Un fichier enregistré depuis Windows porte souvent un BOM."""
    assert lire(b"\xef\xbb\xbf" + en_direct(payload)).forme == FORME_DIRECT


def test_jour_manquant_refuse(payload):
    del payload["donnees"]["jours"][5]

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "jours incohérents avec la fenêtre" in str(refus.value)


def test_jours_desordonnes_refuses(payload):
    payload["donnees"]["jours"] = list(reversed(payload["donnees"]["jours"]))

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "jours incohérents avec la fenêtre" in str(refus.value)


def test_doublon_de_jour_refuse(payload):
    jours = payload["donnees"]["jours"]
    jours[4] = copy.deepcopy(jours[3])

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert "jours incohérents avec la fenêtre" in str(refus.value)


def test_fenetre_trop_longue_refusee():
    debut = datetime.date(2026, 9, 1)
    fin = debut + datetime.timedelta(days=31)  # 32 jours

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(fabriquer_payload(debut, fin)))
    assert str(refus.value) == "fenêtre de 32 jours, maximum 31"


def test_forme_inconnue_refusee():
    with pytest.raises(PayloadInvalide) as refus:
        lire(b'"une chaine"')
    assert str(refus.value) == "forme de payload inconnue"


def test_jours_absents_refuses(payload):
    payload["donnees"]["jours"] = []

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert str(refus.value) == "jours absents"


def test_fenetre_invalide_refusee(payload):
    payload["donnees"]["date"] = "pas-une-date"

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert str(refus.value) == "fenêtre absente ou invalide"


def test_journee_unique_sans_date_fin():
    jour = datetime.date(2026, 10, 5)
    payload = fabriquer_payload(jour, jour)
    payload["donnees"]["date_fin"] = None

    resultat = lire(en_direct(payload))
    assert resultat.debut == resultat.fin == jour


def test_praticiens_nettoyes_et_tries():
    payload = fabriquer_payload(DEBUT, DEBUT, praticiens=("  martin bob  ", "DUPONT Alice"))
    assert lire(en_direct(payload)).praticiens == ("DUPONT Alice", "martin bob")


def test_message_d_erreur_tronque(payload):
    payload["succes"] = False
    payload["message"] = "x" * 500

    with pytest.raises(PayloadInvalide) as refus:
        lire(en_direct(payload))
    assert len(str(refus.value)) <= 200
