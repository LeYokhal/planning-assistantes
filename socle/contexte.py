"""Processeur de contexte de la coquille (brique 6a) : `nav_courante`, `initiales`, `prenom`.

Tolère une requête sans `user` (RequestFactory), un utilisateur anonyme (page
de connexion, 403 / 404 anonymes) et une requête sans `resolver_match` (URL
inconnue). `initiales` et `prenom` sont paresseux : `user.personne` n'est lu
que si un gabarit les rend — la page planning et l'administration, qui ne
rendent pas la barre, ne paient aucune requête.
"""

from django.utils.functional import SimpleLazyObject

# Routes de l'espace personnel, dans les apps qui portent aussi les écrans de
# gestion (`absences/urls.py`, `planning/urls.py`).
ROUTES_MES_ABSENCES = {"mes_absences", "nouvelle", "annuler"}
ROUTES_MES_JOURS = {"mes_jours", "mes_jours_courant"}


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
