"""Limitation de débit par fenêtres fixes, comptées en base.

Pourquoi pas le cache Django : `DatabaseCache` n'implémente pas `incr` et
hérite de `BaseCache.incr`, qui fait un `get` puis un `set` en Python — sans
verrou ni transaction. Sous les deux workers gunicorn de production, les
incréments se perdent ; et le `set` rebâtit la durée de vie sur le `TIMEOUT` du
cache, si bien qu'une fenêtre de 15 minutes ne se referme jamais tant que le
trafic continue. Ici, l'incrément est un `UPDATE … SET nb = nb + 1` exécuté par
la base : deux processus ne peuvent pas se marcher dessus.

Aucune donnée personnelle n'est stockée : l'identifiant (adresse IP ou adresse
e-mail) n'entre en base que sous forme d'empreinte tronquée, et les logs ne
portent jamais que la portée.

Fenêtre FIXE : `debut = (maintenant // fenetre) * fenetre`. Deux appelants de
la même seconde tombent sur la même ligne ; au changement de fenêtre, une
nouvelle ligne repart à 1 et les anciennes sont purgées.
"""

import functools
import hashlib
import logging
import time

from django.conf import settings
from django.db import transaction
from django.db.models import F

from .models import CompteurDebit

logger = logging.getLogger(__name__)

# Nombre de fenêtres révolues conservées avant purge. Deux suffisent : la
# fenêtre courante et la précédente peuvent encore être écrites, au-delà rien
# ne relit jamais la ligne.
FENETRES_CONSERVEES = 2


def maintenant():
    """Horloge en secondes epoch. Isolée pour que les tests la bouchonnent."""
    return int(time.time())


def empreinte(texte):
    """Empreinte courte et stable d'un identifiant. Jamais réversible en base."""
    normalise = (texte or "").strip().casefold()
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()[:16]


def adresse_ip(request):
    """Adresse IP de l'appelant.

    Railway termine TLS devant l'application et ajoute son propre saut à
    `X-Forwarded-For`. Le DERNIER élément est celui écrit par le proxy de
    confiance : c'est le seul qu'un client ne peut pas fabriquer, les éléments
    de gauche étant sous son contrôle.
    """
    transmis = request.META.get("HTTP_X_FORWARDED_FOR", "")
    elements = [element.strip() for element in transmis.split(",") if element.strip()]
    if elements:
        return elements[-1]
    return request.META.get("REMOTE_ADDR") or "inconnue"


def reglage(nom, defaut):
    """Lit un réglage à l'appel, pour que la fixture `settings` des tests agisse."""
    return getattr(settings, nom, defaut)


def compter(portee, identifiant, fenetre_secondes):
    """Incrémente le compteur de la fenêtre courante et renvoie sa valeur.

    L'incrément passe par `F("nb") + 1` : c'est la base qui additionne, jamais
    Python. Deux workers concurrents ne peuvent donc pas perdre un appel.
    """
    cle = f"{portee}:{empreinte(identifiant)}"
    debut = (maintenant() // fenetre_secondes) * fenetre_secondes

    with transaction.atomic():
        compteur, cree = CompteurDebit.objects.get_or_create(
            cle=cle, fenetre_debut=debut, defaults={"nb": 1}
        )
        if not cree:
            CompteurDebit.objects.filter(pk=compteur.pk).update(nb=F("nb") + 1)
            compteur.refresh_from_db(fields=["nb"])

    CompteurDebit.objects.filter(
        cle__startswith=f"{portee}:",
        fenetre_debut__lt=debut - FENETRES_CONSERVEES * fenetre_secondes,
    ).delete()

    return compteur.nb


def depasse(portee, identifiant, reglage_debit):
    """Vrai si cet appel fait passer l'identifiant au-dessus du plafond."""
    max_appels, fenetre_secondes = reglage_debit
    return compter(portee, identifiant, fenetre_secondes) > max_appels


def limite_par_ip(portee, nom_reglage, reponse, defaut=(60, 60), methodes=("POST",)):
    """Décorateur : coupe la vue au-delà du plafond, par adresse IP.

    Le NOM du réglage est passé, pas sa valeur : il est relu à chaque appel, ce
    qui laisse la fixture `settings` des tests le surcharger. Seules les
    méthodes listées sont comptées — un GET ne consomme rien.
    """

    def decorateur(vue):
        @functools.wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if request.method in methodes and depasse(
                portee, adresse_ip(request), reglage(nom_reglage, defaut)
            ):
                # Jamais l'adresse : la portée suffit à comprendre le log.
                logger.warning("debit depasse : %s", portee)
                return reponse(request)
            return vue(request, *args, **kwargs)

        return enveloppe

    return decorateur
