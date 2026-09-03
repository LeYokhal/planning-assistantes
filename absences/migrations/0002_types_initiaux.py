"""Pose les treize types d'absence du cabinet.

Idempotente : `get_or_create` sur le libellé, et **aucune réécriture** d'un type
déjà présent. Un rejeu de la migration sur une base où le cabinet a désactivé un
type ou changé son ordre ne défait pas son geste.

⚠️ Les libellés reproduisent le select Notion **tel quel**, fautes comprises
(« Congé évenement familial », « Décés », « Ecole »). Les corriger ici ferait
diverger l'application de la source que les salariées connaissent, et casserait
tout rapprochement avec l'historique Notion, qui reste consultable en archive.

Le retour arrière est volontairement neutre : supprimer les types effacerait des
absences par cascade PROTECT (donc échouerait), ou pire, laisserait la base dans
un état à moitié défait.
"""

from django.db import migrations

TYPES = [
    # (libellé, bloquant, catégorie, paie, ordre)
    ("Congé payé", True, "demande", True, 10),
    ("Congé sans solde", True, "demande", True, 20),
    ("Maladie", True, "declare", True, 30),
    ("Congé enfant malade", True, "declare", True, 40),
    ("Congé grossesse", True, "declare", True, 50),
    ("Congé évenement familial", True, "declare", False, 60),
    ("Décés", True, "declare", False, 70),
    ("Ecole", True, "declare", False, 80),
    ("Heures sans solde", False, "declare", False, 90),
    ("Départ plus tôt", False, "declare", False, 100),
    ("Départ plus tard", False, "declare", False, 110),
    ("Retard", False, "declare", False, 120),
    ("Autre", False, "declare", False, 130),
]


def poser_les_types(apps, schema_editor):
    TypeAbsence = apps.get_model("absences", "TypeAbsence")
    for libelle, bloquant, categorie, paie, ordre in TYPES:
        TypeAbsence.objects.get_or_create(
            libelle=libelle,
            defaults={
                "bloquant": bloquant,
                "categorie": categorie,
                "paie": paie,
                "actif": True,
                "ordre": ordre,
            },
        )


def ne_rien_defaire(apps, schema_editor):
    """Retour arrière neutre : voir le docstring du module."""


class Migration(migrations.Migration):

    dependencies = [
        ("absences", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(poser_les_types, ne_rien_defaire),
    ]
