"""Modèles du socle : compteur de la limitation de débit.

Le cache Django n'est pas utilisé, délibérément : `DatabaseCache.incr` hérite
de `BaseCache.incr`, qui lit puis écrit sans verrou (incréments perdus sous
deux workers gunicorn) et repousse la durée de vie de la clé à chaque appel,
transformant une fenêtre fixe en blocage glissant. Ce modèle porte le compteur,
et `socle/debit.py` l'incrémente par une mise à jour atomique côté base.
"""

from django.db import models


class CompteurDebit(models.Model):
    """Compteur d'une fenêtre fixe, par portée et identifiant (empreinte). Voir socle/debit.py."""

    cle = models.CharField("clé", max_length=80)
    fenetre_debut = models.PositiveBigIntegerField("début de fenêtre")   # secondes epoch
    nb = models.PositiveIntegerField("nombre", default=0)

    class Meta:
        verbose_name = "compteur de débit"
        verbose_name_plural = "compteurs de débit"
        constraints = [
            models.UniqueConstraint(
                fields=["cle", "fenetre_debut"], name="compteurdebit_cle_fenetre_unique"
            )
        ]
        indexes = [models.Index(fields=["fenetre_debut"])]

    def __str__(self):
        return f"{self.cle} @{self.fenetre_debut} : {self.nb}"
