"""Fabrique de payloads S7 FICTIFS pour les tests.

⚠️ Les exports S7 réels ne servent QUE à la recette manuelle depuis le
navigateur. Aucun test ne les ouvre, ne les copie ni ne les référence : tout ce
qui est lu ici est fabriqué de toutes pièces, avec des agendas inventés.

L'enveloppe du `message` est CALCULÉE à partir du détail, comme le fait l'outil
réel : c'est ce qui rend l'invariant testable dans les deux sens — un payload
cohérent passe, un payload retouché à la main est refusé.
"""

import datetime
import json

AGENDAS = ("DUPONT Alice", "MARTIN Bob")

VERDICT_OUVERT = "ouvert"
VERDICT_ATYPIQUE = "ouvert (atypique)"
VERDICT_FERME = "fermé"
VERDICT_NON_PLANIFIE = "non planifié"

JOURNEE_TYPE = (("09:00", "13:00"), ("14:00", "18:00"))


def _minutes(heure):
    heures, minutes = heure.split(":")
    return int(heures) * 60 + int(minutes)


def ligne(
    praticien,
    verdict=VERDICT_OUVERT,
    presence=True,
    creneaux=(),
    nb_rdv=0,
    duree_rdv=0,
    journee_courte=False,
):
    """Une ligne praticien complète : les treize clés du contrat S7."""
    creneaux = [list(creneau) for creneau in creneaux]
    total = sum(_minutes(fin) - _minutes(debut) for debut, fin in creneaux)
    amplitude = (
        _minutes(creneaux[-1][1]) - _minutes(creneaux[0][0]) if creneaux else 0
    )
    return {
        "praticien": praticien,
        "verdict": verdict,
        "presence": presence,
        "journee_courte": journee_courte,
        "creneaux": creneaux,
        "creneaux_effectifs": creneaux,
        "amplitude_minutes": amplitude,
        "total_minutes": total,
        "amplitude_effective_minutes": amplitude,
        "total_effectif_minutes": total,
        "nb_rdv": nb_rdv,
        "duree_rdv_vivants_minutes": duree_rdv,
        "absences": [],
    }


def regle_defaut(jour, indice):
    """Semaine ordinaire : le premier agenda tous les jours ouvrés, le second lundi / mercredi / vendredi."""
    if jour.weekday() >= 5:
        return {"verdict": VERDICT_NON_PLANIFIE, "presence": False}
    if indice == 0 or jour.weekday() in (0, 2, 4):
        return {
            "verdict": VERDICT_OUVERT,
            "presence": True,
            "creneaux": JOURNEE_TYPE,
            "nb_rdv": 12,
            "duree_rdv": 360,
        }
    return {"verdict": VERDICT_NON_PLANIFIE, "presence": False}


def fabriquer_payload(debut, fin, praticiens=AGENDAS, regle=None):
    """Construit un payload cohérent : enveloppe et comptages calculés."""
    regle = regle or regle_defaut

    jours = []
    for decalage in range((fin - debut).days + 1):
        jour = debut + datetime.timedelta(days=decalage)
        lignes = [
            ligne(praticien=praticien, **regle(jour, indice))
            for indice, praticien in enumerate(praticiens)
        ]
        jours.append(
            {
                "date": jour.isoformat(),
                "nb_ouverts": sum(
                    1
                    for element in lignes
                    if element["verdict"] in (VERDICT_OUVERT, VERDICT_ATYPIQUE)
                ),
                "nb_presents": sum(1 for element in lignes if element["presence"]),
                "praticiens": lignes,
            }
        )

    toutes = [element for jour in jours for element in jour["praticiens"]]
    compte = {
        VERDICT_OUVERT: 0,
        VERDICT_ATYPIQUE: 0,
        VERDICT_FERME: 0,
        VERDICT_NON_PLANIFIE: 0,
    }
    for element in toutes:
        if element["verdict"] in compte:
            compte[element["verdict"]] += 1
    presents = sum(1 for element in toutes if element["presence"])

    message = (
        f"{len(jours)} jour(s) du {debut.isoformat()} au {fin.isoformat()}, "
        f"{len(praticiens)} praticien(s) : "
        f"{compte[VERDICT_OUVERT]} ouvert(s), "
        f"{compte[VERDICT_ATYPIQUE]} atypique(s), "
        f"{compte[VERDICT_FERME]} fermé(s), "
        f"{compte[VERDICT_NON_PLANIFIE]} non planifié(s), "
        f"{presents} présent(s)"
    )

    return {
        "succes": True,
        "message": message,
        "donnees": {
            "date": debut.isoformat(),
            "date_fin": fin.isoformat(),
            "seuil_heures": 4.0,
            "seuil_presence": 5.0,
            "mode": "tous",
            "jours": jours,
        },
    }


def _octets(valeur):
    return json.dumps(valeur, ensure_ascii=False).encode("utf-8")


def en_wrapper_liste(payload):
    """Forme rendue par l'interface claude.ai : `[{"text": "<json>"}]`."""
    return _octets([{"text": json.dumps(payload, ensure_ascii=False)}])


def en_wrapper_dict(payload):
    """Forme rendue par certains clients MCP : `{"text": "<json>"}`."""
    return _octets({"text": json.dumps(payload, ensure_ascii=False)})


def en_direct(payload):
    """Payload direct, sans wrapper."""
    return _octets(payload)
