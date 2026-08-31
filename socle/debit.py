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


# En-têtes où un proxy place parfois l'IP cliente, à confronter au relevé.
EN_TETES_CANDIDATS = (
    "HTTP_X_REAL_IP",
    "HTTP_X_ENVOY_EXTERNAL_ADDRESS",
    "HTTP_FASTLY_CLIENT_IP",
    "HTTP_CF_CONNECTING_IP",
)

# Plages « privées » au sens du relevé : RFC 1918, boucle locale, lien-local,
# unique-local IPv6. On n'utilise PAS `ipaddress.is_private`, dont l'appartenance
# a changé selon les versions de Python (les plages de documentation RFC 5737 /
# RFC 3849 y sont entrées depuis 3.12) : ici une adresse de documentation tient
# lieu de vraie IP cliente publique et doit rester « publique ».
RESEAUX_PRIVES = tuple(
    ipaddress.ip_network(reseau)
    for reseau in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
        "169.254.0.0/16", "::1/128", "fe80::/10", "fc00::/7",
    )
)

_topologie_relevee = False
_avertissement_emis = False


def _classe(texte):
    """« interne », « privee », « publique » ou « illisible » — jamais la valeur."""
    try:
        adresse = ipaddress.ip_address(texte)
    except ValueError:
        return "illisible"
    if adresse in ipaddress.ip_network("100.0.0.0/8"):
        return "interne"
    if any(adresse in reseau for reseau in RESEAUX_PRIVES):
        return "privee"
    return "publique"


def relever_topologie(request):
    """Journalise UNE fois par processus la forme des en-têtes proxy, sans valeur.

    Sert à établir où voyage l'IP cliente derrière Railway (recette 2-bis : ni le
    dernier ni le premier élément public de X-Forwarded-For ne l'étaient).
    """
    global _topologie_relevee
    if _topologie_relevee:
        return
    _topologie_relevee = True
    xff = [
        e.strip()
        for e in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if e.strip()
    ]
    classes_xff = [_classe(e) for e in xff]
    autres = " ".join(
        f"{nom[5:].lower()}="
        f"{_classe(request.META[nom]) if nom in request.META else 'absent'}"
        for nom in EN_TETES_CANDIDATS
    )
    remote = _classe(request.META.get("REMOTE_ADDR", ""))
    logger.info(
        "topologie proxy : x_forwarded_for=%s %s remote_addr=%s",
        classes_xff,
        autres,
        remote,
    )


def adresse_ip(request):
    """Adresse IP publique de l'appelant, derrière le proxy Railway.

    Mesuré en production (brique 2-ter, 31/08/2026) : Railway réécrit
    `X-Real-IP` et `X-Forwarded-For` — une sonde injectant des valeurs
    illisibles dans les deux en-têtes ressort classée « publique » partout.
    `X-Real-IP` porte donc l'IP cliente, imposée par l'infrastructure ; c'est
    la seule source utilisée. `X-Forwarded-For` vaut [client, edge] : son
    dernier élément est un nœud d'entrée partagé (deux valeurs observées),
    jamais un identifiant individuel — ne pas y revenir.
    En local (runserver, sans proxy), l'en-tête est absent : REMOTE_ADDR.
    """
    relever_topologie(request)
    reel = request.META.get("HTTP_X_REAL_IP", "").strip()
    if reel and _classe(reel) != "illisible":
        return reel
    global _avertissement_emis
    if not _avertissement_emis and request.META.get("HTTP_X_FORWARDED_FOR"):
        _avertissement_emis = True
        logger.warning(
            "adresse_ip : X-Real-IP absent ou illisible derriere un proxy, "
            "repli sur REMOTE_ADDR"
        )
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
