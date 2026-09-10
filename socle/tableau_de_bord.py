"""Tableau de bord de la principale et du cabinet (brique 6a, C6.10 / C6.12).

`construire` assemble tout le contexte sans requête HTTP : la vue ne fait que
rendre, et la date du jour est injectable pour figer l'horizon dans les tests.
Rien de nouveau n'est calculé : versions (`planning.services`), couverture
Doctolib (`presences.services.imports_par_date`, la sélection jour par jour de
`planning.donnees`), demandes en attente (la requête de `/absences/`).
"""

import datetime

from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from absences import services as services_absences
from absences.models import AbsenceSalariee
from comptes.models import Compte, Personne
from planning import services as services_planning
from planning.models import PlanningVersion
from presences import services as services_presences
from presences.fenetres import libelle_mois, mois_suivant, plage_mois
from presences.models import ImportPresences

# Carte « Demandes à décider » : au-delà, « Voir tout » mène à /absences/ (D-9).
NB_DEMANDES_AFFICHEES = 5

AUCUNE_VERSION = "Aucune version enregistrée"


def construire(utilisateur, aujourd_hui=None):
    """Le contexte du gabarit `socle/tableau_de_bord.html`."""
    courant = (aujourd_hui or timezone.localdate()).strftime("%Y-%m")
    avec_version = set(PlanningVersion.objects.values_list("mois", flat=True))
    a_venir = sorted(mois for mois in avec_version if mois > courant)
    passes = sorted((mois for mois in avec_version if mois < courant), reverse=True)

    couverts = _jours_couverts(a_venir + [courant] + passes)
    lignes_a_venir = [_ligne(mois, couverts) for mois in a_venir]
    ligne_courante = _ligne(courant, couverts)
    lignes_passees = [_ligne(mois, couverts) for mois in passes]

    preparer = mois_suivant(courant)
    while preparer in avec_version:
        preparer = mois_suivant(preparer)

    # Même requête que `absences_a_decider` ; tranchée à l'affichage, pas en base :
    # les demandes en attente se comptent sur les doigts.
    en_attente = list(
        AbsenceSalariee.objects.filter(statut=AbsenceSalariee.Statut.EN_ATTENTE)
        .select_related("personne", "type")
        .order_by("date_debut")
    )
    demandes = en_attente[:NB_DEMANDES_AFFICHEES]
    for absence in demandes:
        absence.decidable = services_absences.peut_decider(absence, utilisateur)

    reussis = ImportPresences.objects.filter(statut=ImportPresences.Statut.REUSSI)
    return {
        "planning": {
            "importees_jusqu_au": reussis.aggregate(Max("fin"))["fin__max"],
            "a_venir": lignes_a_venir,
            "en_cours": ligne_courante,
            "passes": lignes_passees,
            "rubriques": [
                {"titre": "À venir", "lignes": lignes_a_venir, "repliee": False},
                {"titre": "En cours", "lignes": [ligne_courante], "repliee": False},
                {"titre": "Passés", "lignes": lignes_passees, "repliee": True},
            ],
            "preparer": preparer,
            "preparer_libelle": libelle_mois(preparer),
            "preparer_url": reverse("planning:mois", kwargs={"mois": preparer}),
        },
        "demandes": demandes,
        "nb_demandes": len(en_attente),
        "dernier_import": reussis.defer("payload").order_by("-importe_le", "-id").first(),
        "nb_planifiees": Personne.objects.filter(planifiee=True, actif=True).count(),
        "peut_importer": utilisateur.role == Compte.Role.CABINET,
    }


def _jours_couverts(mois_listes):
    """Les jours (ISO) couverts par un import réussi, sur l'enveloppe des mois listés — un seul appel."""
    plages = [plage_mois(mois) for mois in mois_listes]
    debut = min(plage.debut for plage in plages)
    fin = max(plage.fin for plage in plages)
    return set(services_presences.imports_par_date(debut, fin))


def _ligne(mois, couverts):
    """Une ligne de la carte Planning : état de version (D-5), couverture Doctolib (D-6, C7.10), lien."""
    derniere = services_planning.derniere_version(mois)
    publiee = services_planning.version_publiee(mois)
    historique = publiee is not None and services_planning.est_historique(publiee)
    if derniere is None:
        etat, classe = AUCUNE_VERSION, "neutre"
    elif publiee is None:
        etat, classe = f"Version {derniere.numero} · non publiée", "attente"
    elif publiee.numero == derniere.numero:
        etat, classe = f"Publiée (v{publiee.numero})", "ok"
    else:
        etat, classe = f"Version {derniere.numero} — publiée : v{publiee.numero}", "attente"

    plage = plage_mois(mois)
    non_couvert = any(
        jour.isoformat() not in couverts for jour in _jours(plage.debut, plage.fin)
    )
    route = "planning:historique" if historique else "planning:mois"
    return {
        "mois": mois,
        "libelle": libelle_mois(mois),
        "etat": etat,
        "classe": classe,
        "historique": historique,
        # Un mois historique n'a pas de présences Doctolib et n'en aura pas (C7.10).
        "manquantes": non_couvert and not historique,
        "url": reverse(route, kwargs={"mois": mois}),
    }


def _jours(debut, fin):
    jour = debut
    while jour <= fin:
        yield jour
        jour += datetime.timedelta(days=1)
