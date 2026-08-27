"""URLs de l'API entrante n8n, montées sous `/api/n8n/`.

`app_name` est indispensable : `socle` porte déjà une vue nommée `sante`, et
sans espace de noms `reverse("sante")` désignerait silencieusement l'une ou
l'autre.
"""

from django.urls import path

from . import views

app_name = "n8n"

urlpatterns = [
    path("sante/", views.sante, name="sante"),
    path("imports/", views.declencher_import, name="imports"),
]
