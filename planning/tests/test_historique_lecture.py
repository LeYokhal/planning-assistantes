"""Recette de la lecture d'un mois historique (brique 7b, C7.1).

Décisions couvertes : D3 (page dédiée, sans `DATA`, sans `STATE`, sans moteur ;
`sans_import.html` y renvoie), D6 (`copie` → 404 sur un mois historique), D9
(ordre des colonnes), et la règle des journées arrêtée le 08/09 — une journée
fait une ligne si le cabinet **ouvre** ce jour-là (`regles.chargeur.jours_ouverture`,
la règle datée du calcul de paie) **ou** si elle porte au moins une brique.

Aucune donnée réelle : fiches et fichier de `planning/tests/fabrique.py`.

Deux façons de poser une version historique, toutes deux utiles :

* `_importe(...)` passe par `historique.analyser` / `executer`, le chemin réel ;
* `_pose(...)` écrit la ligne directement, pour les états que l'import
  refuserait mais que la base peut porter — une colonne dont la fiche a été
  supprimée après l'import, par exemple (patron de `test_mes_jours`).
"""

import datetime

import pytest

from absences.models import AbsenceSalariee
from absences.tests import fabrique as fabrique_absences
from planning import historique, services
from planning.models import PlanningVersion
from planning.tests import fabrique

pytestmark = pytest.mark.django_db

MOIS = fabrique.MOIS_HISTORIQUE                     # 2026-03, plage 23/02 → 05/04
URL = f"/planning/{MOIS}/historique/"
PAGE = f"/planning/{MOIS}/"
COPIE = f"/planning/{MOIS}/copie/"
# Régime d'ouverture applicable avant le 05/10/2026 : mardi → samedi.
MARDI = "2026-03-03"
MERCREDI = "2026-03-04"
JEUDI_SANS_BRIQUE = "2026-03-05"
DIMANCHE_VIDE = "2026-03-01"
DIMANCHE_PORTEUR = "2026-03-08"
LUNDI_VIDE = "2026-02-23"
TYPES = ("Maladie", "Congé payé", "Retard", "Ecole")
BLOCS = ("planning-data", "planning-state", "planning-meta")


@pytest.fixture
def fiches(db):
    """Les trois fiches fictives de la 7a, dont la fiche praticien close."""
    return fabrique.personnes_historiques()


def _fichier(mois=MOIS, affectations=None, feries=None, feries_off=None, notes=None):
    planning = fabrique.planning_exporte(
        mois=mois,
        affectations=(
            affectations
            if affectations is not None
            else fabrique.affectations_historiques()
        ),
        feries=feries,
        notes=notes,
    )
    planning["feries_off"] = feries_off or []
    return planning


def _importe(cabinet, **kwargs):
    """Le chemin réel : analyse puis écriture d'une version historique."""
    return historique.executer(historique.analyser(_fichier(**kwargs)), cabinet)


def _pose(affectations, mois=MOIS, numero=1, **extra):
    """Une version historique écrite directement, sans passer par l'import."""
    return PlanningVersion.objects.create(
        mois=mois,
        numero=numero,
        state=fabrique.etat(affectations, **extra),
        publiee=True,
        verifications={"historique": True, "importe_le": "", "empreinte": "",
                       "imports": [], "nb_briques": 0, "nb_jours": 0},
    )


def _jours(reponse):
    return [ligne["date"].isoformat() for ligne in reponse.context["lignes"]]


def _ligne(reponse, iso):
    return next(
        ligne
        for ligne in reponse.context["lignes"]
        if ligne["date"].isoformat() == iso
    )


# --- Accès --------------------------------------------------------------------


def test_acces_par_role(client, cabinet, principale, salariee, connecter, fiches):
    _importe(cabinet)

    assert client.get(URL).status_code == 302        # anonyme
    assert client.get(URL).url.startswith("/connexion/?next=")

    connecter(client, cabinet)
    assert client.get(URL).status_code == 200
    client.logout()

    connecter(client, principale)
    assert client.get(URL).status_code == 200
    client.logout()

    connecter(client, salariee)
    assert client.get(URL).status_code == 403


def test_mois_invalide_introuvable(client, cabinet, connecter):
    connecter(client, cabinet)
    assert client.get("/planning/2026-13/historique/").status_code == 404


def test_404_sans_version_publiee(client, cabinet, connecter, fiches):
    connecter(client, cabinet)
    assert client.get(URL).status_code == 404

    services.enregistrer(MOIS, 0, fabrique.etat(), cabinet)   # enregistrée, pas publiée
    assert client.get(URL).status_code == 404


def test_404_sur_une_version_publiee_ordinaire(client, cabinet, connecter):
    """Une version publiée par l'application se lit sur la page normale, pas ici."""
    fabrique.jeu_complet(cabinet)
    version = services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    services.publier(fabrique.MOIS, version.numero, cabinet)
    connecter(client, cabinet)

    assert client.get(f"/planning/{fabrique.MOIS}/historique/").status_code == 404


# --- Colonnes -----------------------------------------------------------------


def test_colonne_de_la_fiche_close(client, cabinet, connecter, fiches):
    """C7.4 : la colonne d'une fiche fermée est là, avec son libellé et sa mention."""
    _importe(cabinet)
    connecter(client, cabinet)

    reponse = client.get(URL)
    contenu = reponse.content.decode()
    colonne = next(c for c in reponse.context["colonnes"] if c["slot"] == "test_pra")

    assert "Test PRATICIEN" in contenu and "fiche close" in contenu
    assert colonne["libelle"] == "Test PRATICIEN" and colonne["fiche_close"] is True
    assert len(colonne["couleur"]) == 2


def test_ordre_des_colonnes(client, cabinet, connecter, fiches):
    """D9 : praticiens (à part en fin), puis MISC dans leur ordre, puis slot inconnu."""
    fabrique.praticien("LEROY", "Chloe", "gray", "LEROY Chloe")   # « à part » dans les règles
    _pose(
        {
            MARDI: {
                "test_pra": [fabrique.brique("test_ass")],
                "chloe_ler": [fabrique.brique("test_sec")],
                "secretariat": [fabrique.brique("test_ass")],
                "sureffectif": [fabrique.brique("test_sec")],
                "slot_disparu": [fabrique.brique("test_ass")],
            }
        }
    )
    connecter(client, cabinet)

    colonnes = client.get(URL).context["colonnes"]

    assert [c["slot"] for c in colonnes] == [
        "test_pra",       # praticien ordinaire
        "chloe_ler",      # praticien « à part » : en fin des praticiens
        "secretariat",    # MISC, dans l'ordre de LIBELLES_MISC
        "sureffectif",
        "slot_disparu",   # code que plus aucune fiche ne porte
    ]
    assert colonnes[-1]["libelle"] == "slot_disparu"


# --- Journées (décision du 08/09) ---------------------------------------------


def test_journees_retenues(client, cabinet, connecter, fiches):
    """Jour d'ouverture, ou jour porteur d'une brique — et rien d'autre."""
    affectations = dict(fabrique.affectations_historiques())
    affectations[DIMANCHE_PORTEUR] = {"secretariat": [fabrique.brique("test_sec")]}
    _importe(cabinet, affectations=affectations)
    connecter(client, cabinet)

    reponse = client.get(URL)
    jours = _jours(reponse)

    assert MARDI in jours and MERCREDI in jours
    assert JEUDI_SANS_BRIQUE in jours            # ouvert, sans brique : une ligne
    assert DIMANCHE_PORTEUR in jours             # fermé, mais porteur
    assert DIMANCHE_VIDE not in jours            # fermé et vide
    assert LUNDI_VIDE not in jours               # lundi avant le 05/10/2026 : fermé
    assert _ligne(reponse, DIMANCHE_PORTEUR)["hors_ouverture"] is True
    assert _ligne(reponse, MARDI)["hors_ouverture"] is False
    # Texte littéral du gabarit : l'autoescape ne s'y applique pas.
    assert "hors jours d'ouverture" in reponse.content.decode()


def test_ferie_du_calendrier_marque(client, cabinet, connecter, fiches):
    """Les fichiers repris ont `feries` vide : le férié vient du socle."""
    _importe(
        cabinet,
        mois=fabrique.MOIS_FERIE,
        affectations={"2026-01-01": {"secretariat": [fabrique.brique("test_sec")]}},
    )
    connecter(client, cabinet)

    reponse = client.get(f"/planning/{fabrique.MOIS_FERIE}/historique/")

    assert _ligne(reponse, "2026-01-01")["ferie"] == "Jour de l'an"
    assert "férié : Jour de l" in reponse.content.decode()


def test_ferie_rouvert_par_feries_off(client, cabinet, connecter, fiches):
    _importe(
        cabinet,
        mois=fabrique.MOIS_FERIE,
        affectations={"2026-01-01": {"secretariat": [fabrique.brique("test_sec")]}},
        feries_off=["2026-01-01"],
    )
    connecter(client, cabinet)

    reponse = client.get(f"/planning/{fabrique.MOIS_FERIE}/historique/")

    assert _ligne(reponse, "2026-01-01")["ferie"] is None
    assert "férié" not in reponse.content.decode()


def test_ferie_pose_dans_la_page(client, cabinet, connecter, fiches):
    """Un jour fermé à la main dans la page est repris tel quel."""
    _importe(cabinet, feries={JEUDI_SANS_BRIQUE: "Fermeture exceptionnelle"})
    connecter(client, cabinet)

    reponse = client.get(URL)

    assert _ligne(reponse, JEUDI_SANS_BRIQUE)["ferie"] == "Fermeture exceptionnelle"


# --- Cellules, notes, navigation ----------------------------------------------


def test_libelles_de_brique(client, cabinet, connecter, fiches):
    """`t` et `x` sont rendus mot pour mot comme dans « Mes jours »."""
    _pose(
        {
            MARDI: {"test_pra": [fabrique.brique("test_ass", "J")]},
            MERCREDI: {"test_pra": [fabrique.brique("test_ass", "C", x=True)]},
        }
    )
    connecter(client, cabinet)

    contenu = client.get(URL).content.decode()

    assert "Test ASSISTANTE" in contenu
    assert "journée courte (fin 16h30)" in contenu
    assert "(heures sup)" in contenu
    assert contenu.count("journée") == 2          # une simple, une courte


def test_code_inconnu_reste_brut(client, cabinet, connecter, fiches):
    _pose({MARDI: {"secretariat": [fabrique.brique("parti_dep")]}})
    connecter(client, cabinet)

    reponse = client.get(URL)

    assert _ligne(reponse, MARDI)["cellules"][0][0]["libelle"] == "parti_dep"


def test_notes_affichees(client, cabinet, connecter, fiches):
    _importe(cabinet, notes={MARDI: ["Réunion d'équipe"]})
    connecter(client, cabinet)

    contenu = client.get(URL).content.decode()

    assert "Notes" in contenu and "Réunion d&#x27;équipe" in contenu


def test_navigation_vers_la_page_du_mois(client, cabinet, connecter, fiches):
    """Précédent et suivant visent `/planning/<mois>/`, jamais `/historique/`."""
    _importe(cabinet)
    connecter(client, cabinet)

    contenu = client.get(URL).content.decode()

    assert 'href="/planning/2026-02/"' in contenu
    assert 'href="/planning/2026-04/"' in contenu
    assert "/historique/" not in contenu


def test_entete_version_et_non_verifiee(client, cabinet, connecter, fiches):
    version = _importe(cabinet)
    connecter(client, cabinet)

    reponse = client.get(URL)
    contenu = reponse.content.decode()

    assert f"Version {version.numero}" in contenu
    assert "non vérifiée" in contenu and "importée le" in contenu
    assert reponse.context["importe_le"] is not None


# --- Confidentialité ----------------------------------------------------------


def test_ni_data_ni_type_d_absence(client, cabinet, connecter, fiches):
    """La page ne sert pas `DATA` : avec des absences de tout type, elle n'en dit rien."""
    for libelle, jour in (("Maladie", 3), ("Congé payé", 4)):
        fabrique_absences.absence(
            fiches["test_ass"],
            fabrique.type_absence(libelle),
            datetime.date(2026, 3, jour),
            datetime.date(2026, 3, jour),
            statut=AbsenceSalariee.Statut.DECLAREE,
        )
    _importe(cabinet)
    connecter(client, cabinet)

    contenu = client.get(URL).content.decode()

    for mot in TYPES + BLOCS + ("json_script", "moteur.js", "conges"):
        assert mot not in contenu, mot


# --- `sans_import.html` et `copie` --------------------------------------------


def test_sans_import_renvoie_vers_la_lecture(client, cabinet, connecter, fiches):
    _importe(cabinet)
    connecter(client, cabinet)

    contenu = client.get(PAGE).content.decode()

    assert "Aucun import de présences réussi" in contenu   # message existant intact
    assert "le consulter" in contenu and f'href="{URL}"' in contenu


def test_sans_import_sans_lien_si_aucune_version(client, cabinet, connecter, fiches):
    connecter(client, cabinet)

    contenu = client.get(PAGE).content.decode()

    assert "Aucun import de présences réussi" in contenu
    assert "le consulter" not in contenu


def test_sans_import_sans_lien_pour_une_version_ordinaire(client, cabinet, connecter):
    """Un mois sans présences mais à version ordinaire ne renvoie nulle part."""
    fabrique.personnes()
    services.enregistrer(MOIS, 0, fabrique.etat(), cabinet)
    connecter(client, cabinet)

    contenu = client.get(PAGE).content.decode()

    assert "le consulter" not in contenu


def test_copie_refusee_sur_un_mois_historique(client, cabinet, connecter, fiches):
    _importe(cabinet)
    connecter(client, cabinet)

    assert client.get(COPIE).status_code == 404


def test_copie_inchangee_sur_une_version_ordinaire(client, cabinet, connecter):
    fabrique.jeu_complet(cabinet)
    services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    connecter(client, cabinet)

    assert client.get(f"/planning/{fabrique.MOIS}/copie/").status_code == 200


# --- `est_historique` ---------------------------------------------------------


def test_est_historique_les_trois_cas(cabinet, fiches):
    """La 7a n'éprouvait que le cas vrai ; les deux faux comptent autant."""
    fabrique.jeu_complet(cabinet)
    ordinaire = services.enregistrer(fabrique.MOIS, 0, fabrique.etat_propre(), cabinet)
    assert services.est_historique(ordinaire) is False        # non publiée : `[]`

    publiee = services.publier(fabrique.MOIS, ordinaire.numero, cabinet)
    assert services.est_historique(publiee) is False          # dict à trois clés

    assert services.est_historique(_importe(cabinet)) is True
