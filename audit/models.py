"""Journal d'audit : trace des actions sensibles, sans donnée personnelle."""

from django.conf import settings
from django.db import models


class Action(models.TextChoices):
    """Actions journalisées par les briques 1a, 1b et 2."""

    LIEN_DEMANDE = "lien_demande", "Lien de connexion demandé"
    LIEN_REFUSE = "lien_refuse", "Lien de connexion refusé"
    CONNEXION_REFUSEE = "connexion_refusee", "Connexion refusée (jeton)"
    CONNEXION = "connexion", "Connexion"
    DECONNEXION = "deconnexion", "Déconnexion"
    INVITATION_ENVOYEE = "invitation_envoyee", "Invitation envoyée"
    COMPTE_CABINET_ASSURE = "compte_cabinet_assure", "Compte cabinet assuré"
    LIEN_SECOURS = "lien_secours", "Lien de secours généré"
    COMPTE_CREE = "compte_cree", "Compte créé"
    COMPTE_MODIFIE = "compte_modifie", "Compte modifié"
    PERSONNE_CREEE = "personne_creee", "Personne créée"
    PERSONNE_MODIFIEE = "personne_modifiee", "Personne modifiée"
    PERSONNE_SUPPRIMEE = "personne_supprimee", "Personne supprimée"
    COMPTE_SUPPRIME = "compte_supprime", "Compte supprimé"
    IMPORT_DEMANDE = "import_demande", "Import demandé"
    IMPORT_REUSSI = "import_reussi", "Import réussi"
    IMPORT_ECHEC = "import_echec", "Import en échec"
    ACCES_REFUSE = "acces_refuse", "Accès refusé (rôle)"
    PERSONNES_IMPORTEES = "personnes_importees", "Fiche personnel importée"
    APPARIEMENT_APPLIQUE = "appariement_applique", "Appariement Doctolib appliqué"
    COMPTES_CREES = "comptes_crees", "Comptes de connexion créés"
    # Brique 3. ⚠️ Aucun de ces événements ne porte le TYPE d'absence ni la
    # PRÉCISION dans `details` : ce sont des données de santé potentielles, et
    # le garde-fou « @ » ne les reconnaîtrait pas.
    ABSENCE_DEMANDEE = "absence_demandee", "Absence demandée"
    ABSENCE_DECLAREE = "absence_declaree", "Absence déclarée"
    ABSENCE_DECIDEE = "absence_decidee", "Absence décidée"
    ABSENCE_ANNULEE = "absence_annulee", "Absence annulée"
    ABSENCE_CORRIGEE = "absence_corrigee", "Jours comptés corrigés"
    ABSENCE_PURGEE = "absence_purgee", "Absence purgée (rétention)"
    PAIE_CONSULTEE = "paie_consultee", "Données de paie consultées"
    ADRESSE_CHANGEE = "adresse_changee", "Adresse de connexion changée"


class EvenementAudit(models.Model):
    """Un événement du journal d'audit.

    `details` ne contient JAMAIS d'adresse e-mail, de jeton ni de secret :
    l'identité éventuelle est portée par la clé étrangère `qui`.
    """

    quand = models.DateTimeField("quand", auto_now_add=True, db_index=True)
    qui = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="qui",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evenements_audit",
    )
    # L'index est requis : la recette filtre le journal sur l'action.
    action = models.CharField("action", max_length=60, db_index=True)
    type_objet = models.CharField("type d'objet", max_length=40, blank=True)
    id_objet = models.CharField("identifiant d'objet", max_length=40, blank=True)
    details = models.JSONField("détails", default=dict, blank=True)

    class Meta:
        verbose_name = "événement d'audit"
        verbose_name_plural = "événements d'audit"
        ordering = ["-quand", "-id"]

    def __str__(self):
        return f"{self.quand:%Y-%m-%d %H:%M} {self.action}"
