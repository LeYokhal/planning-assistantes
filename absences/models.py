"""Modèles des absences des salariées.

Deux tables : le référentiel des types (`TypeAbsence`, alimenté par migration de
données) et les absences elles-mêmes (`AbsenceSalariee`).

⚠️ Contrainte structurante de la brique : ni le TYPE d'absence ni la PRÉCISION
ne sortent jamais d'ici vers le journal d'audit, les logs applicatifs ou un
webhook. « Maladie » est une donnée de santé, et une précision libre peut en
être une aussi. Le garde-fou `@` d'`audit/services.py` ne protège pas de cela :
il se tient à la main, et des tests dédiés le prouvent.
"""

from django.conf import settings
from django.db import models

from comptes.models import Personne

# Rôles métier dont une absence peut relever (décision P). Les praticiens ne
# sont pas des salariées du planning : la formule des jours comptés n'a aucun
# sens pour eux.
ROLES_SALARIES = (Personne.RoleMetier.ASSISTANTE, Personne.RoleMetier.SECRETAIRE)


class TypeAbsence(models.Model):
    """Un type d'absence. Libellés repris du select Notion, non corrigés."""

    class Categorie(models.TextChoices):
        DEMANDE = "demande", "Soumis à décision"
        DECLARE = "declare", "Déclaration (effective immédiatement)"

    libelle = models.CharField("libellé", max_length=60, unique=True)
    bloquant = models.BooleanField(
        "bloquant",
        default=True,
        help_text="Retire une journée au planning. Les types informatifs ne le font pas.",
    )
    categorie = models.CharField(
        "catégorie",
        max_length=10,
        choices=Categorie.choices,
        default=Categorie.DECLARE,
    )
    paie = models.BooleanField(
        "compté pour la paie",
        default=False,
        help_text="Entre dans les données transmises pour la paie.",
    )
    actif = models.BooleanField("actif", default=True)
    ordre = models.PositiveSmallIntegerField(
        "ordre", default=0, help_text="Ordre d'affichage dans les listes déroulantes."
    )

    class Meta:
        verbose_name = "type d'absence"
        verbose_name_plural = "types d'absence"
        ordering = ["ordre", "libelle"]

    def __str__(self):
        return self.libelle


class AbsenceSalariee(models.Model):
    """Une absence d'une salariée, demandée ou déclarée.

    Jamais effacée hors purge de rétention : le statut `annulee` tient lieu de
    suppression douce, et l'audit porte les transitions.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        VALIDEE = "validee", "Validée"
        REFUSEE = "refusee", "Refusée"
        ANNULEE = "annulee", "Annulée"
        DECLAREE = "declaree", "Déclarée"

    # Statuts sous lesquels l'absence compte vraiment : c'est la définition de
    # `effective`, jamais stockée (décision C).
    STATUTS_EFFECTIFS = (Statut.VALIDEE, Statut.DECLAREE)

    personne = models.ForeignKey(
        Personne,
        verbose_name="personne",
        on_delete=models.PROTECT,
        related_name="absences",
        limit_choices_to={"role_metier__in": ROLES_SALARIES},
    )
    date_debut = models.DateField("premier jour")
    date_fin = models.DateField("dernier jour")
    type = models.ForeignKey(
        TypeAbsence,
        verbose_name="type",
        on_delete=models.PROTECT,
        related_name="absences",
    )
    statut = models.CharField(
        "statut",
        max_length=12,
        choices=Statut.choices,
        db_index=True,
    )
    precision = models.CharField(
        "précision",
        max_length=120,
        blank=True,
        help_text="Facultatif. N'apparaît jamais dans le journal, les logs ni un webhook.",
    )

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="saisie par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="absences_saisies",
    )
    cree_le = models.DateTimeField("créée le", auto_now_add=True)

    decide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="décidée par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="absences_decidees",
    )
    decide_le = models.DateTimeField("décidée le", null=True, blank=True)

    # Décimal et non flottant : c'est de la paie. Une demi-journée s'obtient
    # par correction manuelle (décision O), jamais par la saisie.
    jours_comptes_calcules = models.DecimalField(
        "jours comptés (calculés)",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    jours_comptes = models.DecimalField(
        "jours comptés (retenus)",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    # Les DATES qui portent les jours comptés, en ISO. C'est ce qui permet de
    # répartir une absence à cheval entre deux mois de paie sans jamais rejouer
    # le calcul sur un morceau — un recoupement appliquerait le plafond
    # hebdomadaire une fois par morceau. Figées au calcul : un changement
    # ultérieur de `regles.json` ne redistribue pas une paie déjà envoyée.
    jours_retenus = models.JSONField(
        "jours retenus",
        default=list,
        blank=True,
        help_text="Dates ISO des jours comptés. Sert à la répartition par mois.",
    )
    corrige_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="corrigée par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="absences_corrigees",
    )
    corrige_le = models.DateTimeField("corrigée le", null=True, blank=True)

    a_effacer_le = models.DateField("à effacer le", null=True, blank=True)

    class Meta:
        verbose_name = "absence"
        verbose_name_plural = "absences"
        ordering = ["-date_debut", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__gte=models.F("date_debut")),
                name="absence_dates_ordonnees",
            )
        ]
        indexes = [models.Index(fields=["personne", "date_debut"])]

    def __str__(self):
        return f"absence #{self.pk} du {self.date_debut} au {self.date_fin}"

    @property
    def effective(self):
        """Vrai si l'absence compte : validée ou déclarée. Jamais stockée."""
        return self.statut in self.STATUTS_EFFECTIFS

    @property
    def corrigee(self):
        """Vrai si la valeur retenue a été posée à la main."""
        return self.corrige_le is not None

    @property
    def nb_jours_plage(self):
        """Nombre de jours calendaires de la plage, bornes comprises."""
        return (self.date_fin - self.date_debut).days + 1
