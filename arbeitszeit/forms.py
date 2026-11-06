
from django import forms

from .models import ArbeitszeitEintrag


class ArbeitszeitEintragForm(forms.ModelForm):

    class Meta:
        model = ArbeitszeitEintrag

        fields = [
            "datum",
            "startzeit",
            "endzeit",
            "notizen",
        ]

        labels = {
            "datum": "Datum",
            "startzeit": "Arbeitsbeginn",
            "endzeit": "Arbeitsende",
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
