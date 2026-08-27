"""Modèles de l'import des présences (payload S7 `consulter_jours_travail`).

Une ligne `ImportPresences` = une FENÊTRE d'appel (un payload). Elle n'est
jamais modifiée après la fin de son import, ni supprimée : l'historique est la
preuve de ce qui est entré dans l'application. Un import fautif est simplement
dépassé par un import plus récent couvrant les mêmes jours.

Aucune donnée patient n'est stockée : le payload S7 ne contient que des agendas,
des créneaux et des comptages.
"""

import uuid

from django.conf import settings
from django.db import models


class ImportPresences(models.Model):
    """Une fenêtre importée, réussie ou en échec."""

    class Source(models.TextChoices):
        FICHIER = "fichier", "Fichier"
        ENDPOINT = "endpoint", "Endpoint"

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        REUSSI = "reussi", "Réussi"
        ECHEC = "echec", "Échec"

    source = models.CharField("source", max_length=10, choices=Source.choices)
    statut = models.CharField(
        "statut",
        max_length=10,
        choices=Statut.choices,
        db_index=True,
    )
    # Regroupe les fenêtres d'un même tir. Un import fichier est un lot à lui seul.
    lot = models.UUIDField("lot", default=uuid.uuid4, editable=False, db_index=True)
    # « AAAA-MM » du tir endpoint. Vide pour un fichier : une fenêtre peut
    # chevaucher deux mois, le mois n'est pas une propriété du payload.
    mois = models.CharField("mois", max_length=7, blank=True)
    debut = models.DateField("début de fenêtre", null=True, blank=True)
    fin = models.DateField("fin de fenêtre", null=True, blank=True)
    # Payload DÉBALLÉ : {"succes", "message", "donnees"}. Le wrapper de
    # l'interface claude.ai n'est pas conservé ; sa forme l'est (`forme`).
    payload = models.JSONField("payload", null=True, blank=True)
    forme = models.CharField("forme reçue", max_length=20, blank=True)
    empreinte = models.CharField("empreinte SHA-256", max_length=64, blank=True)
    taille = models.PositiveIntegerField("taille reçue (octets)", default=0)
    message = models.TextField("message du payload", blank=True)
    invariant_ok = models.BooleanField("invariant vérifié", null=True, blank=True)
    nb_jours = models.PositiveIntegerField("nombre de jours", default=0)
    nb_lignes = models.PositiveIntegerField("nombre de lignes", default=0)
    nb_presents = models.PositiveIntegerField("nombre de présents", default=0)
    erreur = models.CharField("erreur", max_length=200, blank=True)
    # Jamais recopié dans le journal d'audit.
    nom_fichier = models.CharField("nom du fichier", max_length=120, blank=True)
    importe_le = models.DateTimeField("importé le", auto_now_add=True, db_index=True)
    termine_le = models.DateTimeField("terminé le", null=True, blank=True)
    importe_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="importé par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imports_presences",
    )
    duree_ms = models.PositiveIntegerField("durée de l'appel (ms)", null=True, blank=True)
    webhook_envoye = models.BooleanField("webhook envoyé", default=False)

    class Meta:
        verbose_name = "import de présences"
        verbose_name_plural = "imports de présences"
        ordering = ["-importe_le", "-id"]
        indexes = [models.Index(fields=["debut", "fin"])]

    def __str__(self):
        return f"import #{self.pk} {self.debut}→{self.fin} ({self.get_statut_display()})"


class VerrouImport(models.Model):
    """Verrou d'import, porté par une contrainte d'unicité.

    Aucun `select_for_update` : le verrou doit rester portable entre SQLite
    (développement, tests) et PostgreSQL (production). Un verrou plus vieux que
    `VERROU_IMPORT_PEREMPTION_MINUTES` est considéré comme périmé et repris.
    """

    cle = models.CharField("clé", max_length=20, unique=True)
    pris_le = models.DateTimeField("pris le", auto_now_add=True)
    motif = models.CharField("motif", max_length=60, blank=True)
    lot = models.UUIDField("lot", null=True, blank=True)

    class Meta:
        verbose_name = "verrou d'import"
        verbose_name_plural = "verrous d'import"

    def __str__(self):
        return f"{self.cle} depuis {self.pris_le:%Y-%m-%d %H:%M} ({self.motif})"
