"""Recette de l'import de la fiche dans `Personne`.

Noms fictifs, absents de `regles/regles.json` sauf mention contraire : la
couleur ne doit venir des règles que lorsque le nom y figure vraiment.
"""

import pytest
from django.db import IntegrityError, transaction

from audit.models import EvenementAudit
from comptes.models import Personne
from personnes.lecture_fiche import lire
from personnes.services import importer_fiche

from .fabrique_fiche import fiche, ligne_fiche

pytestmark = pytest.mark.django_db


def importer(lignes, qui=None):
    return importer_fiche(lire(fiche(lignes)), qui)


# --- Création ----------------------------------------------------------------


def test_creation_pose_tous_les_champs():
    rapport = importer(
        [ligne_fiche("DUPONT Alice", heures=39, jours=["Mardi", "Jeudi"])]
    )

    assert (rapport.lues, rapport.creees) == (1, 1)
    personne = Personne.objects.get(nom="DUPONT", prenom="Alice")
    assert personne.role_metier == Personne.RoleMetier.ASSISTANTE
    assert personne.planifiee is True
    assert personne.heures_hebdo == 39
    assert personne.jours_fixes == ["Mardi", "Jeudi"]
    assert personne.code == "alice_dup"


def test_couleur_vide_si_le_nom_est_absent_des_regles():
    importer([ligne_fiche("DUPONT Alice")])

    assert Personne.objects.get(nom="DUPONT").couleur == ""


def test_import_rejouable_sans_effet():
    lignes = [ligne_fiche("DUPONT Alice", jours=["Mardi"])]
    importer(lignes)

    rapport = importer(lignes)

    assert (rapport.creees, rapport.mises_a_jour, rapport.inchangees) == (0, 0, 1)
    assert Personne.objects.count() == 1


# --- Mise à jour -------------------------------------------------------------


def test_mise_a_jour_des_quatre_champs_de_la_fiche():
    importer([ligne_fiche("DUPONT Alice", heures=39, jours=["Mardi"])])
    personne = Personne.objects.get(nom="DUPONT")
    personne.email_contact = "alice@example.org"
    personne.agenda_doctolib = "DUPONT Alice (Villecresnes)"
    personne.couleur = "yellow"
    personne.actif = False
    personne.save()

    rapport = importer(
        [
            ligne_fiche(
                "DUPONT Alice",
                department="Secretariat",
                planning="__NO__",
                heures=27,
                jours=["Lundi", "Mercredi"],
            )
        ]
    )

    assert rapport.mises_a_jour == 1
    personne.refresh_from_db()
    assert personne.role_metier == Personne.RoleMetier.SECRETAIRE
    assert personne.planifiee is False
    assert personne.heures_hebdo == 27
    assert personne.jours_fixes == ["Lundi", "Mercredi"]
    # Ce qui n'appartient pas à la fiche n'a pas bougé.
    assert personne.email_contact == "alice@example.org"
    assert personne.agenda_doctolib == "DUPONT Alice (Villecresnes)"
    assert personne.couleur == "yellow"
    assert personne.actif is False
    assert personne.code == "alice_dup"


def test_rapprochement_insensible_a_la_casse_du_nom():
    """Une personne saisie à la main dans l'admin est retrouvée par la fiche."""
    Personne.objects.create(
        nom="Dupont", prenom="alice", role_metier=Personne.RoleMetier.ASSISTANTE
    )

    rapport = importer([ligne_fiche("DUPONT Alice", heures=35)])

    assert rapport.creees == 0
    assert Personne.objects.count() == 1


# --- Code et collisions ------------------------------------------------------


def test_collision_de_code_laisse_la_seconde_sans_code():
    rapport = importer(
        [ligne_fiche("MARTIN Jean"), ligne_fiche("MARTINEZ Jean")]
    )

    assert Personne.objects.get(nom="MARTIN").code == "jean_mar"
    assert Personne.objects.get(nom="MARTINEZ").code is None
    assert any("code en collision" in a for a in rapport.avertissements)


def test_deux_personnes_sans_code_cohabitent():
    """`code` est unique : deux codes vides doivent être NULL, pas « »."""
    importer(
        [
            ligne_fiche("MARTIN Jean"),
            ligne_fiche("MARTINEZ Jean"),
            ligne_fiche("MARIN Jean"),
        ]
    )

    assert Personne.objects.filter(code__isnull=True).count() == 2


# --- Avertissements ----------------------------------------------------------


def test_heures_hors_gabarits_averties():
    rapport = importer([ligne_fiche("DUPONT Alice", heures=30)])

    assert any("heures 30 hors gabarits" in a for a in rapport.avertissements)


def test_heures_dans_les_gabarits_sans_avertissement():
    rapport = importer([ligne_fiche("DUPONT Alice", heures=35)])

    assert rapport.avertissements == []


def test_secretaire_sans_heures_avec_jours_fixes_non_avertie():
    rapport = importer(
        [
            ligne_fiche(
                "DUPONT Alice",
                department="Secretariat",
                heures=None,
                jours=["Mardi", "Mercredi", "Jeudi"],
            )
        ]
    )

    assert rapport.avertissements == []


def test_sans_heures_ni_jours_avertie():
    rapport = importer([ligne_fiche("DUPONT Alice", heures=None)])

    assert any("ni heures hebdomadaires ni jours fixes" in a for a in rapport.avertissements)


def test_praticien_sans_heures_non_averti():
    """Un praticien n'a pas de contrat horaire : rien à signaler."""
    rapport = importer(
        [ligne_fiche("LEROY Chloe", department="Praticien", heures=None)]
    )

    assert rapport.avertissements == []


def test_non_planifiee_sans_heures_non_avertie():
    rapport = importer([ligne_fiche("DUPONT Alice", planning="__NO__", heures=None)])

    assert rapport.avertissements == []


def test_personne_en_base_absente_du_fichier_avertie():
    importer([ligne_fiche("DUPONT Alice"), ligne_fiche("MARTIN Bob")])

    rapport = importer([ligne_fiche("DUPONT Alice")])

    assert any(
        "MARTIN Bob : présente en base, absente du fichier" in a
        for a in rapport.avertissements
    )


# --- Journal d'audit ---------------------------------------------------------


def test_audit_sans_aucun_nom(cabinet):
    importer([ligne_fiche("DUPONT Alice"), ligne_fiche("New team member")], cabinet)

    evenement = EvenementAudit.objects.get(action="personnes_importees")
    assert evenement.qui_id == cabinet.pk
    assert evenement.details == {
        "lues": 1,
        "creees": 1,
        "mises_a_jour": 0,
        "inchangees": 0,
        "ignorees": 1,
        "avertissements": 0,
    }
    assert "DUPONT" not in str(evenement.details)
    assert "Alice" not in str(evenement.details)


def test_lignes_ignorees_reportees_dans_le_rapport():
    rapport = importer([ligne_fiche("New team member")])

    assert rapport.lues == 0
    assert len(rapport.ignorees) == 1


# --- Contraintes du modèle ---------------------------------------------------


def test_doublon_nom_prenom_refuse():
    Personne.objects.create(
        nom="DUPONT", prenom="Alice", role_metier=Personne.RoleMetier.ASSISTANTE
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Personne.objects.create(
                nom="DUPONT", prenom="Alice", role_metier=Personne.RoleMetier.PRATICIEN
            )


def test_save_pose_le_code():
    personne = Personne.objects.create(
        nom="DA SILVA COSTA",
        prenom="Ana",
        role_metier=Personne.RoleMetier.ASSISTANTE,
    )

    assert personne.code == "ana_das"


def test_code_saisi_a_la_main_conserve():
    personne = Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.ASSISTANTE,
        code="choisi_a_la_main",
    )

    assert personne.code == "choisi_a_la_main"
