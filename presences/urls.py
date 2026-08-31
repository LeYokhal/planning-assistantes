"""URLs des présences.

L'ordre compte : `/presences/importer/` doit précéder le motif `<AAAA-MM>`,
sinon « importer » serait candidat au mois.
"""

from django.urls import path, re_path

from . import views

app_name = "presences"

urlpatterns = [
    path("presences/", views.presences_courant, name="courant"),
    path("presences/importer/", views.importer_fichier, name="importer"),
    re_path(r"^presences/(?P<mois>\d{4}-\d{2})/$", views.presences_mois, name="mois"),
]
