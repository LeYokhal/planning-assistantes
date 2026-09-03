"""Modèles des personnes du cabinet et des comptes de connexion."""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from .noms import code_pour


class Personne(models.Model):
    """Une personne du cabinet (assistante, secrétaire ou praticien).

    Toutes les colonnes utiles aux briques suivantes sont posées dès la 1a,
    mais aucune logique ne les exploite encore.

    Aucune donnée personnelle sensible n'est stockée ici : ni NSS, ni date de
    naissance, ni téléphone, ni IBAN, ni adresse postale.
    """

    class RoleMetier(models.TextChoices):
        ASSISTANTE = "assistante", "Assistante"
        SECRETAIRE = "secretaire", "Secrétaire"
        PRATICIEN = "praticien", "Praticien"

    # `null=True` est obligatoire : deux chaînes vides violeraient la contrainte
    # d'unicité dès la 2e Personne sans code.
    code = models.CharField(
        "code",
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        help_text="Posé automatiquement à la création s'il est libre. "
        "À saisir à la main en cas de collision.",
    )
    nom = models.CharField("nom", max_length=80)
    prenom = models.CharField("prénom", max_length=80)
    role_metier = models.CharField(
        "rôle métier",
        max_length=20,
        choices=RoleMetier.choices,
    )
    heures_hebdo = models.PositiveSmallIntegerField(
        "heures hebdomadaires",
        null=True,
        blank=True,
    )
    jours_fixes = models.JSONField(
        "jours fixes",
        default=list,
        blank=True,
        help_text='Liste de jours, par exemple ["Mardi", "Jeudi"].',
    )
    planifiee = models.BooleanField("planifiée", default=False)
    couleur = models.CharField("couleur", max_length=20, blank=True)
    agenda_doctolib = models.CharField("agenda Doctolib", max_length=120, blank=True)
    email_contact = models.EmailField(
        "adresse de contact",
        blank=True,
        help_text="Adresse d'invitation. Distincte de l'adresse de connexion du compte.",
    )
    actif = models.BooleanField("actif", default=True)
    cree_le = models.DateTimeField("créé le", auto_now_add=True)
    modifie_le = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "personne"
        verbose_name_plural = "personnes"
        ordering = ["nom", "prenom"]
        constraints = [
            models.UniqueConstraint(
                fields=["nom", "prenom"], name="personne_nom_prenom_unique"
            )
        ]

    def __str__(self):
        return f"{self.prenom} {self.nom}".strip()

    def save(self, *args, **kwargs):
        """Pose le code à la création s'il est libre.

        En cas de collision (même prénom, mêmes trois premières lettres de
        nom), le code reste vide : l'import le signale en avertissement et le
        cabinet le saisit à la main. Poser un code faux serait pire que ne pas
        en poser.
        """
        # Un `save(update_fields=…)` qui ne porte pas `code` ne pourrait pas
        # l'écrire : inutile d'interroger la base, et surtout pas de poser en
        # mémoire une valeur que la base n'aura jamais.
        champs = kwargs.get("update_fields")
        if not self.code and (champs is None or "code" in champs):
            candidat = code_pour(self.prenom, self.nom)
            if candidat and not (
                Personne.objects.filter(code=candidat)
                .exclude(pk=self.pk)
                .exists()
            ):
                self.code = candidat
            else:
                # NULL et non chaîne vide : `code` est unique, et deux chaînes
                # vides se heurteraient dès la seconde personne sans code.
                self.code = None
        super().save(*args, **kwargs)


class CompteManager(BaseUserManager):
    """Fabrique de comptes. Aucun mot de passe n'est jamais utilisable."""

    use_in_migrations = True

    def create_user(self, email, role="salariee", **extra):
        if not email:
            raise ValueError("Une adresse e-mail est obligatoire.")
        compte = self.model(email=self.normalize_email(email), role=role, **extra)
        compte.set_unusable_password()
        compte.save(using=self._db)
        return compte

    def create_superuser(self, email, password=None, **extra):
        """Crée un compte « cabinet » administrateur.

        L'argument `password` n'existe que pour la compatibilité avec la
        commande `createsuperuser` : il est ignoré, le mot de passe reste
        systématiquement inutilisable.
        """
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Un superutilisateur doit avoir is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Un superutilisateur doit avoir is_superuser=True.")
        extra["role"] = Compte.Role.CABINET
        return self.create_user(email, **extra)


class Compte(AbstractBaseUser, PermissionsMixin):
    """Compte de connexion, identifié par son adresse e-mail.

    La connexion se fait uniquement par lien magique (django-sesame) : aucun
    mot de passe n'est saisi, stocké de façon utilisable, ni vérifié.
    """

    class Role(models.TextChoices):
        CABINET = "cabinet", "Cabinet"
        PRINCIPALE = "principale", "Assistante principale"
        SALARIEE = "salariee", "Salariée"

    email = models.EmailField("adresse e-mail", unique=True)
    personne = models.OneToOneField(
        Personne,
        verbose_name="personne",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="compte",
    )
    role = models.CharField(
        "rôle",
        max_length=20,
        choices=Role.choices,
        default=Role.SALARIEE,
    )
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès à l'administration", default=False)
    # is_superuser, groups et user_permissions viennent de PermissionsMixin.
    # Adresse demandée par la salariée, en attente de confirmation par lien.
    # Vidée à la confirmation : c'est ce vidage qui rend le jeton à usage unique
    # (brique 3, décision L).
    email_en_attente = models.EmailField(
        "adresse en attente de confirmation", blank=True
    )
    invite_le = models.DateTimeField("invité le", null=True, blank=True)
    active_le = models.DateTimeField("activé le", null=True, blank=True)
    date_creation = models.DateTimeField("date de création", auto_now_add=True)

    objects = CompteManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "compte"
        verbose_name_plural = "comptes"
        ordering = ["email"]

    def __str__(self):
        return self.email

    def set_password(self, raw_password):
        """Neutralisé : aucun mot de passe utilisable ne peut être défini."""
        self.set_unusable_password()
