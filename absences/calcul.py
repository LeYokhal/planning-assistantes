"""Calcul des jours comptés pour la paie.

Formule du § 4.2 du plan v3, dans sa version corrigée. Ce que la v2 avait faux
et qu'il faut garder en tête en relisant :

* `F` déduisait les fériés du lundi au vendredi sans vérifier qu'ils tombaient
  un jour OUVERT. Sous le régime mardi→samedi, un lundi de Pentecôte retirait
  une brique alors que le cabinet était fermé ce jour-là : un jour de paie perdu
  par la salariée.
* `J` n'excluait pas les fériés, si bien qu'un même jour était compté dans `J`
  ET réservé par `F` — en contradiction avec la justification de `F`.

Module PUR : il lit `Personne`, les règles et le calendrier, n'écrit rien, ne
journalise rien et ne connaît ni `AbsenceSalariee` ni l'audit. C'est ce qui le
rend vérifiable à la main, cas par cas, dans la recette.

Aucune donnée manquante n'est inventée (décision N) : un contrat que les règles
ne savent pas poser rend 0 et un signal, et c'est la validatrice qui tranche.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from comptes.models import Personne
from comptes.noms import JOURS_FR, jour_canonique
from regles.chargeur import charger, jours_ouverture
from socle.feries import est_ferie

SIGNAL_SANS_CONTRAT = "sans_contrat"
SIGNAL_HEURES_HORS_GABARITS = "heures_hors_gabarits"

MESSAGES = {
    SIGNAL_SANS_CONTRAT: (
        "Contrat incomplet : ni heures hebdomadaires ni jours fixes. "
        "Les jours comptés sont à saisir à la main."
    ),
    SIGNAL_HEURES_HORS_GABARITS: (
        "Contrat incomplet : les heures hebdomadaires ne correspondent à aucun "
        "gabarit connu. Les jours comptés sont à saisir à la main."
    ),
}


@dataclass(frozen=True)
class Resultat:
    """Jours comptés, les DATES qui les portent, et le signal éventuel.

    `dates` est la raison d'être de ce module pour la paie : ce sont les jours
    effectivement retenus, en clair. C'est ce qui permet de répartir une absence
    à cheval entre deux mois **sans jamais relancer le calcul sur un morceau** —
    un recoupement appliquerait le plafond hebdomadaire une fois par morceau et
    gonflerait le total (une semaine à cheval pour un contrat 27 h donnerait 5
    jours au lieu de 3).

    Invariant tenu partout : `jours == len(dates)`.
    """

    jours: Decimal
    dates: tuple = ()
    signal: str = ""

    @property
    def message(self):
        """Phrase à afficher, vide s'il n'y a rien à signaler. Sans nom ni type."""
        return MESSAGES.get(self.signal, "")

    @property
    def dates_iso(self):
        """Les dates retenues en ISO, telles qu'elles sont stockées en base."""
        return [jour.isoformat() for jour in self.dates]


def _resultat(dates, signal=""):
    """Fabrique un `Resultat` en tenant l'invariant `jours == len(dates)`."""
    dates = tuple(dates)
    return Resultat(jours=_decimal(len(dates)), dates=dates, signal=signal)


def _decimal(nombre):
    """Entier de jours -> décimal à une décimale, comme la colonne en base."""
    return Decimal(nombre).quantize(Decimal("0.1"))


def _nom_du_jour(jour):
    """« Lundi », « Mardi »… à partir d'une date."""
    return JOURS_FR[jour.weekday()]


def _jours_fixes_canoniques(personne):
    """Jours fixes de la personne, normalisés. Une valeur illisible est ignorée.

    `jours_fixes` est un JSONField alimenté par l'import de la fiche : il peut
    contenir n'importe quoi si la fiche dérive, et le calcul de paie n'est pas
    l'endroit où le découvrir brutalement.
    """
    retenus = []
    for brut in personne.jours_fixes or ():
        canonique = jour_canonique(brut) if isinstance(brut, str) else None
        if canonique is not None and canonique not in retenus:
            retenus.append(canonique)
    return tuple(retenus)


def _dates(debut, fin):
    """Chaque date de la plage, bornes comprises."""
    for decalage in range((fin - debut).days + 1):
        yield debut + datetime.timedelta(days=decalage)


def _semaines(debut, fin):
    """Découpe la plage en semaines lundi → dimanche.

    Rend `(lundi, dimanche, premier_jour_couvert, dernier_jour_couvert)` : la
    semaine complète sert au décompte des fériés, la portion couverte au
    décompte des jours d'absence.
    """
    courant = debut
    while courant <= fin:
        lundi = courant - datetime.timedelta(days=courant.weekday())
        dimanche = lundi + datetime.timedelta(days=6)
        yield lundi, dimanche, max(debut, lundi), min(fin, dimanche)
        courant = dimanche + datetime.timedelta(days=1)


def _ouvert(jour, regles):
    """Vrai si le cabinet ouvre ce jour-là, au régime applicable à cette date."""
    return _nom_du_jour(jour) in jours_ouverture(jour, regles)


def _jours_fixes(personne, debut, fin):
    """Branche « jours fixes » : les jours fixes de la personne, hors fériés."""
    fixes = _jours_fixes_canoniques(personne)
    return _resultat(
        jour
        for jour in _dates(debut, fin)
        if _nom_du_jour(jour) in fixes and not est_ferie(jour)
    )


def _contrat_horaire(personne, debut, fin, briques, regles):
    """Branche « contrat horaire » : semaine par semaine, `min(J, max(0, B − F))`.

    Le plafond est appliqué **une seule fois par semaine, sur la semaine
    entière**, et ce sont les PREMIERS jours de la semaine qui sont retenus. La
    répartition par mois se lit ensuite sur les dates, sans jamais rejouer le
    calcul : c'est ce qui empêche le plafond de s'appliquer deux fois quand une
    semaine est à cheval sur deux mois.
    """
    retenus = []
    for lundi, dimanche, couvert_debut, couvert_fin in _semaines(debut, fin):
        # J, en dates : jours d'absence sur un jour d'ouverture, fériés EXCLUS.
        candidats = [
            jour
            for jour in _dates(couvert_debut, couvert_fin)
            if _ouvert(jour, regles) and not est_ferie(jour)
        ]
        # F : fériés de la semaine ENTIÈRE tombant un jour d'ouverture — eux
        # seuls occupaient déjà une brique du contrat.
        f = sum(
            1
            for jour in _dates(lundi, dimanche)
            if est_ferie(jour) and _ouvert(jour, regles)
        )
        plafond = max(0, briques - f)
        retenus.extend(candidats[:plafond])
    return _resultat(retenus)


def jours_comptes(personne, date_debut, date_fin, regles=None):
    """Jours comptés pour la paie sur la plage, bornes comprises.

    Ordre des branches, repris de `personnes/services.py:_avertir_heures` pour
    que le calcul dise la même chose que l'avertissement d'import :

    1. heures hebdomadaires connues **et** présentes dans les gabarits →
       contrat horaire ;
    2. heures hebdomadaires hors gabarits → contrat incomplet, 0 et signal ;
    3. pas d'heures mais des jours fixes → branche jours fixes ;
    4. ni l'un ni l'autre → contrat incomplet, 0 et signal.
    """
    regles = regles or charger()

    if personne.heures_hebdo:
        gabarit = regles.gabarits.get(int(personne.heures_hebdo))
        if gabarit is None:
            return _resultat((), signal=SIGNAL_HEURES_HORS_GABARITS)
        return _contrat_horaire(personne, date_debut, date_fin, len(gabarit), regles)

    if _jours_fixes_canoniques(personne):
        return _jours_fixes(personne, date_debut, date_fin)

    return _resultat((), signal=SIGNAL_SANS_CONTRAT)


def jours_comptes_de(absence, regles=None):
    """Raccourci sur une `AbsenceSalariee` déjà constituée."""
    return jours_comptes(
        absence.personne, absence.date_debut, absence.date_fin, regles=regles
    )


def est_salariee(personne):
    """Vrai si une absence peut porter sur cette personne (décision P)."""
    return personne.role_metier in (
        Personne.RoleMetier.ASSISTANTE,
        Personne.RoleMetier.SECRETAIRE,
    )
