"""Cycle de vie d'une absence : création, décision, annulation, correction.

Toutes les écritures passent par ici — les vues et l'admin n'écrivent pas de
statut à la main. C'est ce qui garantit qu'un événement d'audit et, le cas
échéant, un webhook accompagnent chaque transition.

⚠️ Aucun appel à `journaliser` de ce module ne passe le type d'absence ni la
précision. Ce qui entre dans `details` : des identifiants, des dates, des
statuts, des comptages. Rien d'autre. Le garde-fou « @ » d'`audit/services.py`
ne reconnaîtrait pas « Maladie » comme une donnée sensible : c'est à la main que
cela se tient.
"""

import datetime
import logging

from django.utils import timezone

from audit.models import Action
from audit.services import journaliser
from comptes.models import Compte

from . import calcul, webhooks
from .models import AbsenceSalariee, TypeAbsence

logger = logging.getLogger(__name__)

PAS_CORRECTION = 0.5


class ActionImpossible(Exception):
    """Geste refusé par la règle métier. Le message est affichable tel quel."""


def _retention_jours():
    """Durée de rétention en jours, ou None si le réglage est absent.

    Fail-closed (décision F) : absent = aucune purge, `a_effacer_le` laissé nul,
    et la commande de purge rattrapera le jour où le réglage apparaîtra.
    """
    from django.conf import settings

    valeur = getattr(settings, "RETENTION_ABSENCES_JOURS", None)
    try:
        jours = int(valeur)
    except (TypeError, ValueError):
        return None
    return jours if jours > 0 else None


def date_effacement(depuis=None):
    """Date de purge à poser, ou None si la rétention n'est pas réglée."""
    jours = _retention_jours()
    if jours is None:
        return None
    base = depuis or timezone.localdate()
    return base + datetime.timedelta(days=jours)


def _poser_echeance(absence):
    """Pose `a_effacer_le` si la rétention est réglée. Sans effet sinon."""
    if absence.a_effacer_le is None:
        absence.a_effacer_le = date_effacement()


def _appliquer_calcul(absence):
    """Pose les jours comptés et les DATES qui les portent.

    `jours_retenus` est figé ici, en même temps que la valeur calculée : c'est
    lui qui permettra de répartir l'absence entre les mois de paie sans jamais
    rejouer le calcul sur un morceau. Renvoie le signal éventuel.
    """
    resultat = calcul.jours_comptes_de(absence)
    absence.jours_comptes_calcules = resultat.jours
    absence.jours_retenus = resultat.dates_iso
    if not absence.corrigee:
        absence.jours_comptes = resultat.jours
    return resultat.signal


def creer(personne, type_absence, date_debut, date_fin, auteur, precision=""):
    """Crée une absence. Le type décide si elle attend une décision.

    Un type de catégorie « déclaration » est effectif immédiatement : les jours
    comptés sont posés dans la foulée, et l'échéance de purge avec.
    """
    if not calcul.est_salariee(personne):
        raise ActionImpossible(
            "Une absence ne peut porter que sur une assistante ou une secrétaire."
        )
    if date_fin < date_debut:
        raise ActionImpossible("Le dernier jour ne peut pas précéder le premier.")

    declaration = type_absence.categorie == TypeAbsence.Categorie.DECLARE
    absence = AbsenceSalariee(
        personne=personne,
        type=type_absence,
        date_debut=date_debut,
        date_fin=date_fin,
        precision=(precision or "").strip(),
        auteur=auteur if getattr(auteur, "is_authenticated", False) else None,
        statut=(
            AbsenceSalariee.Statut.DECLAREE
            if declaration
            else AbsenceSalariee.Statut.EN_ATTENTE
        ),
    )

    signal = ""
    if declaration:
        signal = _appliquer_calcul(absence)
        _poser_echeance(absence)

    absence.save()

    action = Action.ABSENCE_DECLAREE if declaration else Action.ABSENCE_DEMANDEE
    journaliser(
        action,
        qui=auteur,
        objet=absence,
        personne_id=absence.personne_id,
        debut=absence.date_debut.isoformat(),
        fin=absence.date_fin.isoformat(),
        statut=absence.statut,
    )
    logger.info(
        "absence #%s creee (statut %s, %s jour(s) de plage)",
        absence.pk,
        absence.statut,
        absence.nb_jours_plage,
    )

    webhooks.notifier(
        webhooks.EVENEMENT_DECLAREE if declaration else webhooks.EVENEMENT_DEMANDEE,
        absence,
    )
    return absence, signal


def peut_decider(absence, qui):
    """Règle K : la personne concernée ne décide pas de sa propre absence.

    La règle est assise sur la PERSONNE, pas sur l'auteur de la saisie : un
    compte supprimé laisse `auteur` nul (SET_NULL), et une règle qui s'appuierait
    sur lui deviendrait inévaluable. Seul le rôle `cabinet` tranche alors.
    """
    if qui.role == Compte.Role.CABINET:
        return True
    personne_du_decideur = getattr(qui, "personne_id", None)
    return personne_du_decideur is None or personne_du_decideur != absence.personne_id


def decider(absence, valider, qui):
    """Valide ou refuse une demande en attente."""
    if absence.statut != AbsenceSalariee.Statut.EN_ATTENTE:
        raise ActionImpossible("Cette absence n'est plus en attente de décision.")
    # Décision P, tenue aussi ici : une absence de praticien ne doit pas pouvoir
    # devenir effective, quel que soit le chemin par lequel elle a été créée.
    if not calcul.est_salariee(absence.personne):
        raise ActionImpossible(
            "Une absence ne peut porter que sur une assistante ou une secrétaire."
        )
    if not peut_decider(absence, qui):
        raise ActionImpossible(
            "Vous ne pouvez pas décider de votre propre absence : "
            "seul le cabinet peut la trancher."
        )

    absence.statut = (
        AbsenceSalariee.Statut.VALIDEE if valider else AbsenceSalariee.Statut.REFUSEE
    )
    absence.decide_par = qui
    absence.decide_le = timezone.now()

    signal = ""
    if valider:
        signal = _appliquer_calcul(absence)
        _poser_echeance(absence)

    absence.save(
        update_fields=[
            "statut",
            "decide_par",
            "decide_le",
            "jours_comptes_calcules",
            "jours_comptes",
            "jours_retenus",
            "a_effacer_le",
        ]
    )

    journaliser(
        Action.ABSENCE_DECIDEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
        statut=absence.statut,
        jours_comptes=str(absence.jours_comptes or ""),
    )
    logger.info("absence #%s decidee : %s", absence.pk, absence.statut)

    webhooks.notifier(webhooks.EVENEMENT_DECIDEE, absence)
    return signal


def annuler(absence, qui):
    """Annule une demande encore en attente. Auditée, sans webhook."""
    if absence.statut != AbsenceSalariee.Statut.EN_ATTENTE:
        raise ActionImpossible("Seule une demande en attente peut être annulée.")

    absence.statut = AbsenceSalariee.Statut.ANNULEE
    absence.save(update_fields=["statut"])

    journaliser(
        Action.ABSENCE_ANNULEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
    )
    logger.info("absence #%s annulee", absence.pk)
    return absence


def corriger(absence, valeur, qui):
    """Pose à la main la valeur retenue des jours comptés.

    Seule porte d'entrée des demi-journées (décision O) : le pas est de 0,5, la
    valeur est bornée par la durée de la plage, et la valeur calculée n'est
    jamais touchée — c'est ce qui rend l'écart lisible six mois plus tard.
    """
    from decimal import Decimal, InvalidOperation

    try:
        retenu = Decimal(str(valeur)).quantize(Decimal("0.1"))
    except (InvalidOperation, ValueError, TypeError):
        raise ActionImpossible("Valeur illisible.") from None

    if retenu < 0:
        raise ActionImpossible("Les jours comptés ne peuvent pas être négatifs.")
    if retenu > absence.nb_jours_plage:
        raise ActionImpossible(
            f"Les jours comptés ne peuvent pas dépasser la durée de l'absence "
            f"({absence.nb_jours_plage} jour(s))."
        )
    if (retenu % Decimal(str(PAS_CORRECTION))) != 0:
        raise ActionImpossible("Les jours comptés vont par pas d'une demi-journée.")

    absence.jours_comptes = retenu
    absence.corrige_par = qui
    absence.corrige_le = timezone.now()
    absence.save(update_fields=["jours_comptes", "corrige_par", "corrige_le"])

    journaliser(
        Action.ABSENCE_CORRIGEE,
        qui=qui,
        objet=absence,
        personne_id=absence.personne_id,
        calcules=str(absence.jours_comptes_calcules or ""),
        retenus=str(retenu),
    )
    logger.info(
        "absence #%s corrigee : %s -> %s",
        absence.pk,
        absence.jours_comptes_calcules,
        retenu,
    )
    return absence


def recalculer(absence):
    """Rejoue le calcul. Ne touche JAMAIS une absence corrigée à la main."""
    if not absence.effective:
        return False
    resultat = calcul.jours_comptes_de(absence)
    champs = ["jours_comptes_calcules", "jours_retenus"]
    absence.jours_comptes_calcules = resultat.jours
    absence.jours_retenus = resultat.dates_iso
    if not absence.corrigee:
        absence.jours_comptes = resultat.jours
        champs.append("jours_comptes")
    absence.save(update_fields=champs)
    return True


def absences_du_mois(debut, fin, pour_la_paie=True):
    """Absences effectives recouvrant la plage, prêtes pour la paie."""
    requete = AbsenceSalariee.objects.filter(
        statut__in=AbsenceSalariee.STATUTS_EFFECTIFS,
        date_debut__lte=fin,
        date_fin__gte=debut,
    ).select_related("personne", "type")
    if pour_la_paie:
        requete = requete.filter(type__paie=True)
    return requete.order_by("personne__nom", "personne__prenom", "date_debut")
