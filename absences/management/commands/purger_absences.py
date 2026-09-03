"""Purge les absences dont l'échéance de rétention est passée.

Deux temps, dans cet ordre :

1. **rattrapage** — pose `a_effacer_le` sur les absences effectives qui n'en ont
   pas. C'est ce qui rend la décision F opérante : tant que
   `RETENTION_ABSENCES_JOURS` est absente, rien n'est posé et rien n'est purgé ;
   le jour où le cabinet fixe la durée, la première exécution rattrape le stock.
   L'échéance est comptée depuis la date de FIN de l'absence, pas depuis
   aujourd'hui : une absence de l'an dernier ne gagne pas une nouvelle vie.
2. **purge** — supprime les absences dont l'échéance est atteinte.

Réglage absent = la commande ne fait rien et le dit. Aucune exception : elle a
vocation à tourner sans surveillance.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from absences import services
from absences.models import AbsenceSalariee
from audit.models import Action
from audit.services import journaliser


class Command(BaseCommand):
    help = "Pose les echeances de retention manquantes, puis purge les absences echues."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--a-blanc",
            action="store_true",
            help="Montre ce qui serait fait, sans rien ecrire.",
        )

    def handle(self, *args, **options):
        a_blanc = options["a_blanc"]
        jours = services._retention_jours()

        if jours is None:
            self.stdout.write(
                self.style.WARNING(
                    "RETENTION_ABSENCES_JOURS absente ou nulle : aucune purge. "
                    "Les absences restent en base, et cette commande les "
                    "rattrapera le jour ou le reglage sera pose."
                )
            )
            return

        aujourd_hui = timezone.localdate()

        # 1. Rattrapage des echeances manquantes.
        a_rattraper = AbsenceSalariee.objects.filter(
            statut__in=AbsenceSalariee.STATUTS_EFFECTIFS, a_effacer_le__isnull=True
        )
        rattrapees = 0
        for absence in a_rattraper:
            echeance = services.date_effacement(depuis=absence.date_fin)
            if not a_blanc:
                absence.a_effacer_le = echeance
                absence.save(update_fields=["a_effacer_le"])
            rattrapees += 1

        # 2. Purge des echues.
        echues = AbsenceSalariee.objects.filter(a_effacer_le__lte=aujourd_hui)
        purgees = 0
        for absence in echues:
            identifiant = absence.pk
            personne_id = absence.personne_id
            if not a_blanc:
                absence.delete()
                journaliser(
                    Action.ABSENCE_PURGEE,
                    objet=None,
                    absence_id=identifiant,
                    personne_id=personne_id,
                )
            purgees += 1

        prefixe = "[a blanc] " if a_blanc else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixe}retention {jours} jour(s) : "
                f"{rattrapees} echeance(s) posee(s), {purgees} absence(s) purgee(s)."
            )
        )
