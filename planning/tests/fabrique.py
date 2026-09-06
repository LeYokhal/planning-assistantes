"""Fabrique du jeu FICTIF de la brique 4a : le même que `planning/tests_js/fixtures/data_fictif.json`.

Trois praticiens, sept salariées, deux fenêtres d'import couvrant octobre 2026,
quatre absences et trois jours d'école. Noms des fabriques de test uniquement,
aucune donnée réelle. Les règles sont construites sans toucher au fichier du
dépôt, comme `absences/tests/fabrique.py`.
"""

import datetime

from absences.models import AbsenceSalariee, TypeAbsence
from absences.tests import fabrique as fabrique_absences
from comptes.models import Personne
from presences import services as services_presences
from presences.fenetres import plage_mois
from presences.lecture import VERDICT_NON_PLANIFIE, VERDICT_OUVERT
from presences.tests.fabrique import en_direct, fabriquer_payload
from regles import chargeur

MOIS = "2026-10"
PLAGE = plage_mois(MOIS)

AGENDAS = ("DUPONT Alice", "MARTIN Bob", "LEROY Chloe")

# Présence par agenda : jour de semaine (0 = lundi) -> heure de fin.
PRESENCE = {
    "DUPONT Alice": {1: "18:30", 2: "18:30", 3: "16:30", 4: "18:30"},
    "MARTIN Bob": {1: "19:00", 3: "19:00", 4: "19:00"},
    "LEROY Chloe": {1: "18:30", 2: "18:30", 3: "18:30", 4: "18:30", 5: "18:30"},
}
# Samedi 31 octobre : aucune ligne pour Chloe (ligne triviale).
SANS_LIGNE = {("LEROY Chloe", datetime.date(2026, 10, 31))}

PALETTE = {
    "gray": ["#E6E9EC", "#4F5B63"], "brown": ["#EAD9CB", "#6E4A2E"],
    "orange": ["#FBE1C2", "#9E5410"], "yellow": ["#F6ECAE", "#7A5F00"],
    "green": ["#D2EBD5", "#256B31"], "blue": ["#D3E4F7", "#1F529A"],
    "purple": ["#E2D8F5", "#5E3BA6"], "pink": ["#F8D6E4", "#A32F60"],
    "red": ["#F6D0CD", "#A8342E"], "default": ["#E3E3E3", "#3A3A3A"],
}

REGLES_BRUTES = {
    "gabarits": {"39": ["J", "J", "J", "J"], "35": ["J", "J", "J", "C"], "27": ["J", "J", "C"]},
    "binomes": [
        {"assistante": "BERNARD Emma", "praticien": "DUPONT Alice"},
        {"assistante": "ROUX Lina", "praticien": "MARTIN Bob"},
        {"assistante": "GIRARD Zoe", "praticien": "LEROY Chloe", "exclusif": True},
        {"assistante": "LAMBERT Ines", "praticien": "LEROY Chloe", "exclusif": True},
    ],
    "praticiens_exclusifs": {"liste": ["LEROY Chloe"]},
    "creneau_administratif": [{"salariee": "FONTAINE Nora", "brique": "C"}],
    "couleurs": {},
    "praticiens_a_part": {"liste": [{"nom": "LEROY Chloe", "etiquette": "ortho"}]},
    "heures_par_brique": {"J": 9.75, "C": 6.75},
    "etudiantes": {
        "liste": [
            {"nom": "MOREL Lea", "gabarit_sans_cours": ["J", "J", "J", "C"], "mot_cle_notion": "école"}
        ]
    },
    "palette": PALETTE,
    "periodes_ouverture": {
        "liste": [
            {"a_partir_du": None, "jours": ["Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]},
            {"a_partir_du": "2026-10-05", "jours": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]},
        ]
    },
}


def regles(brut=None):
    """Règles fictives, sans toucher au fichier du dépôt."""
    return chargeur._construire(brut or REGLES_BRUTES)


def praticien(nom, prenom, couleur="", agenda="", jours_fixes=None, planifiee=True, actif=True):
    return Personne.objects.create(
        nom=nom, prenom=prenom, role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=planifiee, actif=actif, couleur=couleur, agenda_doctolib=agenda,
        jours_fixes=jours_fixes or [],
    )


def salariee(nom, prenom, heures=39, couleur="", role=Personne.RoleMetier.ASSISTANTE,
             jours_fixes=None, planifiee=True, actif=True):
    return Personne.objects.create(
        nom=nom, prenom=prenom, role_metier=role, planifiee=planifiee, actif=actif,
        heures_hebdo=heures, couleur=couleur, jours_fixes=jours_fixes or [],
    )


def personnes():
    """Les dix personnes du jeu fictif, indexées par prénom."""
    return {
        "Alice": praticien("DUPONT", "Alice", "yellow", "DUPONT Alice"),
        "Bob": praticien("MARTIN", "Bob", "green", "MARTIN Bob"),
        "Chloe": praticien("LEROY", "Chloe", "gray", "LEROY Chloe"),
        "Emma": salariee("BERNARD", "Emma", 39, "brown"),
        "Lina": salariee("ROUX", "Lina", 39, "orange"),
        "Nora": salariee("FONTAINE", "Nora", 35, "blue"),
        "Zoe": salariee("GIRARD", "Zoe", 39, "purple"),
        "Ines": salariee("LAMBERT", "Ines", 39, "pink"),
        "Lea": salariee("MOREL", "Lea", 27, "red"),
        "Sara": salariee(
            "PETIT", "Sara", None, "", Personne.RoleMetier.SECRETAIRE,
            jours_fixes=["Mardi", "Mercredi", "Jeudi"],
        ),
    }


def regle_presences(jour, indice):
    """Règle de présence du jeu fictif, pour `fabriquer_payload`."""
    agenda = AGENDAS[indice]
    fin = PRESENCE[agenda].get(jour.weekday())
    if fin is None or (agenda, jour) in SANS_LIGNE:
        return {"verdict": VERDICT_NON_PLANIFIE, "presence": False}
    return {
        "verdict": VERDICT_OUVERT, "presence": True,
        "creneaux": (("09:00", "13:00"), ("14:00", fin)),
        "nb_rdv": 12, "duree_rdv": 480,
    }


def importer(cabinet, debut, fin, praticiens=AGENDAS, regle=regle_presences):
    """Un import réussi par le service, sans passer par la page."""
    return services_presences.importer_fichier(
        en_direct(fabriquer_payload(debut, fin, praticiens, regle)), cabinet
    )


def importer_le_mois(cabinet):
    """Les deux fenêtres de la plage d'octobre 2026."""
    return [importer(cabinet, debut, fin) for debut, fin in PLAGE.fenetres]


def type_absence(libelle):
    return TypeAbsence.objects.get(libelle=libelle)


def absences(personnes_):
    """Emma en congé payé validé du 13 au 15, Lina en retard le 22, Lea à l'école trois mardis."""
    cp = fabrique_absences.absence(
        personnes_["Emma"], type_absence("Congé payé"),
        datetime.date(2026, 10, 13), datetime.date(2026, 10, 15),
        statut=AbsenceSalariee.Statut.VALIDEE,
    )
    retard = fabrique_absences.absence(
        personnes_["Lina"], type_absence("Retard"),
        datetime.date(2026, 10, 22), datetime.date(2026, 10, 22),
        statut=AbsenceSalariee.Statut.DECLAREE,
    )
    ecoles = [
        fabrique_absences.absence(
            personnes_["Lea"], type_absence("Ecole"), jour, jour,
            statut=AbsenceSalariee.Statut.DECLAREE,
        )
        for jour in (datetime.date(2026, 10, 6), datetime.date(2026, 10, 20), datetime.date(2026, 10, 27))
    ]
    return {"cp": cp, "retard": retard, "ecoles": ecoles}


def jeu_complet(cabinet):
    """Personnes, imports du mois et absences : le jeu fictif entier."""
    personnes_ = personnes()
    imports = importer_le_mois(cabinet)
    return {"personnes": personnes_, "imports": imports, "absences": absences(personnes_)}


def brique(s, t="J", x=False, a=False):
    return {"s": s, "t": t, "x": x, "a": a}


def etat(affectations=None, feries=None, feries_off=None, notes=None):
    return {
        "affectations": affectations or {},
        "feries": feries or {},
        "feries_off": feries_off or [],
        "notes": notes or {},
    }


def etat_propre():
    """Un état valide : Emma chez Alice et Sara au secrétariat, le mardi 29 septembre."""
    return etat({"2026-09-29": {"alice_dup": [brique("emma_ber")], "secretariat": [brique("sara_pet")]}})
