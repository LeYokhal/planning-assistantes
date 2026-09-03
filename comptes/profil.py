"""Changement de l'adresse de connexion par la salariée (décision L).

Le jeton est un jeton signé `django.core.signing`, pas un jeton sesame : il doit
transporter une charge utile (l'identifiant du compte et l'adresse demandée),
ce que sesame ne fait pas. Il est horodaté, donc périmable, et rendu à usage
unique par le vidage de `Compte.email_en_attente` à la confirmation.

Deux propriétés tenues à la main :

* **réponse neutre** — que l'adresse soit libre ou déjà prise par un autre
  compte, la page répond exactement la même chose et aucun mail ne part dans le
  second cas. C'est la doctrine de `/connexion/`, déclinée ici : sans elle, le
  formulaire deviendrait un oracle d'existence de comptes ;
* **`Personne.email_contact` suit** l'adresse de connexion, sinon la prochaine
  invitation repartirait sur l'ancienne.
"""

import logging

from django.core import signing

logger = logging.getLogger(__name__)

SEL = "comptes.changement-adresse"
DUREE_SECONDES = 3600


def fabriquer_jeton(compte, nouvelle_adresse):
    """Jeton signé portant l'identifiant du compte et l'adresse demandée."""
    return signing.dumps(
        {"compte": compte.pk, "email": nouvelle_adresse}, salt=SEL
    )


def lire_jeton(jeton):
    """Renvoie `(identifiant, adresse)`, ou `(None, "")` si le jeton est refusé.

    Un jeton illisible, falsifié ou périmé donne le même résultat : rien ne
    distingue les trois cas côté appelant.
    """
    try:
        charge = signing.loads(jeton, salt=SEL, max_age=DUREE_SECONDES)
    except signing.BadSignature:
        return None, ""
    if not isinstance(charge, dict):
        return None, ""
    identifiant = charge.get("compte")
    adresse = charge.get("email")
    if not isinstance(identifiant, int) or not isinstance(adresse, str) or not adresse:
        return None, ""
    return identifiant, adresse
