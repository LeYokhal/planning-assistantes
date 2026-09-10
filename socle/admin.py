"""Habillage de l'administration (brique 6a, C6.4) : titres et barre latérale.

Aucun modèle du socle n'est enregistré. Les gabarits `admin/base_site.html` et
`admin/index.html` de `socle/templates/` complètent ces attributs — l'app
`socle` précède `django.contrib.admin` dans INSTALLED_APPS pour qu'ils soient
trouvés avant ceux de Django.
"""

from django.contrib import admin

admin.site.site_header = "Espace K Dentaire · Administration"
admin.site.site_title = "Administration · Espace K Dentaire"
admin.site.index_title = "Administration"
# La barre latérale native dupliquait l'index ; l'index en blocs la remplace.
admin.site.enable_nav_sidebar = False
