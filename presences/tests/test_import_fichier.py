"""Recette de l'import d'un fichier S7 depuis l'application."""

import datetime
import io
from unittest.mock import Mock, patch

import pytest

from audit.models import EvenementAudit
from presences.models import ImportPresences

from .fabrique import en_direct, en_wrapper_liste, fabriquer_payload

pytestmark = pytest.mark.django_db

URL_IMPORT = "/presences/importer/"
DEBUT = datetime.date(2026, 9, 28)
FIN = datetime.date(2026, 10, 28)


@pytest.fixture
def poser_webhook(settings):
    settings.N8N_IMPORT_WEBHOOK_URL = "http://n8n.example.org/webhook/import-planning"
    settings.N8N_WEBHOOK_SECRET = "secret-de-test"
    settings.APP_URL = "http://testserver"


def _fichier(octets, nom="export-s7.json"):
    fichier = io.BytesIO(octets)
    fichier.name = nom
    return fichier


def test_anonyme_redirige_vers_la_connexion(client):
    reponse = client.get(URL_IMPORT)
    assert reponse.status_code == 302
    assert reponse.url.startswith("/connexion/?next=")


def test_salariee_refusee_et_journalisee(client, salariee, connecter):
    connecter(client, salariee)

    assert client.get(URL_IMPORT).status_code == 403

    evenement = EvenementAudit.objects.get(action="acces_refuse")
    assert evenement.qui == salariee
    assert evenement.details == {"vue": "importer_fichier"}


def test_principale_refusee(client, principale, connecter):
    connecter(client, principale)
    assert client.get(URL_IMPORT).status_code == 403


def test_cabinet_voit_le_formulaire(client, cabinet, connecter):
    connecter(client, cabinet)
    reponse = client.get(URL_IMPORT)

    assert reponse.status_code == 200
    assert "Importer" in reponse.content.decode()


def test_import_wrapper_liste(client, cabinet, connecter, poser_webhook):
    connecter(client, cabinet)
    octets = en_wrapper_liste(fabriquer_payload(DEBUT, FIN))

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        reponse = client.post(URL_IMPORT, {"fichier": _fichier(octets)})

    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.REUSSI
    assert import_.source == ImportPresences.Source.FICHIER
    assert import_.forme == "wrapper_liste"
    assert import_.debut == DEBUT and import_.fin == FIN
    assert import_.invariant_ok is True
    assert import_.nb_jours == 31 and import_.nb_lignes == 62
    assert import_.nom_fichier == "export-s7.json"
    assert import_.importe_par == cabinet
    assert import_.termine_le is not None
    assert import_.taille == len(octets)

    assert reponse.status_code == 302
    assert reponse.url == "/presences/2026-10/"

    corps = poste.call_args[1]["json"]
    assert corps["evenement"] == "import.termine"
    assert corps["lien"].endswith("/presences/2026-10/")


def test_import_jamais_en_cours(client, cabinet, connecter):
    """Un import fichier est synchrone : il ne passe pas par « en cours »."""
    connecter(client, cabinet)
    client.post(
        URL_IMPORT, {"fichier": _fichier(en_direct(fabriquer_payload(DEBUT, FIN)))}
    )

    assert not ImportPresences.objects.filter(
        statut=ImportPresences.Statut.EN_COURS
    ).exists()


def test_import_payload_direct(client, cabinet, connecter):
    connecter(client, cabinet)
    client.post(
        URL_IMPORT, {"fichier": _fichier(en_direct(fabriquer_payload(DEBUT, FIN)))}
    )

    assert ImportPresences.objects.get().forme == "direct"


def test_audit_sans_nom_de_fichier(client, cabinet, connecter):
    connecter(client, cabinet)
    client.post(
        URL_IMPORT,
        {"fichier": _fichier(en_direct(fabriquer_payload(DEBUT, FIN)), "octobre.json")},
    )

    evenement = EvenementAudit.objects.get(action="import_reussi")
    assert evenement.qui == cabinet
    assert set(evenement.details) == {
        "source",
        "mois",
        "lot",
        "invariant_ok",
        "nb_lignes",
    }
    assert "octobre.json" not in str(evenement.details)


def test_fichier_altere_refuse(client, cabinet, connecter, poser_webhook):
    """Le contrôle négatif de la recette : une ligne praticien retirée."""
    connecter(client, cabinet)
    payload = fabriquer_payload(DEBUT, FIN)
    del payload["donnees"]["jours"][3]["praticiens"][0]

    with patch(
        "presences.webhooks.requests.post", return_value=Mock(status_code=200)
    ) as poste:
        reponse = client.post(
            URL_IMPORT, {"fichier": _fichier(en_direct(payload))}, follow=True
        )

    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur.startswith("écart enveloppe")
    assert import_.invariant_ok is False
    assert import_.payload is None

    contenu = reponse.content.decode()
    assert f"Import #{import_.pk} en échec" in contenu
    assert "écart enveloppe" in contenu
    assert poste.call_args[1]["json"]["evenement"] == "import.echec"
    assert EvenementAudit.objects.filter(action="import_echec").exists()


def test_fichier_non_json_refuse(client, cabinet, connecter):
    connecter(client, cabinet)
    client.post(URL_IMPORT, {"fichier": _fichier(b"pas du json")})

    import_ = ImportPresences.objects.get()
    assert import_.statut == ImportPresences.Statut.ECHEC
    assert import_.erreur == "JSON illisible"
    # L'invariant n'a pas pu être évalué : ni vrai ni faux.
    assert import_.invariant_ok is None


def test_extension_refusee(client, cabinet, connecter):
    connecter(client, cabinet)
    reponse = client.post(
        URL_IMPORT,
        {"fichier": _fichier(en_direct(fabriquer_payload(DEBUT, FIN)), "export.txt")},
    )

    assert reponse.status_code == 200
    assert "extension .json" in reponse.content.decode()
    assert ImportPresences.objects.count() == 0


def test_fichier_trop_volumineux_refuse(client, cabinet, connecter):
    connecter(client, cabinet)
    enorme = b"{" + b" " * (5 * 1024 * 1024 + 1)

    reponse = client.post(URL_IMPORT, {"fichier": _fichier(enorme)})

    assert reponse.status_code == 200
    assert "trop volumineux" in reponse.content.decode()
    assert ImportPresences.objects.count() == 0


def _messages(reponse):
    """Messages affichés, hors échappement HTML."""
    return [str(message) for message in reponse.context["messages"]]


def test_doublon_signale(client, cabinet, connecter):
    connecter(client, cabinet)
    octets = en_direct(fabriquer_payload(DEBUT, FIN))

    client.post(URL_IMPORT, {"fichier": _fichier(octets)})
    premier = ImportPresences.objects.get()

    reponse = client.post(URL_IMPORT, {"fichier": _fichier(octets)}, follow=True)

    assert ImportPresences.objects.count() == 2
    assert f"Identique à l'import #{premier.pk} déjà en base." in _messages(reponse)


def test_import_distinct_non_signale_comme_doublon(client, cabinet, connecter):
    connecter(client, cabinet)

    client.post(
        URL_IMPORT, {"fichier": _fichier(en_direct(fabriquer_payload(DEBUT, FIN)))}
    )
    reponse = client.post(
        URL_IMPORT,
        {
            "fichier": _fichier(
                en_direct(
                    fabriquer_payload(
                        datetime.date(2026, 10, 29), datetime.date(2026, 11, 1)
                    )
                )
            )
        },
        follow=True,
    )

    messages = _messages(reponse)
    assert not any("Identique" in message for message in messages)
    assert any("invariant OK" in message for message in messages)
