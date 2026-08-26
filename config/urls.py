"""Table des URLs du projet.

L'ordre compte : les redirections /admin/login/ et /admin/logout/ doivent
précéder admin.site.urls pour l'emporter sur les vues natives de Django.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from comptes.views import VueDeconnexionAdmin

urlpatterns = [
    # /sante/ puis / (accueil)
    path("", include("socle.urls")),
    # /connexion/, /connexion/lien/, /deconnexion/
    path("", include("comptes.urls")),
    # L'administration n'a pas de connexion propre : tout passe par le lien magique.
    path(
        "admin/login/",
        RedirectView.as_view(url="/connexion/?next=/admin/", permanent=False),
        name="admin_login_redirige",
    ),
    path(
        "admin/logout/",
        VueDeconnexionAdmin.as_view(),
        name="admin_logout_redirige",
    ),
    path("admin/", admin.site.urls),
]
