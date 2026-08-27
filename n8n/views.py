"""API entrante appelée par n8n.

Deux routes en brique 1b : santé et déclenchement d'un import. Les briques 2 à 5
en ajouteront (personnes, paie, publication, purge). Tout est en JSON, sans
session, et rien n'est renvoyé qui ne soit un identifiant, une fenêtre ou un
comptage.
"""

import json
import logging
import uuid

from django.http import JsonResponse

from audit.models import Action
from audit.services import journaliser
from presences import verrou
from presences.fenetres import plage_mois
from presences.services import requalifier_interrompus
from presences.taches import lancer_lot_endpoint

from .securite import secret_n8n_requis

logger = logging.getLogger(__name__)


def _methode_non_autorisee():
    """405 en JSON : le reste de l'API n'émet jamais de HTML."""
    return JsonResponse({"erreur": "methode_non_autorisee"}, status=405)


@secret_n8n_requis
def sante(request):
    """Sonde de l'API : l'application répond-elle, un import est-il en cours ?"""
    if request.method != "GET":
        return _methode_non_autorisee()

    # Un verrou périmé ne doit pas faire croire à n8n qu'un import tourne
    # encore : sans cela, un redéploiement raté bloquerait la sonde pour
    # toujours.
    requalifier_interrompus()
    return JsonResponse(
        {"statut": "ok", "import_en_cours": verrou.actif() is not None}
    )


@secret_n8n_requis
def declencher_import(request):
    """Demande un tir endpoint sur un mois. Répond 202 et rend la main.

    ⚠️ Le chemin endpoint est inactif tant que la brique 0 n'est pas livrée :
    le lot part, la première fenêtre échoue « endpoint inactif », et n8n reçoit
    un webhook `import.echec`. C'est le comportement attendu en 1b.
    """
    if request.method != "POST":
        return _methode_non_autorisee()

    try:
        corps = json.loads(request.body or b"")
    except ValueError:
        return JsonResponse(
            {"accepte": False, "raison": "corps_invalide"}, status=400
        )
    if not isinstance(corps, dict):
        return JsonResponse(
            {"accepte": False, "raison": "corps_invalide"}, status=400
        )

    mois = corps.get("mois")
    if not isinstance(mois, str):
        return JsonResponse({"accepte": False, "raison": "mois_invalide"}, status=400)
    try:
        plage = plage_mois(mois)
    except ValueError:
        return JsonResponse({"accepte": False, "raison": "mois_invalide"}, status=400)

    requalifier_interrompus()

    lot = uuid.uuid4()
    prise = verrou.prendre(f"endpoint {mois}", lot)
    if prise is None:
        return JsonResponse(
            {"accepte": False, "raison": "import_en_cours"}, status=409
        )

    journaliser(
        Action.IMPORT_DEMANDE, mois=mois, lot=str(lot), source="endpoint"
    )

    try:
        lancer_lot_endpoint(plage, lot, prise)
    except Exception as erreur:
        verrou.liberer(prise)
        logger.error("lot %s : lancement impossible (%s)", lot, type(erreur).__name__)
        return JsonResponse(
            {"accepte": False, "raison": "lancement_impossible"}, status=500
        )

    return JsonResponse(
        {
            "accepte": True,
            "lot": str(lot),
            "mois": mois,
            "fenetres": [
                [debut.isoformat(), fin.isoformat()] for debut, fin in plage.fenetres
            ],
        },
        status=202,
    )
