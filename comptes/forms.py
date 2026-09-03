"""Formulaires de l'application comptes."""

from django import forms


class FormulaireAdresse(forms.Form):
    """Demande de changement de l'adresse de connexion."""

    email = forms.EmailField(
        label="Nouvelle adresse e-mail",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class FormulaireConnexion(forms.Form):
    """Demande d'un lien de connexion à partir d'une adresse e-mail."""

    email = forms.EmailField(
        label="Adresse e-mail",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "autofocus": True,
                "placeholder": "prenom.nom@exemple.fr",
            }
        ),
    )
