"""Formulaires des absences.

Brique 3-quater : `FormulaireImport` reçoit le fichier de reprise de l'existant
Notion (C3.9) et n'en juge que la forme ; les verdicts sont rendus par
`services.analyser_import`.
"""

import hashlib
import json

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


# --- Brique 3-quater : fichier de reprise de l'existant Notion (C3.9) --------

# ~200 absences tiennent en moins de 200 Ko : 1 Mo laisse une marge large.
# Assumé (Q4) : Django garde un téléversement en mémoire jusqu'à 2,5 Mo
# (`FILE_UPLOAD_MAX_MEMORY_SIZE`) ; au-delà, il passe par un fichier temporaire
# avant que cette garde ne le refuse. Le fichier réel n'en approche pas.
TAILLE_MAX_IMPORT = 1024 * 1024
CHAMPS_ABSENCE = ("nom", "prenom", "type", "debut", "fin")
CHAMPS_FACULTATIFS = ("ref", "precision")


def _normaliser_absence(indice, brut):
    """Une ligne du fichier, réduite aux chaînes attendues et strippée.

    Ne juge aucune valeur : une date illisible ou un type inconnu sont des
    verdicts du rapport, pas des refus du fichier. `precision` n'est jamais
    reprise (§ 1 du plan). Les messages ne citent que des noms de champs et
    des numéros de ligne, jamais une valeur.
    """
    if not isinstance(brut, dict):
        raise forms.ValidationError(
            f"Ligne {indice} : chaque absence doit être un objet."
        )
    ligne = {}
    for champ in CHAMPS_ABSENCE:
        valeur = brut.get(champ)
        if not isinstance(valeur, str):
            raise forms.ValidationError(
                f"Ligne {indice} : champ « {champ} » manquant ou illisible."
            )
        ligne[champ] = valeur.strip()
    for champ in CHAMPS_FACULTATIFS:
        valeur = brut.get(champ, "")
        if valeur is not None and not isinstance(valeur, str):
            raise forms.ValidationError(
                f"Ligne {indice} : champ « {champ} » illisible."
            )
    ligne["ref"] = (brut.get("ref") or "").strip()
    return ligne


def lire_absences(donnees):
    """La liste `absences` normalisée d'un fichier décodé, ou une `ValidationError`."""
    if not isinstance(donnees, dict) or not isinstance(donnees.get("absences"), list):
        raise forms.ValidationError(
            "Le fichier doit être un objet portant une liste « absences »."
        )
    absences = [
        _normaliser_absence(indice, brut)
        for indice, brut in enumerate(donnees["absences"], start=1)
    ]
    if not absences:
        raise forms.ValidationError("La liste « absences » est vide.")
    return absences


class FormulaireImport(forms.Form):
    """Dépôt du fichier de reprise des absences (C3.9, § 1 du plan 3-quater).

    Sur le patron de `personnes/forms.py` : taille, extension, puis encodage
    UTF-8, JSON et FORME — un objet avec une liste `absences` d'objets portant
    `nom`, `prenom`, `type`, `debut`, `fin` (chaînes) et, facultatifs, `ref`
    et `precision`. Les verdicts sont l'affaire de `services.analyser_import`.

    Après validation, `cleaned_data` porte `absences` (lignes normalisées,
    valeurs natives JSON, prêtes pour la session) et `empreinte` (SHA-256 des
    octets reçus, qui lie la confirmation au fichier analysé).
    """

    fichier = forms.FileField(label="Fichier JSON des absences (reprise Notion)")

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
            raise forms.ValidationError(
                "Le fichier doit être encodé en UTF-8."
            ) from None
        try:
            donnees = json.loads(texte)
        except ValueError:
            raise forms.ValidationError("JSON illisible.") from None
        self._absences = lire_absences(donnees)
        self._empreinte = hashlib.sha256(octets).hexdigest()
        return fichier

    def clean(self):
        donnees = super().clean()
        if "fichier" in donnees:
            donnees["absences"] = self._absences
            donnees["empreinte"] = self._empreinte
        return donnees
