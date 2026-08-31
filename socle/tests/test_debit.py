"""Recette de la limitation de débit.

Aucune adresse réelle : les IP sont de documentation (RFC 5737), les adresses
e-mail du domaine example.org.
"""

import logging
from unittest.mock import patch

import pytest
from django.http import HttpResponse

import socle.debit as debit
from socle.debit import (
    _classe,
    adresse_ip,
    compter,
    depasse,
    empreinte,
    limite_par_ip,
    relever_topologie,
)
from socle.models import CompteurDebit

pytestmark = pytest.mark.django_db

IP = "192.0.2.10"
AUTRE_IP = "192.0.2.11"

# Horodatage aligné sur une frontière de fenêtre de 60 s : les décalages du
# test tombent alors exactement où on les attend.
T0 = 1_000_020


@pytest.fixture(autouse=True)
def _drapeaux_releve():
    """Chaque test repart avec les drapeaux « une fois par processus » à zéro."""
    debit._topologie_relevee = False
    debit._avertissement_emis = False
    yield


# --- Comptage ----------------------------------------------------------------


def test_compter_incremente():
    assert [compter("essai", IP, 60) for _ in range(3)] == [1, 2, 3]


def test_une_seule_ligne_par_fenetre():
    for _ in range(5):
        compter("essai", IP, 60)

    assert CompteurDebit.objects.count() == 1
    assert CompteurDebit.objects.get().nb == 5


def test_fenetre_suivante_repart_a_un():
    with patch("socle.debit.maintenant", return_value=T0):
        assert compter("essai", IP, 60) == 1
        assert compter("essai", IP, 60) == 2

    # 60 secondes plus loin : nouvelle fenêtre.
    with patch("socle.debit.maintenant", return_value=T0 + 60):
        assert compter("essai", IP, 60) == 1


def test_meme_fenetre_jusqu_a_la_derniere_seconde():
    """La fenêtre est fixe : tout l'intervalle tombe sur la même ligne."""
    with patch("socle.debit.maintenant", return_value=T0):
        compter("essai", IP, 60)
    with patch("socle.debit.maintenant", return_value=T0 + 59):
        assert compter("essai", IP, 60) == 2


def test_identifiants_independants():
    compter("essai", IP, 60)

    assert compter("essai", AUTRE_IP, 60) == 1


def test_portees_independantes():
    compter("connexion", IP, 60)

    assert compter("api", IP, 60) == 1


def test_purge_des_vieilles_fenetres():
    with patch("socle.debit.maintenant", return_value=T0):
        compter("essai", IP, 60)
    assert CompteurDebit.objects.count() == 1

    # Trois fenêtres plus loin : la ligne d'origine n'a plus d'utilité.
    with patch("socle.debit.maintenant", return_value=T0 + 180):
        compter("essai", IP, 60)

    assert CompteurDebit.objects.count() == 1
    assert CompteurDebit.objects.get().fenetre_debut == T0 + 180


def test_purge_epargne_la_fenetre_precedente():
    """La fenêtre juste écoulée peut encore être écrite : on la garde."""
    with patch("socle.debit.maintenant", return_value=T0):
        compter("essai", IP, 60)
    with patch("socle.debit.maintenant", return_value=T0 + 60):
        compter("essai", IP, 60)

    assert CompteurDebit.objects.count() == 2


def test_purge_epargne_les_autres_portees():
    with patch("socle.debit.maintenant", return_value=T0):
        compter("api", IP, 60)
    with patch("socle.debit.maintenant", return_value=T0 + 180):
        compter("essai", IP, 60)

    assert CompteurDebit.objects.filter(cle__startswith="api:").exists()


def test_empreinte_ne_conserve_pas_l_identifiant():
    assert IP not in empreinte(IP)
    assert len(empreinte(IP)) == 16


def test_empreinte_insensible_a_la_casse_et_aux_espaces():
    assert empreinte(" Alice@Example.org ") == empreinte("alice@example.org")


# --- Plafond -----------------------------------------------------------------


def test_depasse_au_dela_du_plafond():
    verdicts = [depasse("essai", IP, (3, 60)) for _ in range(4)]

    assert verdicts == [False, False, False, True]


# --- Adresse IP --------------------------------------------------------------


def test_adresse_ip_prend_x_real_ip(rf):
    """Seul X-Real-IP compte : X-Forwarded-For est ignoré, quel qu'il soit."""
    requete = rf.get(
        "/",
        HTTP_X_REAL_IP="198.51.100.7",
        HTTP_X_FORWARDED_FOR="203.0.113.9, 198.51.100.200",
    )

    assert adresse_ip(requete) == "198.51.100.7"


def test_adresse_ip_x_real_ip_ipv6(rf):
    requete = rf.get("/", HTTP_X_REAL_IP="2001:db8::10")

    assert adresse_ip(requete) == "2001:db8::10"


def test_adresse_ip_sans_x_real_ip_derriere_proxy_avertit_une_fois(rf, caplog):
    """X-Real-IP manquant alors qu'un proxy est là : repli signalé une seule fois."""
    requete = rf.get(
        "/", HTTP_X_FORWARDED_FOR="203.0.113.9, 198.51.100.200", REMOTE_ADDR="192.0.2.10"
    )

    with caplog.at_level(logging.WARNING, logger="socle.debit"):
        premier = adresse_ip(requete)
        second = adresse_ip(requete)

    assert premier == second == "192.0.2.10"
    assert caplog.text.count("X-Real-IP absent ou illisible") == 1
    # Aucune valeur d'adresse ne doit fuiter dans le journal.
    assert "203.0.113.9" not in caplog.text
    assert "198.51.100.200" not in caplog.text
    assert "192.0.2.10" not in caplog.text


def test_adresse_ip_x_real_ip_illisible_retombe_sur_remote_addr(rf):
    requete = rf.get("/", HTTP_X_REAL_IP="pas-une-ip", REMOTE_ADDR="192.0.2.10")

    assert adresse_ip(requete) == "192.0.2.10"


def test_adresse_ip_sans_proxy_ne_previent_pas(rf, caplog):
    """En local (runserver), aucun en-tête proxy : REMOTE_ADDR, sans bruit."""
    requete = rf.get("/", REMOTE_ADDR="192.0.2.10")

    with caplog.at_level(logging.WARNING, logger="socle.debit"):
        resultat = adresse_ip(requete)

    assert resultat == "192.0.2.10"
    assert "X-Real-IP absent ou illisible" not in caplog.text


def test_adresse_ip_inconnue(rf):
    requete = rf.get("/")
    requete.META.pop("REMOTE_ADDR", None)

    assert adresse_ip(requete) == "inconnue"


# --- Relevé de topologie -----------------------------------------------------


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("100.64.3.4", "interne"),
        ("10.1.2.3", "privee"),
        ("127.0.0.1", "privee"),
        ("fe80::1", "privee"),
        ("198.51.100.7", "publique"),
        ("2001:db8::10", "publique"),
        ("n-importe-quoi", "illisible"),
        ("", "illisible"),
    ],
)
def test_classe(texte, attendu):
    assert _classe(texte) == attendu


def test_releve_topologie_classe_sans_valeur(rf, caplog):
    requete = rf.get(
        "/",
        HTTP_X_FORWARDED_FOR="198.51.100.7, 100.64.3.4",
        HTTP_X_REAL_IP="198.51.100.7",
        REMOTE_ADDR="100.70.1.1",
    )

    with caplog.at_level(logging.INFO, logger="socle.debit"):
        relever_topologie(requete)

    assert "x_forwarded_for=['publique', 'interne']" in caplog.text
    assert "x_real_ip=publique" in caplog.text
    assert "x_envoy_external_address=absent" in caplog.text
    assert "remote_addr=interne" in caplog.text
    # Aucune valeur d'adresse ne doit fuiter dans le journal.
    assert "198.51.100.7" not in caplog.text
    assert "100.64.3.4" not in caplog.text
    assert "100.70.1.1" not in caplog.text


def test_releve_topologie_une_seule_fois_par_processus(rf, caplog):
    requete = rf.get("/", HTTP_X_FORWARDED_FOR="198.51.100.7, 100.64.3.4")

    with caplog.at_level(logging.INFO, logger="socle.debit"):
        relever_topologie(requete)
        relever_topologie(requete)

    assert caplog.text.count("topologie proxy") == 1


# --- Décorateur --------------------------------------------------------------


def vue_temoin(request):
    return HttpResponse("passe")


def reponse_bloquee(request):
    return HttpResponse("bloque", status=429)


@pytest.fixture
def vue_limitee():
    return limite_par_ip("essai", "DEBIT_ESSAI", reponse=reponse_bloquee)(vue_temoin)


def test_get_jamais_compte(rf, vue_limitee, settings):
    settings.DEBIT_ESSAI = (2, 60)

    for _ in range(10):
        assert vue_limitee(rf.get("/", REMOTE_ADDR=IP)).status_code == 200
    assert CompteurDebit.objects.count() == 0


def test_post_compte_et_bloque_au_dela(rf, vue_limitee, settings):
    settings.DEBIT_ESSAI = (10, 900)

    codes = [
        vue_limitee(rf.post("/", REMOTE_ADDR=IP)).status_code for _ in range(11)
    ]

    assert codes[:10] == [200] * 10
    assert codes[10] == 429


def test_reglage_relu_a_chaque_appel(rf, vue_limitee, settings):
    """Le NOM du réglage est passé au décorateur : la fixture agit vraiment."""
    settings.DEBIT_ESSAI = (1, 900)

    assert vue_limitee(rf.post("/", REMOTE_ADDR=IP)).status_code == 200
    assert vue_limitee(rf.post("/", REMOTE_ADDR=IP)).status_code == 429


def test_plafond_par_adresse_ip(rf, vue_limitee, settings):
    settings.DEBIT_ESSAI = (1, 900)
    vue_limitee(rf.post("/", REMOTE_ADDR=IP))
    vue_limitee(rf.post("/", REMOTE_ADDR=IP))

    # Une autre adresse repart de zéro.
    assert vue_limitee(rf.post("/", REMOTE_ADDR=AUTRE_IP)).status_code == 200


def test_journal_ne_porte_jamais_l_adresse(rf, vue_limitee, settings, caplog):
    settings.DEBIT_ESSAI = (1, 900)
    vue_limitee(rf.post("/", REMOTE_ADDR=IP))

    with caplog.at_level("WARNING", logger="socle.debit"):
        vue_limitee(rf.post("/", REMOTE_ADDR=IP))

    assert "debit depasse : essai" in caplog.text
    assert IP not in caplog.text
