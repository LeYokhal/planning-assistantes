"""Import de la fiche personnel dans `Personne`.

L'import est REJOUABLE : le même fichier passé deux fois ne crée rien la
seconde fois et ne modifie rien. Seules les quatre colonnes qui viennent de la
fiche sont écrites sur une personne existante — `email_contact`,
`agenda_doctolib`, `couleur`, `code` et `actif` appartiennent à
l'application et ne sont jamais écrasés par un import.

Le journal d'audit ne reçoit que des comptages : jamais un nom, jamais une
adresse. Les avertissements nominatifs vont à l'écran, pour le cabinet.
"""

import logging
from dataclasses import dataclass, field

from django.db import transaction

from audit.models import Action
from audit.services import journaliser
from comptes.models import Personne
from presences.services import agendas_recents
from regles.chargeur import charger, couleur_de

logger = logging.getLogger(__name__)

# Colonnes écrites par un import sur une personne déjà connue.
CHAMPS_FICHE = ("role_metier", "planifiee", "heures_hebdo", "jours_fixes")

SALARIEES = (Personne.RoleMetier.ASSISTANTE, Personne.RoleMetier.SECRETAIRE)


@dataclass
class RapportImport:
    """Ce que l'import a fait, et ce sur quoi le cabinet doit se pencher."""

    lues: int = 0
    creees: int = 0
    mises_a_jour: int = 0
    inchangees: int = 0
    ignorees: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)


def _avertir_heures(rapport, personne, gabarits):
    """Signale un contrat que les gabarits ne savent pas poser.

    Une secrétaire planifiée sans heures mais avec des jours fixes est le cas
    normal : ses jours fixes FONT son contrat (règle du skill v1). Tout autre
    trou est signalé.
    """
    if not personne.planifiee or personne.role_metier not in SALARIEES:
        return

    libelle = f"{personne.nom} {personne.prenom}"
    if personne.heures_hebdo:
        if personne.heures_hebdo not in gabarits:
            rapport.avertissements.append(
                f"{libelle} : heures {personne.heures_hebdo} hors gabarits "
                f"({', '.join(str(h) for h in sorted(gabarits))})"
            )
        return

    if personne.role_metier == Personne.RoleMetier.SECRETAIRE and personne.jours_fixes:
        return

    rapport.avertissements.append(
        f"{libelle} : ni heures hebdomadaires ni jours fixes"
    )


def importer_fiche(lecture, qui):
    """Applique une `LectureFiche` sur la base. Renvoie le rapport."""
    rapport = RapportImport(lues=len(lecture.lignes), ignorees=list(lecture.ignorees))
    gabarits = charger().gabarits
    vues = set()

    with transaction.atomic():
        for ligne in lecture.lignes:
            vues.add((ligne.nom.casefold(), ligne.prenom.casefold()))

            personne = Personne.objects.filter(
                nom__iexact=ligne.nom, prenom__iexact=ligne.prenom
            ).first()

            if personne is None:
                personne = Personne(
                    nom=ligne.nom,
                    prenom=ligne.prenom,
                    role_metier=ligne.role_metier,
                    planifiee=ligne.planifiee,
                    heures_hebdo=ligne.heures,
                    jours_fixes=list(ligne.jours),
                    couleur=couleur_de(f"{ligne.nom} {ligne.prenom}"),
                )
                personne.save()
                rapport.creees += 1
                if not personne.code:
                    rapport.avertissements.append(
                        f"{personne.nom} {personne.prenom} : code en collision, "
                        "à saisir dans l'admin"
                    )
            else:
                nouveau = {
                    "role_metier": ligne.role_metier,
                    "planifiee": ligne.planifiee,
                    "heures_hebdo": ligne.heures,
                    "jours_fixes": list(ligne.jours),
                }
                modifies = [
                    champ
                    for champ, valeur in nouveau.items()
                    if getattr(personne, champ) != valeur
                ]
                if modifies:
                    for champ, valeur in nouveau.items():
                        setattr(personne, champ, valeur)
                    # `update_fields` protège les colonnes qui n'appartiennent
                    # pas à la fiche : adresse de contact, agenda, couleur, code.
                    personne.save(update_fields=list(CHAMPS_FICHE))
                    rapport.mises_a_jour += 1
                else:
                    rapport.inchangees += 1

            _avertir_heures(rapport, personne, gabarits)

        for personne in Personne.objects.all():
            if (personne.nom.casefold(), personne.prenom.casefold()) not in vues:
                rapport.avertissements.append(
                    f"{personne.nom} {personne.prenom} : présente en base, "
                    "absente du fichier"
                )

    journaliser(
        Action.PERSONNES_IMPORTEES,
        qui=qui,
        lues=rapport.lues,
        creees=rapport.creees,
        mises_a_jour=rapport.mises_a_jour,
        inchangees=rapport.inchangees,
        ignorees=len(rapport.ignorees),
        avertissements=len(rapport.avertissements),
    )
    logger.info(
        "import fiche : %s lues, %s creees, %s mises a jour, %s inchangees, "
        "%s ignorees, %s avertissements",
        rapport.lues,
        rapport.creees,
        rapport.mises_a_jour,
        rapport.inchangees,
        len(rapport.ignorees),
        len(rapport.avertissements),
    )
    return rapport


def agendas_pour_appariement():
    """Agendas Doctolib du dernier lot d'import réussi."""
    return agendas_recents()
