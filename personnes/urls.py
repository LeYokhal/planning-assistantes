"""URLs des personnes.

`app_name` est indispensable : `presences` porte déjà une vue nommée
`importer`, et sans espace de noms `reverse("importer")` désignerait
silencieusement l'une ou l'autre.
"""

from django.urls import path

from . import views

app_name = "personnes"

urlpatterns = [
    path("personnes/", views.personnes_liste, name="liste"),
    path("personnes/importer/", views.importer_fiche, name="importer"),
    path("personnes/appariement/", views.appariement, name="appariement"),
]
