"""URLs des absences.

`app_name` est indispensable : `presences` et `personnes` portent déjà des vues
nommées de façon voisine, et sans espace de noms un `reverse()` désignerait
silencieusement l'une ou l'autre (leçon de la brique 1b).
"""

from django.urls import path

from . import views

app_name = "absences"

urlpatterns = [
    path("mes-absences/", views.mes_absences, name="mes_absences"),
    path("mes-absences/nouvelle/", views.nouvelle_absence, name="nouvelle"),
    path(
        "mes-absences/<int:identifiant>/annuler/",
        views.annuler_absence,
        name="annuler",
    ),
    path("absences/", views.absences_a_decider, name="decider"),
    path(
        "absences/<int:identifiant>/decider/",
        views.decider_absence,
        name="decider_une",
    ),
    path(
        "absences/<int:identifiant>/corriger/",
        views.corriger_absence,
        name="corriger",
    ),
]
