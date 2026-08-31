"""Table des URLs du projet.

L'ordre compte : les redirections /admin/login/ et /admin/logout/ doivent
précéder admin.site.urls pour l'emporter sur les vues natives de Django. Les
routes applicatives (socle, comptes, présences, personnes) et l'API n8n sont
toutes déclarées avant `admin/`.
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
    # /presences/, /presences/importer/, /presences/<AAAA-MM>/
    path("", include("presences.urls")),
    # /personnes/, /personnes/importer/, /personnes/appariement/
    path("", include("personnes.urls")),
    # API entrante n8n : /api/n8n/sante/, /api/n8n/imports/
    path("api/n8n/", include("n8n.urls")),
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
