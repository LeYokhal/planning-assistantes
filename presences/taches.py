"""Exécution d'un lot d'import endpoint.

Le lot tourne dans un thread du processus web : deux appels de 150 s au plus,
soit très en deçà de la péremption du verrou (15 minutes). Il n'y a pas de file
d'attente, pas de worker séparé, et c'est délibéré — un tir par mois, déclenché
par n8n, ne justifie pas une pièce d'infrastructure de plus.

Un redéploiement tue le thread : le verrou périme, les lignes restées « en
cours » sont requalifiées « interrompu » à la reprise suivante.
"""

import logging
import threading

from django.conf import settings
from django.db import connections

from . import services, webhooks
from .client_doctolib import EndpointErreur, EndpointInactif, appeler
from .models import ImportPresences
from .verrou import liberer

logger = logging.getLogger(__name__)


def lancer_lot_endpoint(plage, lot, verrou):
    """Lance le lot, en thread ou en direct selon `IMPORT_EN_ARRIERE_PLAN`."""
    if getattr(settings, "IMPORT_EN_ARRIERE_PLAN", True):
        threading.Thread(
            target=executer_lot_endpoint,
            args=(plage, lot, verrou),
            name=f"import-{lot}",
            daemon=True,
        ).start()
    else:
        executer_lot_endpoint(plage, lot, verrou)


def executer_lot_endpoint(plage, lot, verrou):
    """Enchaîne les fenêtres du mois EN SÉRIE, puis notifie n8n.

    Arrêt à la première fenêtre en échec : un lot partiel ne doit jamais être
    présenté comme réussi.
    """
    imports = []
    try:
        for debut, fin in plage.fenetres:
            import_ = services.creer_import_endpoint(plage.mois, lot, debut, fin)
            imports.append(import_)

            try:
                contenu, duree_ms = appeler(debut, fin)
            except (EndpointInactif, EndpointErreur) as erreur:
                services.echouer_import(import_, str(erreur))
                break

            services.terminer_import(
                import_, contenu, duree_ms=duree_ms, fenetre_attendue=(debut, fin)
            )
            if import_.statut != ImportPresences.Statut.REUSSI:
                break

        webhooks.notifier_lot(imports)

    except Exception as erreur:
        # Seul le type d'erreur est journalisé : son message peut contenir
        # l'URL de l'endpoint.
        logger.error("lot %s : erreur imprevue (%s)", lot, type(erreur).__name__)
        if imports and imports[-1].statut == ImportPresences.Statut.EN_COURS:
            services.echouer_import(
                imports[-1], f"erreur imprévue ({type(erreur).__name__})"
            )
        try:
            webhooks.notifier_lot(imports)
        except Exception:  # noqa: BLE001 - la notification ne doit rien casser
            logger.error("lot %s : notification impossible", lot)

    finally:
        liberer(verrou)
        # Le thread a ouvert ses propres connexions : les laisser ouvertes
        # épuiserait le pool de la base.
        connections.close_all()
