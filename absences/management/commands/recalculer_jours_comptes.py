"""Rejoue le calcul des jours comptés sur les absences effectives.

À passer quand les périodes d'ouverture changent dans `regles.json`, ou quand
une correction de la formule est déployée.

⚠️ Une absence **corrigée à la main n'est jamais touchée** : sa valeur retenue
est le geste de la validatrice, et l'écraser silencieusement ferait perdre à la
fois la correction et la trace de sa raison. La valeur calculée, elle, est
rafraîchie même sur une absence corrigée : l'écart entre les deux reste ainsi
lisible.
"""

from django.core.management.base import BaseCommand

from absences import services
from absences.models import AbsenceSalariee


class Command(BaseCommand):
    help = "Recalcule les jours comptes des absences effectives."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--mois",
            help="Limite au mois AAAA-MM (sur la plage affichee du mois).",
        )
        parseur.add_argument(
            "--a-blanc",
            action="store_true",
            help="Montre ce qui changerait, sans rien ecrire.",
        )

    def handle(self, *args, **options):
        absences = AbsenceSalariee.objects.filter(
            statut__in=AbsenceSalariee.STATUTS_EFFECTIFS
        ).select_related("personne")

        if options["mois"]:
            from presences.fenetres import plage_mois

            try:
                plage = plage_mois(options["mois"])
            except ValueError:
                self.stderr.write(self.style.ERROR("mois invalide (attendu AAAA-MM)"))
                return
            absences = absences.filter(
                date_debut__lte=plage.fin, date_fin__gte=plage.debut
            )

        recalculees = 0
        preservees = 0
        changees = 0

        for absence in absences:
            if absence.corrigee:
                preservees += 1

            avant = absence.jours_comptes_calcules
            if options["a_blanc"]:
                from absences import calcul

                apres = calcul.jours_comptes_de(absence).jours
            else:
                services.recalculer(absence)
                apres = absence.jours_comptes_calcules

            recalculees += 1
            if avant != apres:
                changees += 1
                self.stdout.write(
                    f"  absence #{absence.pk} : calcules {avant} -> {apres}"
                    + (" (valeur retenue preservee)" if absence.corrigee else "")
                )

        prefixe = "[a blanc] " if options["a_blanc"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixe}{recalculees} absence(s) recalculee(s), "
                f"{changees} changement(s), "
                f"{preservees} correction(s) manuelle(s) preservee(s)."
            )
        )
