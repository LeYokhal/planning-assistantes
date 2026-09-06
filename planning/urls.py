"""URLs du planning.

`app_name` est indispensable : `presences` porte déjà une vue nommée `mois`
et une vue nommée `courant`. Motif « AAAA-MM » et slash final : patron de
`presences/urls.py`.
"""

from django.urls import path, re_path

from . import views

app_name = "planning"

urlpatterns = [
    path("planning/", views.planning_courant, name="courant"),
    re_path(r"^planning/(?P<mois>\d{4}-\d{2})/$", views.planning_mois, name="mois"),
    re_path(r"^planning/(?P<mois>\d{4}-\d{2})/copie/$", views.copie, name="copie"),
    re_path(
        r"^api/planning/(?P<mois>\d{4}-\d{2})/versions/$",
        views.api_versions,
        name="versions",
    ),
    path("api/erreurs/", views.api_erreurs, name="erreurs"),
]
