"""Données de paie d'un mois, et leur mise en forme.

Le paragraphe est construit ICI, côté serveur (décision I), et non dans n8n :
c'est l'application qui sait ce qu'elle a validé, et un texte assemblé côté
workflow dériverait au premier changement de règle sans que rien ne le signale.

⚠️ Le paragraphe et les données portent le NOM des salariées et un nombre de
jours — c'est le sens même de la paie — mais **jamais le type d'absence ni la
précision** : la comptable a besoin de savoir combien de jours sont à payer,
pas qu'une salariée était en arrêt maladie.

LA PLAGE, ET LA RÉPARTITION
---------------------------

Deux règles, posées le 01/09/2026 après le défaut trouvé au checkpoint :

1. **La paie filtre sur le MOIS CALENDAIRE**, pas sur `presences.fenetres.plage_mois`.
   Cette dernière rend des semaines complètes — l'outil du planning — et deux
   mois consécutifs s'y recouvrent de sept jours : une absence de fin septembre
   ressortait dans la paie d'octobre.
2. **Chaque mois reçoit sa portion**, comme le fait la comptable aujourd'hui.
   La répartition se lit sur `AbsenceSalariee.jours_retenus`, les dates figées
   au calcul.

⚠️ **On ne recoupe JAMAIS une absence pour relancer le calcul sur les morceaux.**
Le plafond hebdomadaire s'appliquerait une fois par morceau et gonflerait le
total. Contre-exemple : salariée à 27 h (B = 3), absente une semaine entière à
cheval sur deux mois, régime mardi→samedi. Sur l'absence entière, J = 5, plafond
3, donc **3 jours**. Recoupée en 2 + 3 jours ouvrables, on obtiendrait
min(2,3) + min(3,3) = **5**. Lire les dates retenues évite le piège par
construction : le plafond a déjà été appliqué, une fois, au calcul.
"""

import calendar
import datetime
import re
from decimal import ROUND_FLOOR, Decimal

from . import services

MOIS_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

DEMI = Decimal("0.5")


def plage_calendaire(mois):
    """Premier et dernier jour du mois « AAAA-MM ». Lève `ValueError` sinon.

    Volontairement distincte de `presences.fenetres.plage_mois`, qui rend des
    semaines complètes : la paie se compte en mois, le planning en semaines.
    """
    if not isinstance(mois, str) or not MOIS_RE.match(mois):
        raise ValueError("mois invalide")
    annee, numero = (int(part) for part in mois.split("-"))
    dernier = calendar.monthrange(annee, numero)[1]
    return datetime.date(annee, numero, 1), datetime.date(annee, numero, dernier)


def _cle_mois(jour):
    """« AAAA-MM » d'une date."""
    return f"{jour.year}-{jour.month:02d}"


def _plancher_demi(valeur):
    """Arrondit au demi-jour INFÉRIEUR. Le reste est réattribué par ailleurs."""
    return ((valeur / DEMI).to_integral_value(rounding=ROUND_FLOOR) * DEMI).quantize(
        Decimal("0.1")
    )


def _dates_retenues(absence):
    """Les jours retenus de l'absence, en dates. Une entrée illisible est ignorée."""
    dates = []
    for brut in absence.jours_retenus or ():
        try:
            dates.append(datetime.date.fromisoformat(brut))
        except (TypeError, ValueError):
            continue
    return dates


def portions_par_mois(absence):
    """Répartit les jours comptés de l'absence entre les mois qu'elle touche.

    Renvoie `(portions, reparti)` où `portions` est un dict « AAAA-MM » →
    `Decimal`, et `reparti` dit si la répartition a pu être calculée.

    Trois cas :

    * **absence non corrigée** — un jour retenu vaut un jour facturé au mois où
      il tombe. Exact, sans arrondi, et la somme des mois vaut le total par
      construction ;
    * **absence corrigée** — la valeur retenue est répartie au prorata des jours
      retenus de chaque mois, arrondie au demi-jour inférieur ; le reste va au
      mois du **premier** jour retenu, pour que la somme retombe exactement sur
      la valeur corrigée ;
    * **absence corrigée sans aucun jour retenu** (contrat incomplet corrigé à
      la main) — il n'y a rien sur quoi répartir : la totalité va au mois du
      premier jour de l'absence, et `reparti` vaut `False` pour que l'écran et
      la sortie le signalent.
    """
    total = absence.jours_comptes or Decimal("0")
    retenues = _dates_retenues(absence)

    if not absence.corrigee:
        portions = {}
        for jour in retenues:
            cle = _cle_mois(jour)
            portions[cle] = portions.get(cle, Decimal("0")) + Decimal("1")
        return {cle: valeur.quantize(Decimal("0.1")) for cle, valeur in portions.items()}, True

    if not retenues:
        return {_cle_mois(absence.date_debut): total.quantize(Decimal("0.1"))}, False

    # Prorata des jours retenus, dans l'ordre chronologique.
    comptes = {}
    for jour in retenues:
        cle = _cle_mois(jour)
        comptes[cle] = comptes.get(cle, 0) + 1

    portions = {
        cle: _plancher_demi(total * Decimal(nombre) / Decimal(len(retenues)))
        for cle, nombre in comptes.items()
    }
    reste = total - sum(portions.values())
    if reste:
        # Le premier jour retenu porte le reliquat : la somme des mois vaut
        # exactement la valeur corrigée, sans jamais dépasser.
        portions[_cle_mois(retenues[0])] += reste
    return {cle: valeur.quantize(Decimal("0.1")) for cle, valeur in portions.items()}, True


def portion_du_mois(absence, mois):
    """Jours à facturer à ce mois pour cette absence, et si la répartition a pu se faire."""
    portions, reparti = portions_par_mois(absence)
    return portions.get(mois, Decimal("0.0")), reparti


def _nom(personne):
    return f"{personne.nom} {personne.prenom}".strip()


def _nombre(valeur):
    """« 3 » plutôt que « 3.0 », « 2,5 » plutôt que « 2.5 »."""
    quantifie = (valeur or Decimal("0")).normalize()
    texte = format(quantifie, "f")
    return texte.replace(".", ",")


def donnees_du_mois(mois, plage):
    """Agrège les jours comptés par salariée sur le mois calendaire.

    `plage` est le couple `(premier, dernier)` rendu par `plage_calendaire`.
    Une salariée sans absence comptée n'apparaît pas : la comptable lit une
    liste de ce qui change, pas un effectif.
    """
    premier, dernier = plage
    par_personne = {}

    for absence in services.absences_du_mois(premier, dernier):
        if absence.jours_comptes is None:
            continue
        portion, reparti = portion_du_mois(absence, mois)
        if not portion:
            # L'absence touche la plage mais aucun de ses jours retenus ne
            # tombe dans ce mois : elle est facturée ailleurs.
            continue

        entree = par_personne.setdefault(
            absence.personne_id,
            {
                "personne_id": absence.personne_id,
                "nom": _nom(absence.personne),
                "code": absence.personne.code or "",
                "jours_comptes": Decimal("0"),
                "absences": [],
            },
        )
        entree["jours_comptes"] += portion
        entree["absences"].append(
            {
                "absence_id": absence.pk,
                "debut": absence.date_debut.isoformat(),
                "fin": absence.date_fin.isoformat(),
                # La portion facturée à CE mois, et le total de l'absence : la
                # comptable doit pouvoir comprendre un chiffre partiel.
                "jours_comptes": str(portion),
                "jours_comptes_absence": str(absence.jours_comptes),
                "a_cheval": portion != absence.jours_comptes,
                "corrigee": absence.corrigee,
                "repartition_calculee": reparti,
            }
        )

    salariees = sorted(par_personne.values(), key=lambda e: e["nom"].casefold())
    for entree in salariees:
        entree["jours_comptes"] = str(entree["jours_comptes"])

    return {
        "mois": mois,
        "debut": premier.isoformat(),
        "fin": dernier.isoformat(),
        "salariees": salariees,
        "paragraphe": paragraphe(mois, salariees),
    }


def paragraphe(mois, salariees):
    """Phrase prête à coller dans le mail de la comptable. Sans type d'absence."""
    if not salariees:
        return f"Paie {mois} : aucune absence à signaler."

    morceaux = [
        f"{entree['nom']} : {_nombre(Decimal(entree['jours_comptes']))} jour(s)"
        for entree in salariees
    ]
    phrase = f"Paie {mois} — absences à décompter : " + " ; ".join(morceaux) + "."

    a_signaler = [
        entree["nom"]
        for entree in salariees
        if any(not a["repartition_calculee"] for a in entree["absences"])
    ]
    if a_signaler:
        phrase += (
            " À vérifier — répartition entre mois non calculable pour : "
            + ", ".join(sorted(set(a_signaler)))
            + "."
        )
    return phrase
