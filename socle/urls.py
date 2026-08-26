"""URLs du socle : page de santé et accueil."""

from django.urls import path

from . import views

urlpatterns = [
    path("sante/", views.sante, name="sante"),
    path("", views.accueil, name="accueil"),
]
