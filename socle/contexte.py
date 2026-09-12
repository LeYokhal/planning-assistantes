"""Processeur de contexte de la coquille (brique 6a) : `nav_courante`, `initiales`, `prenom` ;
brique 8 (D8.5) : `nav_urls`, les onglets de gestion qui suivent le mois de la page.

Tolère une requête sans `user` (RequestFactory), un utilisateur anonyme (page
de connexion, 403 / 404 anonymes) et une requête sans `resolver_match` (URL
inconnue). `initiales` et `prenom` sont paresseux : `user.personne` n'est lu
que si un gabarit les rend — la page planning rend la barre depuis la brique 6d
(test d'isolement `socle/tests/test_navigation.py`) ; `nav_urls` se calcule
par `reverse`, sans requête.
"""

import re

from django.urls import reverse
from django.utils.functional import SimpleLazyObject

# Routes de l'espace personnel, dans les apps qui portent aussi les écrans de
# gestion (`absences/urls.py`, `planning/urls.py`).
ROUTES_MES_ABSENCES = {"mes_absences", "nouvelle", "annuler"}
ROUTES_MES_JOURS = {"mes_jours", "mes_jours_courant"}

# Brique 8 (D8.5) : le mois d'une page, « AAAA-MM », lu dans l'URL résolue
# (`/planning/<mois>/`, `/presences/<mois>/`) ou dans `?mois=` (`/absences/`).
MOIS = re.compile(r"\d{4}-\d{2}")


def _mois_de(request):
    """Le mois porté par la page, ou `None` (absent, ou pas de la forme « AAAA-MM »)."""
    match = getattr(request, "resolver_match", None)
    brut = (match.kwargs.get("mois") if match else None) or request.GET.get("mois")
    return brut if brut and MOIS.fullmatch(brut) else None


def _nav_urls(mois):
    """Les trois onglets de gestion : sur le mois de la page s'il y en a un, sinon le mois courant."""
    if mois:
        return {
            "planning": reverse("planning:mois", kwargs={"mois": mois}),
            "absences": reverse("absences:decider") + f"?mois={mois}",
            "presences": reverse("presences:mois", kwargs={"mois": mois}),
        }
    return {
        "planning": reverse("planning:courant"),
        "absences": reverse("absences:decider"),
        "presences": reverse("presences:courant"),
    }


def _nav_courante(resolution):
    """L'entrée de navigation à marquer courante, ou `""`."""
    if resolution is None:
        return ""
    app, nom = resolution.app_name, resolution.url_name
    if app == "planning":
        return "mes_jours" if nom in ROUTES_MES_JOURS else "planning"
    if app == "absences":
        return "mes_absences" if nom in ROUTES_MES_ABSENCES else "absences"
    if app in ("presences", "personnes"):
        return "donnees"
    if app == "comptes" and nom == "profil":
        return "profil"
    if app == "" and nom == "accueil":
        return "tableau_de_bord"
    return ""


def coquille(request):
    """Contexte de `socle/base.html` ; vide et sans requête pour un anonyme."""
    contexte = {
        "nav_courante": _nav_courante(getattr(request, "resolver_match", None)),
        "nav_urls": _nav_urls(_mois_de(request)),
        "initiales": "",
        "prenom": "",
    }
    utilisateur = getattr(request, "user", None)
    if utilisateur is None or not utilisateur.is_authenticated:
        return contexte

    def personne():
        # Une requête si `personne_id` est posé, aucune sinon ; Django met la
        # relation en cache sur l'instance : `prenom` et `initiales` la partagent.
        return utilisateur.personne

    def prenom():
        fiche = personne()
        return fiche.prenom if fiche else ""

    def initiales():
        fiche = personne()
        if fiche:
            return (fiche.prenom[:1] + fiche.nom[:1]).upper()
        return utilisateur.get_role_display()[:1].upper()

    contexte["prenom"] = SimpleLazyObject(prenom)
    contexte["initiales"] = SimpleLazyObject(initiales)
    return contexte
