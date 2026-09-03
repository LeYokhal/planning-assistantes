"""Fabrique de données FICTIVES pour les tests des absences.

Aucune absence réelle, aucun nom réel, aucune adresse réelle : noms inventés
(« DUPONT Alice », « MARTIN Bob »…) et domaine `example.org` uniquement, comme
`presences/tests/fabrique.py`.

Les règles fabriquées ici portent les deux périodes d'ouverture du cabinet, pour
que les tests du calcul puissent éprouver la bascule du 5 octobre 2026 sans
dépendre du fichier réel du dépôt.
"""

import datetime

from comptes.models import Personne
from regles import chargeur

from absences.models import AbsenceSalariee, TypeAbsence

# Bascule des jours d'ouverture, calée sur un lundi (§ 4.1 du plan).
BASCULE = datetime.date(2026, 10, 5)

REGLES_BRUTES = {
    "gabarits": {"39": ["J", "J", "J", "J"], "35": ["J", "J", "J", "C"], "27": ["J", "J", "C"]},
    "binomes": [],
    "praticiens_exclusifs": {"liste": []},
    "creneau_administratif": [],
    "couleurs": {},
    "praticiens_a_part": {"liste": []},
    "heures_par_brique": {"J": 9.75, "C": 6.75},
    "etudiantes": {"liste": []},
    "periodes_ouverture": {
        "liste": [
            {
                "a_partir_du": None,
                "jours": ["Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
            },
            {
                "a_partir_du": BASCULE.isoformat(),
                "jours": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"],
            },
        ]
    },
}


def regles():
    """Règles fictives, construites sans toucher au fichier du dépôt."""
    return chargeur._construire(REGLES_BRUTES)


def personne(
    nom="DUPONT",
    prenom="Alice",
    role_metier=Personne.RoleMetier.ASSISTANTE,
    heures_hebdo=39,
    jours_fixes=None,
    **extra,
):
    """Une salariée fictive."""
    return Personne.objects.create(
        nom=nom,
        prenom=prenom,
        role_metier=role_metier,
        heures_hebdo=heures_hebdo,
        jours_fixes=jours_fixes or [],
        planifiee=True,
        **extra,
    )


def praticien(nom="LEROY", prenom="Chloe"):
    """Un praticien fictif : aucune absence ne doit pouvoir porter sur lui."""
    return Personne.objects.create(
        nom=nom,
        prenom=prenom,
        role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=True,
    )


def type_absence(
    libelle="Congé payé",
    categorie=TypeAbsence.Categorie.DEMANDE,
    bloquant=True,
    paie=True,
    **extra,
):
    """Un type d'absence, créé ou repris.

    `update_or_create` et non `create` : la migration `0002_types_initiaux` a
    déjà posé les treize types dans la base de test, et `libelle` est unique.
    Le test garde la main sur la catégorie et le drapeau de paie.
    """
    type_, _ = TypeAbsence.objects.update_or_create(
        libelle=libelle,
        defaults={
            "categorie": categorie,
            "bloquant": bloquant,
            "paie": paie,
            **extra,
        },
    )
    return type_


def absence(
    personne_,
    type_,
    debut=datetime.date(2026, 5, 26),
    fin=datetime.date(2026, 5, 30),
    statut=AbsenceSalariee.Statut.EN_ATTENTE,
    **extra,
):
    """Une absence fictive, posée directement en base."""
    return AbsenceSalariee.objects.create(
        personne=personne_,
        type=type_,
        date_debut=debut,
        date_fin=fin,
        statut=statut,
        **extra,
    )


def lier(compte, personne_):
    """Rattache un compte à une personne, comme le fait l'action d'admin."""
    compte.personne = personne_
    compte.save(update_fields=["personne"])
    return compte
