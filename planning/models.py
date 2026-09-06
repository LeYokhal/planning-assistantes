"""Versions du planning des assistantes (brique 4a).

Une ligne `PlanningVersion` = un « Enregistrer » depuis la page, pour un mois.
Elle n'est jamais modifiée ni supprimée (admin en lecture seule, patron de
`ImportPresences`) : l'historique est la preuve de ce qui a été enregistré.

Le `state` ne porte que quatre clés — `affectations`, `feries`, `feries_off`,
`notes` — nettoyées côté serveur avant l'écriture. Ni congé, ni type d'absence,
ni nom : les congés viennent de `absences` à chaque rendu, jamais du `state`.

Les champs de publication (`publiee`, `publie_le`, `publie_par`, `verifications`)
sont posés par `services.publier` (brique 4b), sur la dernière version du mois
seulement. La « version publiée du mois » est la dernière `publiee=True` par
numéro : une correction est une nouvelle version, publiée à son tour, qui
supersède la précédente. Aucune dépublication.
"""

from django.conf import settings
from django.db import models


class PlanningVersion(models.Model):
    """Une version enregistrée du planning d'un mois."""

    mois = models.CharField("mois", max_length=7)
    numero = models.PositiveIntegerField("numéro")
    state = models.JSONField("état", default=dict)
    version_de_base = models.PositiveIntegerField(
        "version de base",
        default=0,
        help_text="Numéro de la version affichée quand celle-ci a été enregistrée. 0 = aucune.",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="enregistrée par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versions_planning",
    )
    cree_le = models.DateTimeField("créée le", auto_now_add=True)
    # `[]` tant que la version n'est pas publiée (toute violation refuse
    # l'enregistrement). À la publication, compte-rendu du contrôle réussi sur
    # `DATA` recalculé : `{verifie_le, imports: [{id, empreinte}], nb_briques}`.
    # Jamais de nom, jamais de type d'absence.
    verifications = models.JSONField("vérifications", default=list, blank=True)
    publiee = models.BooleanField("publiée", default=False)
    publie_le = models.DateTimeField("publiée le", null=True, blank=True)
    publie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="publiée par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versions_planning_publiees",
    )

    class Meta:
        verbose_name = "version du planning"
        verbose_name_plural = "versions du planning"
        ordering = ("mois", "-numero")
        # La contrainte indexe déjà `mois` en première colonne : pas d'index
        # séparé.
        constraints = [
            models.UniqueConstraint(
                fields=["mois", "numero"], name="planningversion_mois_numero_unique"
            )
        ]

    def __str__(self):
        return f"planning {self.mois} v{self.numero}"
