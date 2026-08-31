"""Formulaire d'import de la fiche personnel."""

from django import forms

# La fiche complète du cabinet tient en quelques dizaines de kilo-octets :
# 2 Mo laissent une marge large sans exposer la lecture à un fichier énorme.
TAILLE_MAX = 2 * 1024 * 1024


class FormulaireImportFiche(forms.Form):
    """Dépôt d'un export JSON de la fiche personnel Notion (5 colonnes)."""

    fichier = forms.FileField(label="Fichier JSON de la fiche personnel")

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if fichier.size > TAILLE_MAX:
            raise forms.ValidationError("Fichier trop volumineux (maximum 2 Mo).")
        if not fichier.name.lower().endswith(".json"):
            raise forms.ValidationError("Le fichier doit porter l'extension .json.")
        return fichier
