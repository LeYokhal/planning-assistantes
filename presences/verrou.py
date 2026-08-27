"""Verrou d'import, porté par une contrainte d'unicité.

Un seul tir endpoint à la fois : le serveur MCP Doctolib n'accepte qu'un appel
en cours. Le verrou est une ligne unique en base plutôt qu'un `select_for_update`
— la base de développement est SQLite, celle de production PostgreSQL, et le
mécanisme doit valoir pour les deux.

Un redéploiement peut interrompre un tir en cours : le verrou survit alors à son
porteur. D'où la péremption, et la requalification des lignes restées « en cours ».
"""

import datetime
import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import VerrouImport

logger = logging.getLogger(__name__)

CLE = "import"
TENTATIVES = 2


def peremption():
    """Durée au-delà de laquelle un verrou est considéré comme abandonné."""
    minutes = getattr(settings, "VERROU_IMPORT_PEREMPTION_MINUTES", 15)
    return datetime.timedelta(minutes=minutes)


def actif():
    """Renvoie le verrou en cours s'il existe ET n'est pas périmé, sinon None."""
    from django.utils import timezone

    verrou = VerrouImport.objects.filter(cle=CLE).first()
    if verrou is None:
        return None
    if verrou.pris_le < timezone.now() - peremption():
        return None
    return verrou


def prendre(motif, lot=None):
    """Prend le verrou et le renvoie, ou renvoie None si un import est en cours.

    Sur collision, un verrou périmé est repris : il est supprimé, les lignes
    restées « en cours » sont requalifiées en échec, et une seule nouvelle
    tentative est faite.
    """
    from django.utils import timezone

    for _ in range(TENTATIVES):
        try:
            with transaction.atomic():
                return VerrouImport.objects.create(
                    cle=CLE, motif=str(motif)[:60], lot=lot
                )
        except IntegrityError:
            existant = VerrouImport.objects.filter(cle=CLE).first()
            if existant is None:
                # Libéré entre-temps : on retente.
                continue
            if existant.pris_le >= timezone.now() - peremption():
                return None
            logger.warning(
                "verrou d'import perime (pris le %s) : reprise", existant.pris_le
            )
            # Le filtre sur `pris_le` évite de supprimer un verrou repris par
            # quelqu'un d'autre entre la lecture et la suppression.
            VerrouImport.objects.filter(
                pk=existant.pk, pris_le=existant.pris_le
            ).delete()
            # Import local : `services` importe `verrou`, le cycle serait direct.
            from . import services

            services.requalifier_interrompus()
    return None


def liberer(verrou):
    """Libère le verrou. Silencieux s'il a déjà disparu."""
    if verrou is None:
        return
    VerrouImport.objects.filter(pk=verrou.pk).delete()
