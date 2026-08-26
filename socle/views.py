"""Vues du socle : page de santé et accueil."""

import logging

from django.contrib.auth.decorators import login_required
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def sante(request):
    """Page de santé publique, interrogée par Railway.

    Aucune authentification, et aucun détail d'erreur exposé : le message
    d'exception part dans les logs, jamais dans la réponse HTTP.
    """
    etat = {"statut": "ok", "base": "ok", "migrations_en_attente": 0}
    code = 200

    connexion = connections["default"]
    try:
        with connexion.cursor() as curseur:
            curseur.execute("SELECT 1")
            curseur.fetchone()
    except Exception:
        logger.exception("sante : la base de donnees ne repond pas")
        return JsonResponse({"statut": "degrade", "base": "ko"}, status=503)

    try:
        executeur = MigrationExecutor(connexion)
        cible = executeur.loader.graph.leaf_nodes()
        etat["migrations_en_attente"] = len(executeur.migration_plan(cible))
    except Exception:
        logger.exception("sante : impossible de calculer les migrations en attente")
        return JsonResponse({"statut": "degrade", "base": "ok"}, status=503)

    if etat["migrations_en_attente"]:
        etat["statut"] = "degrade"
        code = 503

    return JsonResponse(etat, status=code)


@login_required
def accueil(request):
    """Page d'accueil de l'application, réservée aux comptes connectés."""
    return render(request, "socle/accueil.html")
