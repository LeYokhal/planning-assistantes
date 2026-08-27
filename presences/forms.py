"""Formulaire d'import d'un fichier S7."""

from django import forms

# Le plus gros payload observé (31 jours, 8 agendas) pèse environ 250 Ko : 5 Mo
# laissent une marge confortable sans exposer la lecture à un fichier énorme.
TAILLE_MAX = 5 * 1024 * 1024


class FormulaireImportFichier(forms.Form):
    """Dépôt d'un payload `consulter_jours_travail` enregistré tel quel."""

    fichier = forms.FileField(
        label="Fichier JSON S7 (consulter_jours_travail, mode « tous »)"
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if fichier.size > TAILLE_MAX:
            raise forms.ValidationError("Fichier trop volumineux (maximum 5 Mo).")
        if not fichier.name.lower().endswith(".json"):
            raise forms.ValidationError("Le fichier doit porter l'extension .json.")
        return fichier
