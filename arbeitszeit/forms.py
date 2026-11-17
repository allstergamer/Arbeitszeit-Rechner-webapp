
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import ArbeitszeitEintrag


class RegistrierungForm(UserCreationForm):
    first_name = forms.CharField(label="Vorname", max_length=150)
    last_name = forms.CharField(label="Nachname", max_length=150)

    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "last_name")


class ArbeitszeitEintragForm(forms.ModelForm):

    class Meta:
        model = ArbeitszeitEintrag

        fields = [
            "datum",
            "startzeit",
            "endzeit",
            "azv",
            "notizen",
        ]

        labels = {
            "datum": "Datum",
            "startzeit": "Arbeitsbeginn",
            "endzeit": "Arbeitsende",
            "azv": "AZV – Arbeitszeitverkürzung",
            "notizen": "Notizen",
        }

        widgets = {
            "datum": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "startzeit": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
            "endzeit": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
            "azv": forms.CheckboxInput(attrs={"class": "azv-checkbox"}),
            "notizen": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optionale Notizen zum Arbeitstag",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        startzeit = cleaned_data.get("startzeit")
        endzeit = cleaned_data.get("endzeit")

        if startzeit and endzeit and endzeit <= startzeit:
            self.add_error(
                "endzeit",
                "Die Arbeitsende-Zeit muss nach dem Arbeitsbeginn liegen."
            )

        return cleaned_data
