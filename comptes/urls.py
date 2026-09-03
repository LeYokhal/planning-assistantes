"""URLs d'authentification et de profil.

`app_name` est posé en brique 3 : la vue `profil` est référencée par un
`{% url %}` depuis les gabarits des absences, et le projet compte désormais
assez de vues pour qu'un nom nu devienne ambigu.
"""

from django.urls import path

from . import views

app_name = "comptes"

urlpatterns = [
    path("connexion/", views.demander_lien, name="connexion"),
    path("connexion/lien/", views.VueConnexionLien.as_view(), name="connexion_lien"),
    path("deconnexion/", views.VueDeconnexion.as_view(), name="deconnexion"),
    path("mon-profil/", views.profil, name="profil"),
    path(
        "mon-profil/confirmer/<str:jeton>/",
        views.confirmer_adresse,
        name="confirmer_adresse",
    ),
]
