"""Formulaires du planning.

Brique 7a : `FormulaireImportHistorique` reçoit le fichier de reprise d'un
planning de 2026 (C7.1) et n'en juge que **l'enveloppe** — taille, extension,
encodage, JSON lisible. La structure (clés racine, mois, briques `{a, s, t, x}`)
et les verdicts sont l'affaire de `historique.analyser`, qui a besoin de la base
pour résoudre les codes.

Patron de `absences/forms.py:FormulaireImport` (3-quater, C3.9), même plafond.
"""

import json

from django import forms

from .historique import TAILLE_MAX_IMPORT


class FormulaireImportHistorique(forms.Form):
    """Dépôt du fichier d'un planning historique.

    Après validation, `cleaned_data["planning"]` porte l'objet JSON décodé, tel
    quel : c'est lui qui transite en session entre l'analyse et la confirmation,
    et c'est lui que `historique.analyser` relit au rejeu.
    """

    fichier = forms.FileField(
        label="Fichier JSON du planning (export de la page)",
        help_text="Format de l'export JSON de la page planning, 1 Mo au plus.",
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if fichier.size > TAILLE_MAX_IMPORT:
            raise forms.ValidationError("Fichier trop volumineux (maximum 1 Mo).")
        if not fichier.name.lower().endswith(".json"):
            raise forms.ValidationError("Le fichier doit porter l'extension .json.")
        octets = fichier.read()
        try:
            texte = octets.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("Le fichier doit être encodé en UTF-8.") from None
        try:
            self._planning = json.loads(texte)
        except ValueError:
            raise forms.ValidationError("JSON illisible.") from None
        return fichier

    def clean(self):
        donnees = super().clean()
        if "fichier" in donnees:
            donnees["planning"] = self._planning
        return donnees
