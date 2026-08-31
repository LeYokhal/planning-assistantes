"""Recette du chemin endpoint (brique 0) et d'un lot complet.

⚠️ La brique 0 n'est pas livrée : aucun de ces tests ne touche au réseau, tout
passe par un bouchon sur `requests.post`. Les payloads sont fictifs.
"""

import datetime
import logging
import uuid
from unittest.mock import Mock, patch

import pytest
import requests

from presences import verrou
from presences.client_doctolib import EndpointErreur, EndpointInactif, appeler
from presences.fenetres import plage_mois
from presences.models import ImportPresences, VerrouImport
from presences.taches import executer_lot_endpoint

from .fabrique import en_direct, fabriquer_payload

pytestmark = pytest.mark.django_db

URL = "http://mcp.example.org/presences"
SECRET = "secret-endpoint-de-test"
MOIS = "2026-10"
PLAGE = plage_mois(MOIS)


@pytest.fixture
def poser_endpoint(settings):
    settings.DOCTOLIB_PRESENCES_URL = URL
    settings.DOCTOLIB_PRESENCES_SECRET = SECRET


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_IMPORT_WEBHOOK_URL = "http://n8n.example.org/webhook/import-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-webhook-de-test"
    settings.APP_URL = "http://testserver"


def _reponse(octets, statut=200, corps=None):
    """Réponse HTTP bouchonnée : contenu brut, statut, et corps JSON éventuel."""
    reponse = Mock(status_code=statut, content=octets)
    if corps is None:
        reponse.json.side_effect = ValueError("pas du json")
    else:
        reponse.json.return_value = corps
    return reponse


def _payload_de(fenetre):
    return en_direct(fabriquer_payload(*fenetre))


# --- Client -----------------------------------------------------------------


def test_endpoint_inactif_sans_variables(settings, caplog):
    settings.DOCTOLIB_PRESENCES_URL = ""
    settings.DOCTOLIB_PRESENCES_SECRET = ""

    with patch("presences.client_doctolib.requests.post") as poste:
        with pytest.raises(EndpointInactif) as refus:
            appeler(*PLAGE.fenetres[0])

    assert poste.call_count == 0
    assert "brique 0 non livrée" in str(refus.value)


def test_endpoint_inactif_sans_secret(settings):
    settings.DOCTOLIB_PRESENCES_URL = URL
    settings.DOCTOLIB_PRESENCES_SECRET = ""

    with patch("presences.client_doctolib.requests.post") as poste:
        with pytest.raises(EndpointInactif):
            appeler(*PLAGE.fenetres[0])
    assert poste.call_count == 0


def test_requete_construite(poser_endpoint):
    debut, fin = PLAGE.fenetres[0]

    with patch(
        "presences.client_doctolib.requests.post",
        return_value=_reponse(_payload_de((debut, fin))),
    ) as poste:
        contenu, duree_ms = appeler(debut, fin)

    _, arguments = poste.call_args
    assert arguments["headers"]["X-Presences-Secret"] == SECRET
    assert arguments["headers"]["Content-Type"] == "application/json"
    assert arguments["timeout"] == (10, 150)
    assert arguments["json"] == {
        "date": "2026-09-28",
        "date_fin": "2026-10-28",
        "praticien": "tous",
    }
    assert contenu
    assert duree_ms >= 0


def test_statut_non_200_leve_une_erreur(poser_endpoint):
    with patch(
        "presences.client_doctolib.requests.post",
        return_value=_reponse(
            b"", statut=503, corps={"succes": False, "message": "Doctolib indisponible"}
        ),
    ):
        with pytest.raises(EndpointErreur) as refus:
            appeler(*PLAGE.fenetres[0])

    assert str(refus.value) == "HTTP 503 : Doctolib indisponible"


def test_erreur_reseau_ne_garde_que_le_type(poser_endpoint):
    with patch(
        "presences.client_doctolib.requests.post",
        side_effect=requests.ConnectTimeout("boum " + URL),
    ):
        with pytest.raises(EndpointErreur) as refus:
            appeler(*PLAGE.fenetres[0])

    assert str(refus.value) == "endpoint injoignable (ConnectTimeout)"
    assert URL not in str(refus.value)


def test_aucun_secret_ni_url_dans_les_logs(poser_endpoint, caplog):
    debut, fin = PLAGE.fenetres[0]

    with patch(
        "presences.client_doctolib.requests.post",
        return_value=_reponse(_payload_de((debut, fin))),
    ):
        with caplog.at_level(logging.DEBUG):
            appeler(debut, fin)

    assert SECRET not in caplog.text
    assert URL not in caplog.text


# --- Lot complet ------------------------------------------------------------


class Routeur:
    """Aiguilleur d'appels HTTP pour un lot complet.

    `presences.client_doctolib.requests` et `presences.webhooks.requests`
    désignent le MÊME module : deux `patch` imbriqués sur `requests.post` se
    marcheraient dessus, et le second gagnerait. Un seul bouchon, qui aiguille
    sur l'URL appelée, teste correctement les deux chemins.
    """

    def __init__(self):
        self.reponses = []
        self.appels_endpoint = []
        self.appels_webhook = []

    def programmer(self, *reponses):
        """Empile les réponses (ou exceptions) rendues par l'endpoint."""
        self.reponses.extend(reponses)
        return self

    def __call__(self, url, **arguments):
        if url == URL:
            self.appels_endpoint.append(arguments)
            resultat = self.reponses.pop(0)
            if isinstance(resultat, Exception):
                raise resultat
            return resultat
        self.appels_webhook.append(arguments)
        return Mock(status_code=200)

    @property
    def dernier_webhook(self):
        return self.appels_webhook[-1]["json"]


@pytest.fixture
def routeur(poser_endpoint, poser_webhook):
    aiguilleur = Routeur()
    with patch("presences.client_doctolib.requests.post", side_effect=aiguilleur):
        yield aiguilleur


def _prendre_verrou():
    lot = uuid.uuid4()
    return lot, verrou.prendre(f"endpoint {MOIS}", lot)


def test_lot_complet(routeur):
    routeur.programmer(*(_reponse(_payload_de(f)) for f in PLAGE.fenetres))
    lot, prise = _prendre_verrou()

    executer_lot_endpoint(PLAGE, lot, prise)

    imports = list(ImportPresences.objects.order_by("id"))
    assert len(imports) == 2
    assert all(import_.statut == ImportPresences.Statut.REUSSI for import_ in imports)
    assert {import_.mois for import_ in imports} == {MOIS}
    assert {import_.lot for import_ in imports} == {lot}
    assert all(import_.duree_ms is not None for import_ in imports)
    assert [import_.debut for import_ in imports] == [f[0] for f in PLAGE.fenetres]
    assert [import_.fin for import_ in imports] == [f[1] for f in PLAGE.fenetres]

    # Les deux fenêtres ont bien été demandées, dans l'ordre et en série.
    assert [appel["json"]["date"] for appel in routeur.appels_endpoint] == [
        "2026-09-28",
        "2026-10-29",
    ]

    corps = routeur.dernier_webhook
    assert corps["evenement"] == "import.termine"
    assert len(corps["fenetres"]) == 2
    assert len(routeur.appels_webhook) == 1
    assert VerrouImport.objects.count() == 0


def test_lot_arrete_a_la_premiere_fenetre_en_echec(routeur):
    routeur.programmer(
        _reponse(_payload_de(PLAGE.fenetres[0])),
        _reponse(
            b"", statut=503, corps={"succes": False, "message": "Doctolib indisponible"}
        ),
    )
    lot, prise = _prendre_verrou()

    executer_lot_endpoint(PLAGE, lot, prise)

    premier, second = ImportPresences.objects.order_by("id")
    assert premier.statut == ImportPresences.Statut.REUSSI
    assert second.statut == ImportPresences.Statut.ECHEC
    assert second.erreur == "HTTP 503 : Doctolib indisponible"

    assert routeur.dernier_webhook["evenement"] == "import.echec"
    assert VerrouImport.objects.count() == 0


def test_endpoint_inactif_fait_echouer_le_lot(routeur, settings):
    """Le comportement attendu en 1b : la brique 0 n'est pas livrée."""
    settings.DOCTOLIB_PRESENCES_URL = ""
    settings.DOCTOLIB_PRESENCES_SECRET = ""
    lot, prise = _prendre_verrou()

    executer_lot_endpoint(PLAGE, lot, prise)

    assert routeur.appels_endpoint == []
    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur == "endpoint inactif (brique 0 non livrée)"
    assert import_.invariant_ok is None
    assert import_.payload is None

    assert routeur.dernier_webhook["evenement"] == "import.echec"
    assert VerrouImport.objects.count() == 0


def test_fenetre_inattendue_refusee(routeur):
    """Le payload reçu doit couvrir exactement la fenêtre demandée."""
    autre = (datetime.date(2026, 11, 2), datetime.date(2026, 11, 8))
    routeur.programmer(_reponse(_payload_de(autre)))
    lot, prise = _prendre_verrou()

    executer_lot_endpoint(PLAGE, lot, prise)

    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur.startswith("fenêtre inattendue")
    assert import_.invariant_ok is None
    assert VerrouImport.objects.count() == 0


def test_erreur_imprevue_ne_laisse_rien_en_cours(routeur, caplog):
    routeur.programmer(RuntimeError("boum"))
    lot, prise = _prendre_verrou()

    with caplog.at_level(logging.ERROR, logger="presences.taches"):
        executer_lot_endpoint(PLAGE, lot, prise)

    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur == "erreur imprévue (RuntimeError)"
    assert "RuntimeError" in caplog.text
    assert "boum" not in caplog.text
    assert VerrouImport.objects.count() == 0


def test_verrou_libere_meme_si_la_notification_echoue(routeur):
    routeur.programmer(*(_reponse(_payload_de(f)) for f in PLAGE.fenetres))
    lot, prise = _prendre_verrou()

    with patch(
        "presences.webhooks.notifier_lot", side_effect=RuntimeError("n8n muet")
    ):
        executer_lot_endpoint(PLAGE, lot, prise)

    assert VerrouImport.objects.count() == 0
