"""Client HTTP commun des webhooks n8n sortants.

Factorisation du patron partagé par `comptes/mails.py` (brique 1a) et
`presences/webhooks.py` (brique 1b), auxquels s'ajoute `absences/webhooks.py`
(brique 3) : le seuil de trois appelants annoncé dans le commentaire de tête de
`presences/webhooks.py` est atteint.

Ce module fait l'appel et RIEN d'autre. Il ne journalise pas : chaque appelant
garde son propre logger et ses propres messages, parce que la recette existante
les vérifie nommément (`caplog.at_level(..., logger="comptes.mails")`,
`logger="presences.webhooks"`). Ce qui est factorisé, c'est la garde
fail-closed, l'en-tête, le délai, la capture du réseau et le test du statut.

⚠️ L'URL est passée en argument POSITIONNEL à `requests.post`. La fixture
`Routeur` de `presences/tests/test_endpoint.py` aiguille sur `url` reçu en
positionnel : la passer en mot-clé casserait six tests de lot.

Aucune valeur sensible ne ressort d'ici : `Resultat.erreur` ne porte que le NOM
de la classe d'exception, jamais son message — celui de `requests` contient
l'URL appelée.
"""

from dataclasses import dataclass

import requests

DELAI_SECONDES = 10

MOTIF_OK = "ok"
MOTIF_NON_CONFIGURE = "non_configure"
MOTIF_RESEAU = "reseau"
MOTIF_STATUT = "statut"


@dataclass(frozen=True)
class Resultat:
    """Issue d'un appel. `ok` suffit à l'appelant qui ne journalise rien."""

    ok: bool
    motif: str
    statut: int = None
    erreur: str = ""

    def __bool__(self):
        return self.ok


def poster(url, en_tete_secret, secret, corps):
    """Poste `corps` en JSON vers `url`. Ne lève jamais, ne journalise jamais.

    Fail-closed : sans URL ou sans secret, aucun appel réseau n'est tenté et le
    résultat porte le motif `non_configure`.
    """
    if not url or not secret:
        return Resultat(False, MOTIF_NON_CONFIGURE)

    try:
        reponse = requests.post(
            url,
            json=corps,
            headers={
                en_tete_secret: secret,
                "Content-Type": "application/json",
            },
            timeout=DELAI_SECONDES,
        )
    except requests.RequestException as erreur:
        # Seul le TYPE de l'erreur remonte : son message porte l'URL.
        return Resultat(False, MOTIF_RESEAU, erreur=type(erreur).__name__)

    if reponse.status_code >= 400:
        return Resultat(False, MOTIF_STATUT, statut=reponse.status_code)

    return Resultat(True, MOTIF_OK, statut=reponse.status_code)
