"""Recette de l'appariement agenda Doctolib ↔ praticien.

Noms d'agendas fictifs, dans les formes que Doctolib produit réellement :
suffixe de cabinet, titre, casse et espaces variables.
"""

import pytest

from audit.models import EvenementAudit
from comptes.models import Personne
from personnes.appariement import APPROCHE, AUCUN, EXACT, PLANNING_FIXE, appliquer, apparier

pytestmark = pytest.mark.django_db


def praticien(nom, prenom, planifiee=True, **extra):
    return Personne.objects.create(
        nom=nom,
        prenom=prenom,
        role_metier=Personne.RoleMetier.PRATICIEN,
        planifiee=planifiee,
        **extra,
    )


def par_personne(rapport):
    return {
        proposition.personne.nom: proposition for proposition in rapport.propositions
    }


# --- Appariement exact -------------------------------------------------------


@pytest.mark.parametrize(
    "agenda",
    [
        "DUPONT Alice",
        "DUPONT ALICE",
        "dupont alice",
        "DUPONT Alice (Villecresnes)",
        "DUPONT Alice ",
        "Dr DUPONT Alice",
    ],
)
def test_exact_malgre_casse_accents_suffixe_et_titre(agenda):
    praticien("DUPONT", "Alice")

    proposition = apparier([agenda]).propositions[0]

    assert (proposition.mode, proposition.agenda) == (EXACT, agenda)


def test_exact_avec_nom_accentue():
    praticien("LEVEQUE", "Chloé")

    proposition = apparier(["LÉVÊQUE Chloé"]).propositions[0]

    assert proposition.mode == EXACT


# --- Appariement approché ----------------------------------------------------


def test_approche_sur_prenom_et_debut_de_nom():
    praticien("MARTINEZ", "Bob")

    proposition = apparier(["MARTIN Bob"]).propositions[0]

    assert (proposition.mode, proposition.agenda) == (APPROCHE, "MARTIN Bob")


def test_deux_candidats_approches_ne_tranchent_pas():
    praticien("MARTINEZ", "Bob")

    proposition = apparier(["MARTIN Bob", "MARTINON Bob"]).propositions[0]

    assert (proposition.mode, proposition.agenda) == (AUCUN, None)


# --- Absence d'agenda --------------------------------------------------------


def test_planning_fixe_si_jours_fixes():
    praticien("LEROY", "Chloe", jours_fixes=["Mardi", "Jeudi"])

    proposition = apparier(["DUPONT Alice"]).propositions[0]

    assert (proposition.mode, proposition.agenda) == (PLANNING_FIXE, None)


def test_aucun_si_ni_agenda_ni_jours_fixes():
    praticien("LEROY", "Chloe")

    proposition = apparier(["DUPONT Alice"]).propositions[0]

    assert (proposition.mode, proposition.agenda) == (AUCUN, None)


def test_praticien_non_planifie_hors_propositions():
    praticien("DUPONT", "Alice", planifiee=False)

    assert apparier(["DUPONT Alice"]).propositions == []


def test_assistante_hors_propositions():
    Personne.objects.create(
        nom="DUPONT",
        prenom="Alice",
        role_metier=Personne.RoleMetier.ASSISTANTE,
        planifiee=True,
    )

    assert apparier(["DUPONT Alice"]).propositions == []


def test_praticien_inactif_hors_propositions():
    praticien("DUPONT", "Alice", actif=False)

    assert apparier(["DUPONT Alice"]).propositions == []


# --- Un agenda ne sert qu'une fois -------------------------------------------


def test_agenda_deja_propose_non_repropose():
    praticien("DUPONT", "Alice")
    praticien("DUPONTEL", "Alice")

    rapport = apparier(["DUPONT Alice"])

    propositions = par_personne(rapport)
    assert propositions["DUPONT"].mode == EXACT
    assert propositions["DUPONTEL"].agenda is None


# --- Orphelins ---------------------------------------------------------------


def test_orphelin_reconnu_parmi_les_non_planifies():
    praticien("MARTIN", "Bob", planifiee=False)

    rapport = apparier(["MARTIN Bob"])

    assert len(rapport.orphelins) == 1
    assert rapport.orphelins[0].personne.nom == "MARTIN"


def test_orphelin_inconnu():
    rapport = apparier(["INCONNU Zoe"])

    assert rapport.orphelins[0].personne is None


def test_agenda_apparie_nest_pas_orphelin():
    praticien("DUPONT", "Alice")

    assert apparier(["DUPONT Alice"]).orphelins == []


def test_compteurs():
    praticien("DUPONT", "Alice")
    praticien("MARTINEZ", "Bob")
    praticien("LEROY", "Chloe", jours_fixes=["Mardi"])

    rapport = apparier(["DUPONT Alice", "MARTIN Bob", "INCONNU Zoe"])

    assert rapport.compteurs == {
        EXACT: 1,
        APPROCHE: 1,
        PLANNING_FIXE: 1,
        AUCUN: 0,
        "orphelins": 1,
    }


# --- Application -------------------------------------------------------------


def test_appliquer_ecrit_exact_et_approche(cabinet):
    alice = praticien("DUPONT", "Alice")
    bob = praticien("MARTINEZ", "Bob")
    chloe = praticien("LEROY", "Chloe", jours_fixes=["Mardi"])

    rapport = apparier(["DUPONT Alice (Villecresnes)", "MARTIN Bob"])
    ecrits = appliquer(rapport, cabinet)

    assert ecrits == {EXACT: 1, APPROCHE: 1}
    alice.refresh_from_db()
    bob.refresh_from_db()
    chloe.refresh_from_db()
    assert alice.agenda_doctolib == "DUPONT Alice (Villecresnes)"
    assert bob.agenda_doctolib == "MARTIN Bob"
    assert chloe.agenda_doctolib == ""


def test_appliquer_journalise_les_comptages(cabinet):
    praticien("DUPONT", "Alice")

    appliquer(apparier(["DUPONT Alice", "INCONNU Zoe"]), cabinet)

    evenement = EvenementAudit.objects.get(action="appariement_applique")
    assert evenement.qui_id == cabinet.pk
    assert evenement.details == {
        "exact": 1,
        "approche": 0,
        "planning_fixe": 0,
        "aucun": 0,
        "orphelins": 1,
    }


def test_appliquer_ne_touche_pas_les_autres_champs(cabinet):
    alice = praticien("DUPONT", "Alice", heures_hebdo=39)
    alice.email_contact = "alice@example.org"
    alice.save()

    appliquer(apparier(["DUPONT Alice"]), cabinet)

    alice.refresh_from_db()
    assert alice.email_contact == "alice@example.org"
    assert alice.heures_hebdo == 39


def test_agenda_actuel_expose_quand_il_change():
    praticien("DUPONT", "Alice", agenda_doctolib="ANCIEN LIBELLE")

    proposition = apparier(["DUPONT Alice"]).propositions[0]

    assert proposition.agenda_actuel == "ANCIEN LIBELLE"
    assert proposition.change is True


def test_agenda_actuel_identique_ne_change_pas():
    praticien("DUPONT", "Alice", agenda_doctolib="DUPONT Alice")

    proposition = apparier(["DUPONT Alice"]).propositions[0]

    assert proposition.change is False
