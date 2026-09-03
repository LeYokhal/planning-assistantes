"""Formulaires des absences."""

from django import forms

from .models import TypeAbsence


class FormulaireAbsence(forms.Form):
    """Saisie d'une absence par la salariée."""

    type = forms.ModelChoiceField(
        label="Motif",
        queryset=TypeAbsence.objects.none(),
        empty_label="— choisir —",
    )
    date_debut = forms.DateField(
        label="Premier jour",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_fin = forms.DateField(
        label="Dernier jour",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    precision = forms.CharField(
        label="Précision (facultatif)",
        max_length=120,
        required=False,
        help_text="Visible du cabinet seulement. N'entre ni dans le journal ni dans un mail.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Requête posée à l'instanciation : la liste des types vit en base et
        # peut changer entre deux imports du module.
        self.fields["type"].queryset = TypeAbsence.objects.filter(actif=True)

    def clean(self):
        donnees = super().clean()
        debut = donnees.get("date_debut")
        fin = donnees.get("date_fin")
        if debut and fin and fin < debut:
            raise forms.ValidationError(
                "Le dernier jour ne peut pas précéder le premier."
            )
        return donnees


class FormulaireCorrection(forms.Form):
    """Correction des jours comptés par la validatrice."""

    jours_comptes = forms.DecimalField(
        label="Jours comptés",
        max_digits=4,
        decimal_places=1,
        min_value=0,
    )
