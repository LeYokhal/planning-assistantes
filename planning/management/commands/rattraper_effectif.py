"""Rattrape les marqueurs d'effectif des versions déjà publiées (brique 6b, D6b.10).

Les versions publiées avant la brique 6b n'ont pas de clé `effectif` dans
`verifications` : cette commande la calcule et la range, **sans republier, sans
webhook, sans toucher `publie_le` ni `publie_par`**. Idempotente : une version
déjà marquée est laissée telle quelle. Les versions historiques (C7.8) sont
ignorées : sans présences Doctolib, il n'y a rien à évaluer.

`DATA` est reconstruit avec les imports et les personnes d'aujourd'hui
(`donnees.construire`, une fois par mois) : le compte-rendu dit la vérité
d'aujourd'hui ; quand les imports retenus diffèrent de ceux de la publication,
la ligne de sortie le dit. Aucune vérification de règles : ce n'est pas une
publication.

Sortie, journal d'audit et logs : mois, numéro, comptages — jamais un nom,
jamais un type d'absence.

⚠️ En production : après déploiement, par le cabinet, `--a-blanc` d'abord
(frontière manuelle, Phase 5 de la brique 6b).
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from audit.models import Action
from audit.services import journaliser
from planning import donnees, effectif, services
from planning.models import PlanningVersion

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Calcule les marqueurs d'effectif des versions publiees qui n'en ont pas encore."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--mois",
            help="Limite au mois AAAA-MM.",
        )
        parseur.add_argument(
            "--a-blanc",
            action="store_true",
            help="Montre ce qui serait fait, sans rien ecrire.",
        )

    def handle(self, *args, **options):
        a_blanc = options["a_blanc"]
        versions = PlanningVersion.objects.filter(publiee=True)

        if options["mois"]:
            from presences.fenetres import plage_mois

            try:
                plage_mois(options["mois"])
            except ValueError:
                self.stderr.write(self.style.ERROR("mois invalide (attendu AAAA-MM)"))
                return
            versions = versions.filter(mois=options["mois"])

        prefixe = "[a blanc] " if a_blanc else ""
        donnees_par_mois = {}
        marquees = 0
        ignorees = 0

        for version in versions.order_by("mois", "numero"):
            etiquette = f"{prefixe}{version.mois} v{version.numero}"
            base = version.verifications if isinstance(version.verifications, dict) else {}

            if services.est_historique(version):
                self.stdout.write(f"{etiquette} : historique, ignoree")
                ignorees += 1
                continue
            if "effectif" in base:
                self.stdout.write(f"{etiquette} : deja marquee, ignoree")
                ignorees += 1
                continue

            if version.mois not in donnees_par_mois:
                donnees_par_mois[version.mois] = donnees.construire(version.mois)
            data = donnees_par_mois[version.mois]

            compte_rendu = effectif.calculer(data, version.state)
            compte_rendu["calcule_le"] = timezone.now().isoformat()
            jours = compte_rendu["jours"]
            nb_moins = sum(1 for entree in jours.values() if entree["moins"])
            nb_plus = sum(1 for entree in jours.values() if entree["plus"])
            imports_actuels = {
                (import_["id"], import_["empreinte"]) for import_ in data["meta"].get("imports", [])
            }
            imports_publies = {
                (import_.get("id"), import_.get("empreinte"))
                for import_ in base.get("imports", [])
                if isinstance(import_, dict)
            }
            ecart = (
                ", imports differents de la publication"
                if imports_actuels != imports_publies
                else ""
            )

            if not a_blanc:
                PlanningVersion.objects.filter(pk=version.pk).update(
                    verifications={**base, "effectif": compte_rendu}
                )
                journaliser(
                    Action.PLANNING_EFFECTIF_RATTRAPE,
                    objet=version,
                    mois=version.mois,
                    numero=version.numero,
                    jours_evalues=len(jours),
                    moins=nb_moins,
                    plus=nb_plus,
                )
                logger.info(
                    "planning %s : version %s marquee (%s jours evalues, %s moins, %s plus)",
                    version.mois,
                    version.numero,
                    len(jours),
                    nb_moins,
                    nb_plus,
                )

            self.stdout.write(
                f"{etiquette} : marquee ({len(jours)} jours evalues, "
                f"{nb_moins} moins, {nb_plus} plus){ecart}"
            )
            marquees += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixe}{marquees} version(s) marquee(s), {ignorees} ignoree(s)."
            )
        )
