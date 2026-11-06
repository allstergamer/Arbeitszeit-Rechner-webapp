from datetime import date, datetime, time, timedelta
import calendar

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ArbeitszeitEintragForm
from .models import (
    AenderungsHistorie,
    ArbeitszeitEintrag,
    ArbeitszeitEinstellung,
    BenutzerProfil,
    LiveErfassung,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

WOCHEN_TAGE = [
    ("0", "Montag"),
    ("1", "Dienstag"),
    ("2", "Mittwoch"),
    ("3", "Donnerstag"),
    ("4", "Freitag"),
    ("5", "Samstag"),
    ("6", "Sonntag"),
]

ARBEITSZEIT_MODELLE = [
    ("flex", "Gleitzeit"),
    ("kern", "Kernzeit"),
    ("regel", "Regelarbeitszeit"),
]


def minuten_formatieren(minuten):
    minuten = int(minuten or 0)
    stunden, rest = divmod(abs(minuten), 60)
    vorzeichen = "-" if minuten < 0 else ""
    return f"{vorzeichen}{stunden}:{rest:02d} h"


def einstellung_fuer_datum(benutzer, datum):
    return (
        ArbeitszeitEinstellung.objects.filter(
            benutzer=benutzer,
            gueltig_ab__lte=datum,
        )
        .order_by("-gueltig_ab")
        .first()
    )


def snapshot_fuer_eintrag(eintrag):
    return {
        "datum": str(eintrag.datum),
        "startzeit": eintrag.startzeit.strftime("%H:%M"),
        "endzeit": eintrag.endzeit.strftime("%H:%M"),
        "fruehstueckspause": eintrag.fruehstueckspause,
        "mittagspause": eintrag.mittagspause,
        "arbeitsminuten": eintrag.arbeitsminuten,
        "sollminuten": eintrag.sollminuten,
        "differenzminuten": eintrag.differenzminuten,
        "azv": eintrag.azv,
        "notizen": eintrag.notizen,
    }


def arbeitszeit_berechnen(datum, startzeit, endzeit, fruehstueck, mittag):
    start = datetime.combine(datum, startzeit)
    ende = datetime.combine(datum, endzeit)
    anwesenheitsminuten = int((ende - start).total_seconds() // 60)
    pausenminuten = int(fruehstueck) + int(mittag)

    if anwesenheitsminuten <= 0:
        raise ValueError("Das Arbeitsende muss nach dem Arbeitsbeginn liegen.")

    if pausenminuten >= anwesenheitsminuten:
        raise ValueError(
            "Die Gesamtpause muss kürzer als die Anwesenheitszeit sein."
        )

    return anwesenheitsminuten - pausenminuten


def eintrag_speichern_mit_historie(eintrag, aktion):
    """Speichert Eintrag und Historieneintrag atomar."""
    with transaction.atomic():
        eintrag.save()
        AenderungsHistorie.objects.create(
            benutzer=eintrag.benutzer,
            eintrag_id=eintrag.pk,
            aktion=aktion,
            daten_snapshot=snapshot_fuer_eintrag(eintrag),
        )


# ---------------------------------------------------------------------------
# Formulare für Einstellungen und Profil
# ---------------------------------------------------------------------------

class ArbeitszeitEinstellungForm(forms.Form):
    gueltig_ab = forms.DateField(
        label="Gültig ab",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )
    wochen_soll = forms.IntegerField(
        label="Wochensoll (Minuten)",
        min_value=0,
        initial=2315,
    )
    fruehstueckspause = forms.IntegerField(
        label="Frühstückspause (Minuten)",
        min_value=0,
        initial=20,
    )
    mittagspause = forms.IntegerField(
        label="Mittagspause (Minuten)",
        min_value=0,
        initial=30,
    )

    def __init__(self, *args, einstellung=None, **kwargs):
        self.einstellung = einstellung
        initial = kwargs.setdefault("initial", {})

        if einstellung:
            initial.setdefault("gueltig_ab", timezone.localdate())
            initial.setdefault("wochen_soll", einstellung.wochen_soll)
            initial.setdefault("fruehstueckspause", einstellung.fruehstueckspause)
            initial.setdefault("mittagspause", einstellung.mittagspause)
        else:
            initial.setdefault("gueltig_ab", timezone.localdate())
        super().__init__(*args, **kwargs)


class TagesSollForm(forms.Form):
    pass


for tag_key, tag_name in WOCHEN_TAGE:
    TagesSollForm.base_fields[f"tag_{tag_key}"] = forms.IntegerField(
        label=f"{tag_name} – Soll (Minuten)",
        min_value=0,
        required=True,
    )


class ArbeitszeitenForm(forms.Form):
    pass


for tag_key, tag_name in WOCHEN_TAGE[:5]:

    # Zuerst alle Beginn-Felder
    for modell_key, modell_name in ARBEITSZEIT_MODELLE:
        ArbeitszeitenForm.base_fields[f"{tag_key}_{modell_key}_start"] = forms.TimeField(
            label=f"{tag_name} – {modell_name}: Beginn",
            required=False,
            widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            input_formats=["%H:%M"],
        )

    # Danach alle Ende-Felder
    for modell_key, modell_name in ARBEITSZEIT_MODELLE:
        ArbeitszeitenForm.base_fields[f"{tag_key}_{modell_key}_ende"] = forms.TimeField(
            label=f"{tag_name} – {modell_name}: Ende",
            required=False,
            widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            input_formats=["%H:%M"],
        )


class BenutzerProfilForm(forms.ModelForm):
    class Meta:
        model = BenutzerProfil
        fields = ["theme"]
        labels = {"theme": "Darstellung"}
        widgets = {
            "theme": forms.Select(),
        }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    heute = timezone.localdate()
    wochenbeginn = heute - timedelta(days=heute.weekday())
    wochenende = wochenbeginn + timedelta(days=7)
    monatsbeginn = heute.replace(day=1)

    eintraege = ArbeitszeitEintrag.objects.filter(benutzer=request.user)
    heutiger_eintrag = eintraege.filter(datum=heute).first()
    wochen_eintraege = eintraege.filter(
        datum__gte=wochenbeginn,
        datum__lt=wochenende,
    )
    monats_eintraege = eintraege.filter(
        datum__gte=monatsbeginn,
        datum__lte=heute,
    )

    wochen_ist = wochen_eintraege.aggregate(
        summe=Sum("arbeitsminuten")
    )["summe"] or 0
    monats_ist = monats_eintraege.aggregate(
        summe=Sum("arbeitsminuten")
    )["summe"] or 0
    zeitkonto = eintraege.aggregate(
        summe=Sum("differenzminuten")
    )["summe"] or 0

    einstellung = einstellung_fuer_datum(request.user, heute)
    wochen_soll = einstellung.wochen_soll if einstellung else 2315
    live_erfassung = LiveErfassung.objects.filter(benutzer=request.user).first()

    context = {
        "heute": heute,
        "heute_ist": minuten_formatieren(
            heutiger_eintrag.arbeitsminuten if heutiger_eintrag else 0
        ),
        "wochen_ist": minuten_formatieren(wochen_ist),
        "wochen_soll": minuten_formatieren(wochen_soll),
        "zeitkonto": minuten_formatieren(zeitkonto),
        "monats_ist": minuten_formatieren(monats_ist),
        "letzte_eintraege": eintraege.order_by("-datum")[:5],
        "live_erfassung": live_erfassung,
        "live_seit": (
            timezone.localtime(live_erfassung.gestartet_am).strftime("%d.%m.%Y %H:%M")
            if live_erfassung else None
        ),
    }
    return render(request, "arbeitszeit/dashboard.html", context)


# ---------------------------------------------------------------------------
# Arbeitszeiteinträge
# ---------------------------------------------------------------------------

@login_required
def eintrag_erfassen(request):
    form = ArbeitszeitEintragForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        datum = form.cleaned_data["datum"]
        einstellung = einstellung_fuer_datum(request.user, datum)

        if einstellung is None:
            form.add_error(
                None,
                "Für dieses Datum existieren keine gültigen Arbeitseinstellungen.",
            )
        else:
            try:
                arbeitsminuten = arbeitszeit_berechnen(
                    datum,
                    form.cleaned_data["startzeit"],
                    form.cleaned_data["endzeit"],
                    einstellung.fruehstueckspause,
                    einstellung.mittagspause,
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                eintrag = form.save(commit=False)
                eintrag.benutzer = request.user
                eintrag.fruehstueckspause = einstellung.fruehstueckspause
                eintrag.mittagspause = einstellung.mittagspause
                eintrag.arbeitsminuten = arbeitsminuten
                eintrag.sollminuten = einstellung.tages_soll.get(
                    str(datum.weekday()), 0
                )
                eintrag.differenzminuten = (
                    eintrag.arbeitsminuten - eintrag.sollminuten
                )

                try:
                    eintrag_speichern_mit_historie(eintrag, "erstellt")
                except IntegrityError:
                    form.add_error(
                        None,
                        "Für diesen Tag existiert bereits ein Eintrag.",
                    )
                else:
                    messages.success(request, "Arbeitszeiteintrag wurde gespeichert.")
                    return redirect("eintraege")

    return render(
        request,
        "arbeitszeit/eintrag_erfassen.html",
        {"form": form, "bearbeiten": False},
    )


@login_required
def eintraege(request):
    queryset = ArbeitszeitEintrag.objects.filter(benutzer=request.user)

    filter_von = request.GET.get("von", "")
    filter_bis = request.GET.get("bis", "")

    if filter_von:
        try:
            queryset = queryset.filter(datum__gte=date.fromisoformat(filter_von))
        except ValueError:
            filter_von = ""

    if filter_bis:
        try:
            queryset = queryset.filter(datum__lte=date.fromisoformat(filter_bis))
        except ValueError:
            filter_bis = ""

    return render(
        request,
        "arbeitszeit/eintraege.html",
        {
            "eintraege": queryset.order_by("-datum"),
            "filter_von": filter_von,
            "filter_bis": filter_bis,
        },
    )


@login_required
def eintrag_bearbeiten(request, eintrag_id):
    eintrag = get_object_or_404(
        ArbeitszeitEintrag,
        pk=eintrag_id,
        benutzer=request.user,
    )
    ursprungsdatum = eintrag.datum

    if request.method == "POST":
        form = ArbeitszeitEintragForm(request.POST, instance=eintrag)

        if form.is_valid():
            datum = form.cleaned_data["datum"]

            # Bei unverändertem Datum gelten die im Eintrag gespeicherten
            # historischen Pausen- und Sollwerte weiter.
            if datum == ursprungsdatum:
                fruehstueck = eintrag.fruehstueckspause
                mittag = eintrag.mittagspause
                sollminuten = eintrag.sollminuten
            else:
                einstellung = einstellung_fuer_datum(request.user, datum)
                if einstellung is None:
                    form.add_error(
                        None,
                        "Für dieses Datum existieren keine gültigen Einstellungen.",
                    )
                    return render(
                        request,
                        "arbeitszeit/eintrag_erfassen.html",
                        {"form": form, "bearbeiten": True},
                    )
                fruehstueck = einstellung.fruehstueckspause
                mittag = einstellung.mittagspause
                sollminuten = einstellung.tages_soll.get(str(datum.weekday()), 0)

            try:
                arbeitsminuten = arbeitszeit_berechnen(
                    datum,
                    form.cleaned_data["startzeit"],
                    form.cleaned_data["endzeit"],
                    fruehstueck,
                    mittag,
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                aktualisiert = form.save(commit=False)
                aktualisiert.fruehstueckspause = fruehstueck
                aktualisiert.mittagspause = mittag
                aktualisiert.arbeitsminuten = arbeitsminuten
                aktualisiert.sollminuten = sollminuten
                aktualisiert.differenzminuten = arbeitsminuten - sollminuten

                try:
                    eintrag_speichern_mit_historie(aktualisiert, "bearbeitet")
                except IntegrityError:
                    form.add_error(
                        None,
                        "Für dieses Datum existiert bereits ein anderer Eintrag.",
                    )
                else:
                    messages.success(
                        request,
                        "Arbeitszeiteintrag wurde aktualisiert.",
                    )
                    return redirect("eintraege")
    else:
        form = ArbeitszeitEintragForm(instance=eintrag)

    return render(
        request,
        "arbeitszeit/eintrag_erfassen.html",
        {"form": form, "bearbeiten": True},
    )


@login_required
def eintrag_loeschen(request, eintrag_id):
    if request.method != "POST":
        return redirect("eintraege")

    eintrag = get_object_or_404(
        ArbeitszeitEintrag,
        pk=eintrag_id,
        benutzer=request.user,
    )

    with transaction.atomic():
        AenderungsHistorie.objects.create(
            benutzer=request.user,
            eintrag_id=eintrag.pk,
            aktion="geloescht",
            daten_snapshot=snapshot_fuer_eintrag(eintrag),
        )
        eintrag.delete()

    messages.success(request, "Arbeitszeiteintrag wurde gelöscht.")
    return redirect("eintraege")


# ---------------------------------------------------------------------------
# Auswertungen und PDF
# ---------------------------------------------------------------------------

def _auswertungszeitraum(request):
    heute = timezone.localdate()

    zeitraum = request.GET.get("zeitraum", "monat")
    if zeitraum not in ("woche", "monat", "jahr"):
        zeitraum = "monat"

    try:
        jahr = int(request.GET.get("jahr", heute.year))
    except (TypeError, ValueError):
        jahr = heute.year

    jahr = max(2000, min(jahr, 2100))

    if zeitraum == "woche":
        standard_nummer = heute.isocalendar().week
    elif zeitraum == "monat":
        standard_nummer = heute.month
    else:
        standard_nummer = 1

    try:
        nummer = int(request.GET.get("nummer", standard_nummer))
    except (TypeError, ValueError):
        nummer = standard_nummer

    if zeitraum == "woche":
        max_week = date(jahr, 12, 28).isocalendar().week
        nummer = max(1, min(nummer, max_week))

        start = date.fromisocalendar(jahr, nummer, 1)
        ende = start + timedelta(days=7)

    elif zeitraum == "monat":
        nummer = max(1, min(nummer, 12))

        start = date(jahr, nummer, 1)
        letzter_tag = calendar.monthrange(jahr, nummer)[1]
        ende = date(jahr, nummer, letzter_tag) + timedelta(days=1)

    else:
        nummer = 1
        start = date(jahr, 1, 1)
        ende = date(jahr + 1, 1, 1)

    return zeitraum, jahr, nummer, start, ende


@login_required
def auswertungen(request):
    heute = timezone.localdate()

    ansicht = request.GET.get("ansicht", "monat")

    if ansicht not in ("monat", "woche"):
        ansicht = "monat"

    alle_eintraege = ArbeitszeitEintrag.objects.filter(
        benutzer=request.user
    ).order_by("-datum")

    gruppen = {}

    for eintrag in alle_eintraege:
        if ansicht == "monat":
            schluessel = (
                eintrag.datum.year,
                eintrag.datum.month,
            )
            zeitraum_text = eintrag.datum.strftime("%Y-%m")

        else:
            iso = eintrag.datum.isocalendar()
            schluessel = (
                iso.year,
                iso.week,
            )
            zeitraum_text = f"{iso.year}-KW{iso.week:02d}"

        if schluessel not in gruppen:
            gruppen[schluessel] = {
                "zeitraum": zeitraum_text,
                "anzahl": 0,
                "ist": 0,
                "soll": 0,
                "differenz": 0,
            }

        gruppe = gruppen[schluessel]

        gruppe["anzahl"] += 1
        gruppe["ist"] += eintrag.arbeitsminuten
        gruppe["soll"] += eintrag.sollminuten
        gruppe["differenz"] += eintrag.differenzminuten

    auswertungen_liste = []

    for gruppe in gruppen.values():
        auswertungen_liste.append({
            "zeitraum": gruppe["zeitraum"],
            "anzahl": gruppe["anzahl"],
            "ist_zeit": minuten_formatieren(gruppe["ist"]),
            "soll_zeit": minuten_formatieren(gruppe["soll"]),
            "differenz_zeit": minuten_formatieren(gruppe["differenz"]),
        })

    return render(
        request,
        "arbeitszeit/auswertungen.html",
        {
            "ansicht": ansicht,
            "auswertungen": auswertungen_liste,
            "heute": heute,
            "aktuelles_jahr": heute.year,
            "aktuelles_iso_jahr": heute.isocalendar().year,
            "aktueller_tag": heute.day,
            "aktueller_monat": heute.month,
            "aktuelle_kw": heute.isocalendar().week,
            "jahre": range(2000, 2101),
        },
    )

@login_required
def pdf_export(request):
    zeitraum, jahr, nummer, start, ende = _auswertungszeitraum(request)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
            KeepTogether,
        )
        from reportlab.pdfgen import canvas
    except ImportError:
        messages.error(
            request,
            "PDF-Export nicht verfügbar: Bitte installiere zuerst reportlab."
        )
        return redirect("auswertungen")

    # ---------------------------------------------------------------
    # PDF-Einstellungen
    # ---------------------------------------------------------------

    response = HttpResponse(content_type="application/pdf")

    if zeitraum == "monat":
        dateiname = f"Arbeitszeit_Monat_{jahr}-{nummer:02d}.pdf"
    elif zeitraum == "woche":
        dateiname = f"Arbeitszeit_Woche_{jahr}_KW{nummer:02d}.pdf"
    else:
        dateiname = f"Arbeitszeit_Jahr_{jahr}.pdf"

    response["Content-Disposition"] = (
        f'attachment; filename="{dateiname}"'
    )

    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=12 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    titel_style = ParagraphStyle(
        "PDFTitel",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        alignment=0,
        spaceAfter=5,
        textColor=colors.HexColor("#222222"),
    )

    name_style = ParagraphStyle(
        "PDFName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=15,
    )

    kw_style = ParagraphStyle(
        "PDFKalenderwoche",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        spaceBefore=0,
        spaceAfter=5,
        textColor=colors.HexColor("#222222"),
    )

    header_style = ParagraphStyle(
        "PDFTabellenkopf",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9,
        alignment=TA_CENTER,
    )

    # ---------------------------------------------------------------
    # Seitenzahlen: Seite X von Y
    # ---------------------------------------------------------------

    class NumberedCanvas(canvas.Canvas):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.saved_page_states = []

        def showPage(self):
            self.saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            anzahl_seiten = len(self.saved_page_states)

            for zustand in self.saved_page_states:
                self.__dict__.update(zustand)

                self.saveState()
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.HexColor("#333333"))

                self.drawString(
                    20 * mm,
                    9 * mm,
                    "Signum-Felder bitte handschriftlich ausfüllen."
                )

                self.drawRightString(
                    landscape(A4)[0] - 20 * mm,
                    9 * mm,
                    f"Seite {self._pageNumber} von {anzahl_seiten}"
                )

                self.restoreState()
                canvas.Canvas.showPage(self)

            canvas.Canvas.save(self)

    # ---------------------------------------------------------------
    # Formatierung
    # ---------------------------------------------------------------

    def pdf_minuten(minuten):
        minuten = int(minuten or 0)

        stunden, rest = divmod(abs(minuten), 60)

        if minuten > 0:
            vorzeichen = "+"
        elif minuten < 0:
            vorzeichen = "-"
        else:
            vorzeichen = ""

        return f"{vorzeichen}{stunden:02d}:{rest:02d}"

    monatsnamen = [
        "Januar", "Februar", "März", "April",
        "Mai", "Juni", "Juli", "August",
        "September", "Oktober", "November", "Dezember",
    ]

    wochentage = [
        "Montag", "Dienstag", "Mittwoch",
        "Donnerstag", "Freitag",
    ]

    # ---------------------------------------------------------------
    # Arbeitszeiteinträge laden
    # ---------------------------------------------------------------

    alle_eintraege = {
        eintrag.datum: eintrag
        for eintrag in ArbeitszeitEintrag.objects.filter(
            benutzer=request.user
        ).order_by("datum")
    }

    # Kumuliertes Zeitkonto vor dem Exportzeitraum.
    kumulativ_start = sum(
        eintrag.differenzminuten
        for datum, eintrag in alle_eintraege.items()
        if datum < start
    )

    # ---------------------------------------------------------------
    # Kalenderwochen und Tageszeilen erstellen
    # ---------------------------------------------------------------

    def wochen_erstellen(monats_start, monats_ende, kumulativ):
        gruppen = {}

        aktueller_tag = monats_start

        while aktueller_tag < monats_ende:
            if aktueller_tag.weekday() < 5:
                wochenstart = (
                    aktueller_tag
                    - timedelta(days=aktueller_tag.weekday())
                )

                gruppen.setdefault(wochenstart, []).append(aktueller_tag)

            aktueller_tag += timedelta(days=1)

        wochen = []

        for wochenstart, tage in sorted(gruppen.items()):
            iso = wochenstart.isocalendar()

            zeilen = []

            for tag in tage:
                eintrag = alle_eintraege.get(tag)

                if eintrag:
                    differenz = eintrag.differenzminuten
                    kumulativ += differenz

                    beginn = eintrag.startzeit.strftime("%H:%M")
                    ende_zeit = eintrag.endzeit.strftime("%H:%M")
                    differenz_text = pdf_minuten(differenz)

                else:
                    beginn = ""
                    ende_zeit = ""
                    differenz_text = ""

                zeilen.append([
                    beginn,
                    "",
                    ende_zeit,
                    "",
                    differenz_text,
                    pdf_minuten(kumulativ),
                    f"{wochentage[tag.weekday()]}, "
                    f"{tag.strftime('%d.%m.%Y')}",
                ])

            wochen.append({
                "name": f"KW {iso.week:02d}/{iso.year}",
                "zeilen": zeilen,
            })

        return wochen, kumulativ

    # ---------------------------------------------------------------
    # Tabellen für eine Kalenderwoche
    # ---------------------------------------------------------------

    def wochen_tabelle(woche):
        kopf = [
            Paragraph("Beginn", header_style),
            Paragraph("Signum", header_style),
            Paragraph("Ende", header_style),
            Paragraph("Signum", header_style),
            Paragraph("Differenz", header_style),
            Paragraph("Kumulativ", header_style),
            Paragraph("Wochentag + Datum", header_style),
        ]

        daten = [kopf] + woche["zeilen"]

        tabelle = Table(
            daten,
            colWidths=[
                55, 58, 55, 58, 75, 75, 352
            ],
            rowHeights=[22] + [19] * len(woche["zeilen"]),
            repeatRows=1,
            hAlign="LEFT",
        )

        tabelle.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#E6E6E6")),

            ("TEXTCOLOR", (0, 0), (-1, -1),
             colors.HexColor("#222222")),

            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),

            ("ALIGN", (0, 0), (5, -1), "CENTER"),
            ("ALIGN", (6, 0), (6, -1), "LEFT"),

            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

            ("GRID", (0, 0), (-1, -1),
             0.5, colors.HexColor("#555555")),

            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),

            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))

        return tabelle

    # ---------------------------------------------------------------
    # Seitenkopf
    # ---------------------------------------------------------------

    def seitenkopf(titel):
        return [
            Paragraph(titel, titel_style),
            Paragraph(
                "Name: ______________________________________________",
                name_style,
            ),
            Spacer(1, 12),
        ]

    # ---------------------------------------------------------------
    # Kalenderwochen gleichmäßig auf zwei Seiten verteilen
    # ---------------------------------------------------------------

    def monatsseiten_erstellen(wochen, titel):
        anzahl = len(wochen)

        # Erste Seite bekommt bei ungerader Anzahl eine KW mehr.
        teilung = (anzahl + 1) // 2

        seiten = [
            wochen[:teilung],
            wochen[teilung:],
        ]

        for index, wochen_der_seite in enumerate(seiten):
            if index > 0:
                story.append(PageBreak())

            story.extend(seitenkopf(titel))

            for woche in wochen_der_seite:
                block = KeepTogether([
                    Paragraph(woche["name"], kw_style),
                    wochen_tabelle(woche),
                ])

                story.append(block)

                # Abstand zwischen den Kalenderwochen.
                story.append(Spacer(1, 15))

    # ---------------------------------------------------------------
    # PDF-Inhalt
    # ---------------------------------------------------------------

    story = []

    if zeitraum == "monat":

        titel = (
            f"Monatsarbeitszeitnachweis – "
            f"{monatsnamen[nummer - 1]} {jahr}"
        )

        wochen, _ = wochen_erstellen(
            start,
            ende,
            kumulativ_start,
        )

        # Genau zwei Seiten für den Monatsnachweis.
        monatsseiten_erstellen(wochen, titel)

    elif zeitraum == "woche":

        iso = start.isocalendar()

        titel = (
            f"Wochenarbeitszeitnachweis – "
            f"KW {iso.week:02d}/{iso.year}"
        )

        wochen, _ = wochen_erstellen(
            start,
            ende,
            kumulativ_start,
        )

        story.extend(seitenkopf(titel))

        for woche in wochen:
            story.append(Paragraph(woche["name"], kw_style))
            story.append(wochen_tabelle(woche))
            story.append(Spacer(1, 15))

    else:
        # Jahresbericht: Jeder Monat bekommt eine Doppelseite.
        kumulativ = kumulativ_start

        for monat in range(1, 13):
            if monat > 1:
                story.append(PageBreak())
            monat_start = date(jahr, monat, 1)

            if monat == 12:
                monat_ende = date(jahr + 1, 1, 1)
            else:
                monat_ende = date(jahr, monat + 1, 1)

            wochen, kumulativ = wochen_erstellen(
                monat_start,
                monat_ende,
                kumulativ,
            )

            titel = (
                f"Monatsarbeitszeitnachweis – "
                f"{monatsnamen[monat - 1]} {jahr}"
            )

            monatsseiten_erstellen(wochen, titel)

    # ---------------------------------------------------------------
    # PDF erstellen
    # ---------------------------------------------------------------

    doc.build(
        story,
        canvasmaker=NumberedCanvas,
    )

    return response



# ---------------------------------------------------------------------------
# Änderungshistorie
# ---------------------------------------------------------------------------

@login_required
def historie(request):
    eintraege = AenderungsHistorie.objects.filter(
        benutzer=request.user
    ).order_by("-zeitpunkt")

    return render(
        request,
        "arbeitszeit/historie.html",
        {"historie": eintraege},
    )


# ---------------------------------------------------------------------------
# Einstellungen (neue Versionen ab Stichtag; bestehende bleiben erhalten)
# ---------------------------------------------------------------------------

@login_required
def einstellungen(request):
    aktuelle = einstellung_fuer_datum(request.user, timezone.localdate())

    if request.method == "POST":
        form = ArbeitszeitEinstellungForm(request.POST, einstellung=aktuelle)
        tages_initial = {
            f"tag_{tag}": (
                aktuelle.tages_soll.get(tag, 0) if aktuelle else
                {"0": 475, "1": 475, "2": 475, "3": 475, "4": 415, "5": 0, "6": 0}[tag]
            )
            for tag, _ in WOCHEN_TAGE
        }
        zeiten_initial = {}
        basis_zeiten = aktuelle.zeiten if aktuelle else {}
        for tag, _ in WOCHEN_TAGE[:5]:
            for modell, _ in ARBEITSZEIT_MODELLE:
                standard = (
                    basis_zeiten.get(tag, {}).get(modell)
                    or (
                        {"flex": ["07:00", "17:00"], "kern": ["08:00", "15:00"],
                         "regel": ["07:30", "16:15"]}
                        if tag != "4"
                        else {"flex": ["07:00", "15:15"], "kern": ["08:00", "12:00"],
                              "regel": ["07:30", "14:30"]}
                    )[modell]
                )
                zeiten_initial[f"{tag}_{modell}_start"] = standard[0]
                zeiten_initial[f"{tag}_{modell}_ende"] = standard[1]

        tages_form = TagesSollForm(request.POST, initial=tages_initial)
        zeiten_form = ArbeitszeitenForm(request.POST, initial=zeiten_initial)

        if form.is_valid() and tages_form.is_valid() and zeiten_form.is_valid():
            tages_soll = {
                tag: tages_form.cleaned_data[f"tag_{tag}"]
                for tag, _ in WOCHEN_TAGE
            }
            zeiten = {}
            for tag, _ in WOCHEN_TAGE[:5]:
                zeiten[tag] = {}
                for modell, _ in ARBEITSZEIT_MODELLE:
                    beginn = zeiten_form.cleaned_data[f"{tag}_{modell}_start"]
                    ende = zeiten_form.cleaned_data[f"{tag}_{modell}_ende"]
                    if beginn and ende and ende <= beginn:
                        zeiten_form.add_error(
                            f"{tag}_{modell}_ende",
                            "Das Ende muss nach dem Beginn liegen.",
                        )
                    elif bool(beginn) != bool(ende):
                        zeiten_form.add_error(
                            f"{tag}_{modell}_ende",
                            "Beginn und Ende müssen beide angegeben werden.",
                        )
                    zeiten[tag][modell] = [
                        beginn.strftime("%H:%M") if beginn else "",
                        ende.strftime("%H:%M") if ende else "",
                    ]

            if not zeiten_form.errors:
                gueltig_ab = form.cleaned_data["gueltig_ab"]
                if ArbeitszeitEinstellung.objects.filter(
                    benutzer=request.user,
                    gueltig_ab=gueltig_ab,
                ).exists():
                    form.add_error(
                        "gueltig_ab",
                        "Für dieses Datum existiert bereits eine Einstellungsversion.",
                    )
                else:
                    ArbeitszeitEinstellung.objects.create(
                        benutzer=request.user,
                        gueltig_ab=gueltig_ab,
                        wochen_soll=form.cleaned_data["wochen_soll"],
                        tages_soll=tages_soll,
                        fruehstueckspause=form.cleaned_data["fruehstueckspause"],
                        mittagspause=form.cleaned_data["mittagspause"],
                        zeiten=zeiten,
                    )
                    messages.success(
                        request,
                        "Neue Einstellungen wurden gespeichert und gelten ab dem gewählten Datum.",
                    )
                    return redirect("einstellungen")
    else:
        initial = {
            "gueltig_ab": timezone.localdate(),
            "wochen_soll": aktuelle.wochen_soll if aktuelle else 2315,
            "fruehstueckspause": aktuelle.fruehstueckspause if aktuelle else 20,
            "mittagspause": aktuelle.mittagspause if aktuelle else 30,
        }
        form = ArbeitszeitEinstellungForm(initial=initial)

        tages_initial = {
            f"tag_{tag}": (
                aktuelle.tages_soll.get(tag, 0) if aktuelle else
                {"0": 475, "1": 475, "2": 475, "3": 475, "4": 415, "5": 0, "6": 0}[tag]
            )
            for tag, _ in WOCHEN_TAGE
        }
        tages_form = TagesSollForm(initial=tages_initial)

        zeiten_initial = {}
        basis_zeiten = aktuelle.zeiten if aktuelle else {}
        for tag, _ in WOCHEN_TAGE[:5]:
            for modell, _ in ARBEITSZEIT_MODELLE:
                standard = (
                    basis_zeiten.get(tag, {}).get(modell)
                    or (
                        {"flex": ["07:00", "17:00"], "kern": ["08:00", "15:00"],
                         "regel": ["07:30", "16:15"]}
                        if tag != "4"
                        else {"flex": ["07:00", "15:15"], "kern": ["08:00", "12:00"],
                              "regel": ["07:30", "14:30"]}
                    )[modell]
                )
                zeiten_initial[f"{tag}_{modell}_start"] = standard[0]
                zeiten_initial[f"{tag}_{modell}_ende"] = standard[1]
        zeiten_form = ArbeitszeitenForm(initial=zeiten_initial)

    return render(
        request,
        "arbeitszeit/einstellungen.html",
        {
            "form": form,
            "tages_soll_form": tages_form,
            "zeiten_form": zeiten_form,
            "einstellungen": ArbeitszeitEinstellung.objects.filter(
                benutzer=request.user
            ).order_by("-gueltig_ab"),
        },
    )


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------

@login_required
def profil(request):
    profil_obj, _ = BenutzerProfil.objects.get_or_create(benutzer=request.user)
    form = BenutzerProfilForm(request.POST or None, instance=profil_obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dein Profil wurde aktualisiert.")
        return redirect("profil")

    return render(request, "arbeitszeit/profil.html", {"form": form})


# ---------------------------------------------------------------------------
# Live-Erfassung
# ---------------------------------------------------------------------------

@login_required
def live_start(request):
    if request.method != "POST":
        return redirect("dashboard")

    if LiveErfassung.objects.filter(benutzer=request.user).exists():
        messages.warning(request, "Die Live-Erfassung läuft bereits.")
        return redirect("dashboard")

    try:
        LiveErfassung.objects.create(benutzer=request.user)
    except IntegrityError:
        messages.warning(request, "Die Live-Erfassung läuft bereits.")
    else:
        messages.success(request, "Live-Erfassung wurde gestartet.")

    return redirect("dashboard")


@login_required
def live_stop(request):
    if request.method != "POST":
        return redirect("dashboard")

    live = get_object_or_404(LiveErfassung, benutzer=request.user)
    gestartet = timezone.localtime(live.gestartet_am)
    beendet = timezone.localtime(timezone.now())

    if gestartet.date() != beendet.date():
        messages.error(
            request,
            "Die Live-Erfassung überschreitet einen Tageswechsel. "
            "Bitte erfasse diesen Zeitraum manuell und starte danach neu.",
        )
        return redirect("dashboard")

    datum = gestartet.date()
    einstellung = einstellung_fuer_datum(request.user, datum)
    if einstellung is None:
        messages.error(
            request,
            "Für den Starttag existieren keine gültigen Arbeitseinstellungen.",
        )
        return redirect("dashboard")

    try:
        arbeitsminuten = arbeitszeit_berechnen(
            datum,
            gestartet.time().replace(tzinfo=None),
            beendet.time().replace(tzinfo=None),
            einstellung.fruehstueckspause,
            einstellung.mittagspause,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")

    eintrag = ArbeitszeitEintrag(
        benutzer=request.user,
        datum=datum,
        startzeit=gestartet.time().replace(tzinfo=None),
        endzeit=beendet.time().replace(tzinfo=None),
        fruehstueckspause=einstellung.fruehstueckspause,
        mittagspause=einstellung.mittagspause,
        arbeitsminuten=arbeitsminuten,
        sollminuten=einstellung.tages_soll.get(str(datum.weekday()), 0),
        differenzminuten=(
            arbeitsminuten
            - einstellung.tages_soll.get(str(datum.weekday()), 0)
        ),
    )

    try:
        with transaction.atomic():
            eintrag_speichern_mit_historie(eintrag, "erstellt")
            live.delete()
    except IntegrityError:
        messages.error(
            request,
            "Für diesen Tag existiert bereits ein Arbeitszeiteintrag. "
            "Die Live-Erfassung wurde nicht beendet.",
        )
    else:
        messages.success(request, "Arbeitszeit wurde gespeichert.")
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# Anmeldung, Registrierung und Abmeldung
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user is not None:
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(next_url or "dashboard")
        messages.error(request, "Benutzername oder Passwort ist nicht korrekt.")

    return render(
        request,
        "arbeitszeit/login.html",
        {"next": request.GET.get("next", "")},
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Registrierung erfolgreich. Du kannst dich jetzt anmelden.",
        )
        return redirect("login")

    return render(request, "arbeitszeit/register.html", {"form": form})


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("login")
