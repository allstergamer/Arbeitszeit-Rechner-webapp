
from django.conf import settings
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone


def standard_tages_soll():
    return {
        "0": 475,
        "1": 475,
        "2": 475,
        "3": 475,
        "4": 415,
        "5": 0,
        "6": 0,
    }


def standard_arbeitszeiten():
    werktag = {
        "flex": ["07:00", "17:00"],
        "kern": ["08:00", "15:00"],
        "regel": ["07:30", "16:15"],
    }

    return {
        "0": werktag,
        "1": werktag,
        "2": werktag,
        "3": werktag,
        "4": {
            "flex": ["07:00", "15:15"],
            "kern": ["08:00", "12:00"],
            "regel": ["07:30", "14:30"],
        },
    }


class BenutzerProfil(models.Model):
    THEMES = [
        ("Hell", "Hell"),
        ("Dunkel", "Dunkel"),
        ("System", "System"),
    ]

    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profil",
    )

    theme = models.CharField(
        max_length=10,
        choices=THEMES,
        default="System",
    )

    erstellt_am = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profil: {self.benutzer.username}"


class ArbeitszeitEinstellung(models.Model):
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arbeitszeit_einstellungen",
    )

    gueltig_ab = models.DateField()

    wochen_soll = models.PositiveIntegerField(default=2315)
    tages_soll = models.JSONField(default=standard_tages_soll)

    fruehstueckspause = models.PositiveIntegerField(default=20)
    mittagspause = models.PositiveIntegerField(default=30)

    zeiten = models.JSONField(default=standard_arbeitszeiten)

    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-gueltig_ab"]
        constraints = [
            UniqueConstraint(
                fields=["benutzer", "gueltig_ab"],
                name="einstellung_pro_benutzer_und_stichtag",
            )
        ]

    def __str__(self):
        return f"Einstellungen {self.benutzer.username} ab {self.gueltig_ab}"


class ArbeitszeitEintrag(models.Model):
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arbeitszeit_eintraege",
    )

    datum = models.DateField()
    startzeit = models.TimeField()
    endzeit = models.TimeField()

    fruehstueckspause = models.PositiveIntegerField(default=20)
    mittagspause = models.PositiveIntegerField(default=30)

    arbeitsminuten = models.IntegerField(default=0)
    sollminuten = models.IntegerField(default=0)
    differenzminuten = models.IntegerField(default=0)

    azv = models.BooleanField(default=False)
    notizen = models.TextField(blank=True)

    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-datum"]
        constraints = [
            UniqueConstraint(
                fields=["benutzer", "datum"],
                name="eintrag_pro_benutzer_und_tag",
            )
        ]

    def __str__(self):
        return f"{self.benutzer.username} – {self.datum}"


class AenderungsHistorie(models.Model):
    AKTIONEN = [
        ("erstellt", "Erstellt"),
        ("bearbeitet", "Bearbeitet"),
        ("geloescht", "Gelöscht"),
    ]

    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="aenderungshistorie",
    )

    # Bewusst keine ForeignKey-Beziehung:
    # Die Historie soll auch nach dem Löschen eines Eintrags bestehen bleiben.
    eintrag_id = models.PositiveIntegerField()

    aktion = models.CharField(max_length=20, choices=AKTIONEN)
    zeitpunkt = models.DateTimeField(default=timezone.now)

    # Vollständiger Datenstand zum Zeitpunkt der Änderung.
    daten_snapshot = models.JSONField()

    class Meta:
        ordering = ["-zeitpunkt"]

    def __str__(self):
        return f"{self.benutzer.username} – {self.aktion} – {self.zeitpunkt}"


class LiveErfassung(models.Model):
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="live_erfassung",
    )

    gestartet_am = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Live-Erfassung: {self.benutzer.username}"
