"""URLs d'authentification."""

from django.urls import path

from . import views

urlpatterns = [
    path("connexion/", views.demander_lien, name="connexion"),
    path("connexion/lien/", views.VueConnexionLien.as_view(), name="connexion_lien"),
    path("deconnexion/", views.VueDeconnexion.as_view(), name="deconnexion"),
]
