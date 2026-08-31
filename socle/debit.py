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
import ipaddress
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


# Réseaux d'où ne vient jamais un client : sauts internes Railway (100.0.0.0/8,
# réponse officielle de Railway), plages privées et boucle locale, IPv4 et IPv6.
RESEAUX_INTERNES = tuple(
    ipaddress.ip_network(reseau)
    for reseau in (
        "100.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
        "fc00::/7", "fe80::/10", "::1/128",
    )
)


def _interne(texte):
    """Vrai pour un saut à ignorer : adresse interne, privée, locale, ou illisible."""
    try:
        adresse = ipaddress.ip_address(texte)
    except ValueError:
        return True
    return any(adresse in reseau for reseau in RESEAUX_INTERNES)


def adresse_ip(request):
    """Adresse IP publique de l'appelant, derrière le proxy Railway.

    Railway supprime l'en-tête `X-Forwarded-For` du client et le reconstruit :
    l'IP cliente d'abord, puis un ou plusieurs sauts internes en 100.0.0.0/8.
    On parcourt donc l'en-tête de droite à gauche en sautant les adresses
    internes ou privées : la première adresse publique est le client. La règle
    reste juste si le proxy AJOUTE à un en-tête fourni par le client (chaîne
    « usurpé, client, saut ») : le client réel précède toujours les sauts.
    Recette de la brique 2 : lire le dernier élément prenait un saut interne,
    partagé par tous les visiteurs — le plafond n'était plus individuel.
    """
    transmis = request.META.get("HTTP_X_FORWARDED_FOR", "")
    for element in reversed([e.strip() for e in transmis.split(",") if e.strip()]):
        if not _interne(element):
            return element
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
