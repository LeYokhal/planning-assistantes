"""Appariement des agendas Doctolib aux praticiens de la fiche.

Port de la logique du skill v1 (`build_planning.py`, appariement des
praticiens), avec deux différences assumées :

* le skill s'arrêtait net (`sys.exit`) sur un praticien non apparié ; ici rien
  ne s'arrête — on PROPOSE, le cabinet regarde, et applique s'il est d'accord ;
* les agendas non retenus sont rendus visibles (« orphelins ») avec, quand
  c'est possible, la personne non planifiée qu'ils désignent : c'est le signal
  qu'une case « Planning » n'a pas été cochée dans Notion.

Rien n'est écrit tant que `appliquer` n'est pas appelé.
"""

import logging
from dataclasses import dataclass, field

from audit.models import Action
from audit.services import journaliser
from comptes.models import Personne
from comptes.noms import normaliser

logger = logging.getLogger(__name__)

EXACT = "exact"
APPROCHE = "approche"
PLANNING_FIXE = "planning_fixe"
AUCUN = "aucun"

# Longueur du préfixe de nom exigé par l'appariement approché, reprise du
# skill : assez pour écarter les homonymes, assez court pour absorber une
# graphie composée.
LONGUEUR_PREFIXE = 4


@dataclass(frozen=True)
class Proposition:
    """Ce que l'appariement propose pour un praticien planifié."""

    personne: Personne
    agenda: str | None
    mode: str
    agenda_actuel: str

    @property
    def change(self):
        return (self.agenda or "") != self.agenda_actuel


@dataclass(frozen=True)
class Orphelin:
    """Un agenda qu'aucun praticien planifié ne réclame."""

    agenda: str
    personne: Personne | None


@dataclass
class RapportAppariement:
    propositions: list = field(default_factory=list)
    orphelins: list = field(default_factory=list)
    agendas: tuple = ()
    compteurs: dict = field(default_factory=dict)


def _candidats_approches(personne, agendas):
    """Agendas dont un mot est le prénom et un autre commence comme le nom."""
    prenom = normaliser(personne.prenom)
    prefixe = normaliser(personne.nom)[:LONGUEUR_PREFIXE]
    if not prenom or not prefixe:
        return []
    return [
        agenda
        for agenda in agendas
        if prenom in normaliser(agenda).split()
        and any(mot.startswith(prefixe) for mot in normaliser(agenda).split())
    ]


def _reconnaitre(agenda, personnes):
    """La personne que cet agenda désigne, exactement ou approximativement."""
    cible = normaliser(agenda)
    for personne in personnes:
        if normaliser(f"{personne.nom} {personne.prenom}") == cible:
            return personne
    for personne in personnes:
        if agenda in _candidats_approches(personne, [agenda]):
            return personne
    return None


def apparier(agendas):
    """Confronte les agendas aux praticiens planifiés. N'écrit rien."""
    agendas = tuple(agendas)
    planifies = list(
        Personne.objects.filter(
            role_metier=Personne.RoleMetier.PRATICIEN, planifiee=True, actif=True
        )
    )

    rapport = RapportAppariement(agendas=agendas)
    compteurs = {EXACT: 0, APPROCHE: 0, PLANNING_FIXE: 0, AUCUN: 0}
    retenus = set()

    for personne in planifies:
        cible = normaliser(f"{personne.nom} {personne.prenom}")
        libres = [agenda for agenda in agendas if agenda not in retenus]

        exacts = [agenda for agenda in libres if normaliser(agenda) == cible]
        if exacts:
            agenda, mode = exacts[0], EXACT
        else:
            candidats = _candidats_approches(personne, libres)
            if len(candidats) == 1:
                agenda, mode = candidats[0], APPROCHE
            elif personne.jours_fixes:
                # Le skill acceptait déjà ce cas : ses jours fixes suffisent à
                # le planifier, aucun agenda n'est requis.
                agenda, mode = None, PLANNING_FIXE
            else:
                agenda, mode = None, AUCUN

        if agenda is not None:
            retenus.add(agenda)
        compteurs[mode] += 1
        rapport.propositions.append(
            Proposition(
                personne=personne,
                agenda=agenda,
                mode=mode,
                agenda_actuel=personne.agenda_doctolib or "",
            )
        )

    non_planifies = list(
        Personne.objects.filter(role_metier=Personne.RoleMetier.PRATICIEN).exclude(
            pk__in=[personne.pk for personne in planifies]
        )
    )
    for agenda in agendas:
        if agenda not in retenus:
            rapport.orphelins.append(
                Orphelin(agenda=agenda, personne=_reconnaitre(agenda, non_planifies))
            )

    compteurs["orphelins"] = len(rapport.orphelins)
    rapport.compteurs = compteurs
    return rapport


def appliquer(rapport, qui):
    """Écrit les agendas proposés (exact et approché). Renvoie les comptages."""
    ecrits = {EXACT: 0, APPROCHE: 0}
    for proposition in rapport.propositions:
        if proposition.mode in ecrits and proposition.agenda:
            proposition.personne.agenda_doctolib = proposition.agenda
            proposition.personne.save(update_fields=["agenda_doctolib"])
            ecrits[proposition.mode] += 1

    comptages = dict(rapport.compteurs)
    journaliser(Action.APPARIEMENT_APPLIQUE, qui=qui, objet=None, **comptages)
    logger.info(
        "appariement applique : %s exacts, %s approches, %s orphelins",
        ecrits[EXACT],
        ecrits[APPROCHE],
        len(rapport.orphelins),
    )
    return ecrits
