"""Fabrique d'exports de fiche personnel pour les tests.

Noms fictifs uniquement. Aucune donnée réelle n'entre ici.
"""

import json

# Passer cette sentinelle en valeur retire la colonne de la ligne produite :
# de quoi fabriquer un export à qui il manque une colonne.
MANQUANT = object()


def ligne_fiche(
    name,
    department="Assistante",
    planning="__YES__",
    heures=39,
    jours=None,
):
    """Une ligne d'export, avec exactement les cinq colonnes attendues."""
    ligne = {
        "Name": name,
        "Department": department,
        "Planning": planning,
        "Heures hebdomadaire": heures,
        "Jours de travail": jours,
    }
    return {cle: valeur for cle, valeur in ligne.items() if valeur is not MANQUANT}


def fiche(lignes):
    """Forme `{"results": [...]}`, celle que produit une requête Notion."""
    return json.dumps({"results": list(lignes)}, ensure_ascii=False).encode("utf-8")


def fiche_liste(lignes):
    """Forme liste directe, également acceptée."""
    return json.dumps(list(lignes), ensure_ascii=False).encode("utf-8")
