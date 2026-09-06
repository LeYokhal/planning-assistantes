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
    re_path(
        r"^api/planning/(?P<mois>\d{4}-\d{2})/versions/(?P<numero>\d+)/publier/$",
        views.api_publier,
        name="publier",
    ),
    path("api/erreurs/", views.api_erreurs, name="erreurs"),
    # Brique 4b : « Mes jours », l'espace de la salariée sur le planning publié.
    path("mes-jours/", views.mes_jours_courant, name="mes_jours_courant"),
    re_path(r"^mes-jours/(?P<mois>\d{4}-\d{2})/$", views.mes_jours, name="mes_jours"),
]
