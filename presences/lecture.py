"""Lecture et contrôle d'un payload S7 (`consulter_jours_travail`, mode « tous »).

Port durci de `charger_s7` du skill v1
(`reference/skill-v1/scripts/build_planning.py`). Les gardes sont strictes et ne
se contournent pas : un payload qui ne les passe pas toutes est refusé en bloc,
et rien n'entre dans l'écran des présences.

Deux durcissements par rapport au skill :

* le skill n'appliquait l'invariant que si l'enveloppe figurait dans le
  `message` — ici, une enveloppe absente est un refus ;
* le mode doit être « tous ». Un payload mono-praticien afficherait un cabinet
  presque vide, un praticien manquant se lisant « ne travaille pas ».

Aucun message d'erreur ne transporte de donnée patient : les payloads S7 n'en
contiennent pas, et seuls nos propres libellés (français, tronqués) sortent d'ici.
"""

import datetime
import json
import re
import unicodedata
from dataclasses import dataclass

# Les accents sont portés par des échappements \u00e9 : le motif et les
# verdicts ne dépendent ainsi ni de l'encodage du fichier source ni de sa forme
# Unicode. Le message lu est normalisé en NFC avant la recherche (voir `lire`).
RX_ENVELOPPE = re.compile(
    r"(\d+) ouvert\(s\), (\d+) atypique\(s\), (\d+) ferm\u00e9\(s\), "
    r"(\d+) non planifi\u00e9\(s\), (\d+) pr\u00e9sent\(s\)"
)

VERDICT_OUVERT = "ouvert"
VERDICT_ATYPIQUE = "ouvert (atypique)"
VERDICT_FERME = "ferm\u00e9"
VERDICT_NON_PLANIFIE = "non planifi\u00e9"

FORME_WRAPPER_LISTE = "wrapper_liste"
FORME_WRAPPER_DICT = "wrapper_dict"
FORME_DIRECT = "direct"

MODE_ATTENDU = "tous"
FENETRE_MAX_JOURS = 31
LONGUEUR_MAX_ERREUR = 200


class PayloadInvalide(Exception):
    """Payload refusé par une garde de lecture. Message français, tronqué."""

    def __init__(self, message):
        super().__init__(str(message)[:LONGUEUR_MAX_ERREUR])


@dataclass(frozen=True)
class Lecture:
    """Résultat d'une lecture réussie : tout est recompté, rien n'est cru sur parole."""

    payload: dict
    forme: str
    debut: datetime.date
    fin: datetime.date
    mode: str
    message: str
    attendu: tuple
    obtenu: tuple
    nb_jours: int
    nb_lignes: int
    nb_presents: int
    praticiens: tuple


def _charger_texte(texte):
    """Décode la charge JSON transportée dans la clé `text` d'un wrapper."""
    if not isinstance(texte, str):
        raise PayloadInvalide("forme de payload inconnue")
    try:
        interieur = json.loads(texte)
    except ValueError:
        raise PayloadInvalide("JSON illisible") from None
    if not isinstance(interieur, dict):
        raise PayloadInvalide("forme de payload inconnue")
    return interieur


def deballer(brut):
    """Retire l'éventuel wrapper de l'interface et renvoie `(payload, forme)`.

    Trois formes acceptées, exactement celles que sait lire le skill v1 : la
    liste `[{"text": "..."}]`, le dict `{"text": "..."}` sans `donnees`, et le
    payload direct `{"succes", "message", "donnees"}`.
    """
    if isinstance(brut, list):
        if not brut or not isinstance(brut[0], dict) or "text" not in brut[0]:
            raise PayloadInvalide("forme de payload inconnue")
        return _charger_texte(brut[0]["text"]), FORME_WRAPPER_LISTE

    if isinstance(brut, dict):
        if "text" in brut and "donnees" not in brut:
            return _charger_texte(brut["text"]), FORME_WRAPPER_DICT
        return brut, FORME_DIRECT

    raise PayloadInvalide("forme de payload inconnue")


def recompter(payload):
    """Recompte `(ouvert, atypique, fermé, non planifié, présents)` sur le détail.

    C'est ce recompte, jamais l'enveloppe du `message`, qui fait foi.
    """
    ouverts = atypiques = fermes = non_planifies = presents = 0
    for jour in payload["donnees"]["jours"]:
        if not isinstance(jour, dict) or not isinstance(jour.get("praticiens"), list):
            raise PayloadInvalide("jours illisibles (praticiens absents)")
        for ligne in jour["praticiens"]:
            if not isinstance(ligne, dict):
                raise PayloadInvalide("ligne de praticien illisible")
            verdict = ligne.get("verdict")
            if verdict == VERDICT_OUVERT:
                ouverts += 1
            elif verdict == VERDICT_ATYPIQUE:
                atypiques += 1
            elif verdict == VERDICT_FERME:
                fermes += 1
            elif verdict == VERDICT_NON_PLANIFIE:
                non_planifies += 1
            presents += bool(ligne.get("presence"))
    return (ouverts, atypiques, fermes, non_planifies, presents)


def _date_ou_none(valeur):
    """Convertit une date ISO en `date`, ou renvoie None si ce n'en est pas une."""
    if not isinstance(valeur, str):
        return None
    try:
        return datetime.date.fromisoformat(valeur)
    except ValueError:
        return None


def lire(contenu):
    """Lit des octets et renvoie une `Lecture`, ou lève `PayloadInvalide`.

    L'ordre des gardes est délibéré : forme, succès, mode, fenêtre, jours,
    enveloppe, invariant. Le premier refus arrête tout.
    """
    try:
        brut = json.loads(contenu.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise PayloadInvalide("JSON illisible") from None

    payload, forme = deballer(brut)

    if not payload.get("succes"):
        raise PayloadInvalide(
            "appel S7 en échec : " + str(payload.get("message", ""))[:150]
        )

    donnees = payload.get("donnees")
    if not isinstance(donnees, dict):
        raise PayloadInvalide("donnees absentes")

    mode = donnees.get("mode")
    if mode != MODE_ATTENDU:
        raise PayloadInvalide(
            f"mode « {mode} » refusé : seul le mode « {MODE_ATTENDU} » est accepté"
        )

    debut = _date_ou_none(donnees.get("date"))
    # `date_fin` nulle ou vide = journée unique.
    brut_fin = donnees.get("date_fin")
    fin = debut if brut_fin in (None, "") else _date_ou_none(brut_fin)
    if debut is None or fin is None or fin < debut:
        raise PayloadInvalide("fenêtre absente ou invalide")

    nb_jours_fenetre = (fin - debut).days + 1
    if nb_jours_fenetre > FENETRE_MAX_JOURS:
        raise PayloadInvalide(
            f"fenêtre de {nb_jours_fenetre} jours, maximum {FENETRE_MAX_JOURS}"
        )

    jours = donnees.get("jours")
    if not isinstance(jours, list) or not jours:
        raise PayloadInvalide("jours absents")

    attendues = [
        (debut + datetime.timedelta(days=n)).isoformat()
        for n in range(nb_jours_fenetre)
    ]
    obtenues = [jour.get("date") if isinstance(jour, dict) else None for jour in jours]
    if obtenues != attendues:
        raise PayloadInvalide(
            "jours incohérents avec la fenêtre (dates manquantes, doublons ou désordre)"
        )

    # NFC : un message en forme décomposée (e + accent combinant) doit matcher
    # le motif aussi bien qu'un message composé.
    message = unicodedata.normalize("NFC", str(payload.get("message", "")))
    correspondance = RX_ENVELOPPE.search(message)
    if correspondance is None:
        raise PayloadInvalide("enveloppe absente du message")

    attendu = tuple(int(valeur) for valeur in correspondance.groups())
    obtenu = recompter(payload)
    if attendu != obtenu:
        raise PayloadInvalide(
            f"écart enveloppe / recompte : attendu {attendu}, obtenu {obtenu}"
        )

    praticiens = sorted(
        {
            str(ligne.get("praticien", "")).strip()
            for jour in jours
            for ligne in jour["praticiens"]
        },
        key=str.casefold,
    )
    nb_lignes = sum(len(jour["praticiens"]) for jour in jours)

    return Lecture(
        payload=payload,
        forme=forme,
        debut=debut,
        fin=fin,
        mode=mode,
        message=message,
        attendu=attendu,
        obtenu=obtenu,
        nb_jours=len(jours),
        nb_lignes=nb_lignes,
        nb_presents=obtenu[4],
        praticiens=tuple(praticiens),
    )
