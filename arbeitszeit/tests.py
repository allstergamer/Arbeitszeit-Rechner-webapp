from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AenderungsHistorie,
    ArbeitszeitEintrag,
    ArbeitszeitEinstellung,
    LiveErfassung,
)


class LiveErfassungTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="live-test",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.heute = timezone.localdate()

    def arbeitszeit_einstellung_anlegen(self, datum):
        return ArbeitszeitEinstellung.objects.update_or_create(
            benutzer=self.user,
            gueltig_ab=datum,
            defaults={
                "tages_soll": {str(datum.weekday()): 480},
                "fruehstueckspause": 0,
                "mittagspause": 0,
            },
        )[0]

    def test_live_stop_speichert_eintrag_und_aenderungshistorie(self):
        self.arbeitszeit_einstellung_anlegen(self.heute)
        gestartet_am = timezone.make_aware(
            datetime.combine(self.heute, time(8, 0))
        )
        beendet_am = timezone.make_aware(
            datetime.combine(self.heute, time(16, 0))
        )

        with patch("arbeitszeit.views.timezone.now", return_value=gestartet_am):
            start_response = self.client.post(reverse("live_start"))

        self.assertRedirects(start_response, reverse("dashboard"))
        self.assertTrue(LiveErfassung.objects.filter(benutzer=self.user).exists())
        LiveErfassung.objects.filter(benutzer=self.user).update(
            gestartet_am=gestartet_am
        )

        with patch("arbeitszeit.views.timezone.now", return_value=beendet_am):
            stop_response = self.client.post(reverse("live_stop"), follow=True)

        self.assertContains(stop_response, "Arbeitszeit wurde gespeichert.")
        eintrag = ArbeitszeitEintrag.objects.get(benutzer=self.user, datum=self.heute)
        self.assertEqual(eintrag.startzeit, time(8, 0))
        self.assertEqual(eintrag.endzeit, time(16, 0))
        self.assertEqual(eintrag.arbeitsminuten, 480)
        self.assertEqual(eintrag.sollminuten, 480)
        self.assertEqual(eintrag.differenzminuten, 0)
        self.assertFalse(LiveErfassung.objects.filter(benutzer=self.user).exists())
        self.assertTrue(
            AenderungsHistorie.objects.filter(
                benutzer=self.user,
                eintrag_id=eintrag.id,
                aktion="erstellt",
            ).exists()
        )

    def test_tageswechsel_meldet_fehler_und_live_erfassung_kann_abgebrochen_werden(self):
        gestern = self.heute - timedelta(days=1)
        gestartet_am = timezone.make_aware(
            datetime.combine(gestern, time(23, 30))
        )
        LiveErfassung.objects.create(
            benutzer=self.user,
            gestartet_am=gestartet_am,
        )
        beendet_am = timezone.make_aware(
            datetime.combine(self.heute, time(0, 30))
        )

        with patch("arbeitszeit.views.timezone.now", return_value=beendet_am):
            stop_response = self.client.post(reverse("live_stop"), follow=True)

        self.assertContains(stop_response, "überschreitet einen Tageswechsel")
        self.assertTrue(LiveErfassung.objects.filter(benutzer=self.user).exists())
        self.assertFalse(ArbeitszeitEintrag.objects.filter(benutzer=self.user).exists())

        cancel_response = self.client.post(reverse("live_cancel"), follow=True)

        self.assertContains(cancel_response, "Es wurde kein Eintrag gespeichert.")
        self.assertFalse(LiveErfassung.objects.filter(benutzer=self.user).exists())
        self.assertFalse(ArbeitszeitEintrag.objects.filter(benutzer=self.user).exists())


class ArbeitszeitEinstellungTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="settings-test",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.einstellung = ArbeitszeitEinstellung.objects.get(
            benutzer=self.user,
            gueltig_ab=timezone.localdate(),
        )

    def get_form_data(self):
        data = {
            "gueltig_ab": self.einstellung.gueltig_ab.isoformat(),
            "wochen_soll": "2400",
            "fruehstueckspause": "15",
            "mittagspause": "45",
        }
        data.update({f"tag_{tag}": "480" for tag in range(7)})

        for tag in range(5):
            for modell in ("flex", "kern", "regel"):
                data[f"{tag}_{modell}_start"] = "08:00"
                data[f"{tag}_{modell}_ende"] = "16:00"

        return data

    def test_speichert_pausenaenderungen_in_bestehender_einstellung(self):
        response = self.client.post(
            reverse("einstellungen"),
            self.get_form_data(),
            follow=True,
        )

        self.assertContains(response, "Einstellungen für das gewählte Datum wurden aktualisiert.")
        self.einstellung.refresh_from_db()
        self.assertEqual(self.einstellung.fruehstueckspause, 15)
        self.assertEqual(self.einstellung.mittagspause, 45)
        self.assertEqual(self.einstellung.wochen_soll, 2400)
        self.assertContains(response, "15 + 45 min")

    def test_tagessollfelder_werden_im_einstellungsformular_angezeigt(self):
        response = self.client.get(reverse("einstellungen"))

        self.assertContains(response, 'name="tag_0"')
        self.assertContains(response, 'name="tag_6"')


class ArbeitszeitWarnungenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="warning-test",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_warnung_wird_fuer_zeitspanne_ueber_11_stunden_angezeigt(self):
        heute = timezone.localdate()
        langer_eintrag = ArbeitszeitEintrag.objects.create(
            benutzer=self.user,
            datum=heute,
            startzeit=time(6, 0),
            endzeit=time(17, 1),
        )
        eintrag_mit_11_stunden = ArbeitszeitEintrag.objects.create(
            benutzer=self.user,
            datum=heute - timedelta(days=1),
            startzeit=time(6, 0),
            endzeit=time(17, 0),
        )

        for route in ("dashboard", "eintraege"):
            response = self.client.get(reverse(route))
            eintraege = response.context[
                "letzte_eintraege" if route == "dashboard" else "eintraege"
            ]
            warnungen = {
                eintrag.pk: eintrag.warnung_lange_arbeitszeit
                for eintrag in eintraege
            }
            self.assertTrue(warnungen[langer_eintrag.pk])
            self.assertFalse(warnungen[eintrag_mit_11_stunden.pk])
            self.assertContains(response, "Warnung: Arbeitszeit länger als empfohlen")
            self.assertContains(response, "Abbrechen")
            self.assertContains(response, "Bearbeiten")
            self.assertContains(response, "Löschen")

    def test_live_warnung_erscheint_erst_nach_11_stunden(self):
        jetzt = timezone.now()
        live = LiveErfassung.objects.create(
            benutzer=self.user,
            gestartet_am=jetzt - timedelta(hours=11, minutes=1),
        )

        with patch("arbeitszeit.views.timezone.now", return_value=jetzt):
            response = self.client.get(reverse("dashboard"))

        self.assertTrue(response.context["live_warnung_lange_arbeitszeit"])
        self.assertContains(response, "Die laufende Arbeitszeit dauert länger als 11 Stunden.")

        live.gestartet_am = jetzt - timedelta(hours=11)
        live.save(update_fields=["gestartet_am"])
        with patch("arbeitszeit.views.timezone.now", return_value=jetzt):
            response = self.client.get(reverse("dashboard"))

        self.assertFalse(response.context["live_warnung_lange_arbeitszeit"])
        self.assertNotContains(response, "Die laufende Arbeitszeit dauert länger als 11 Stunden.")


class ArbeitszeitverkuerzungTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="azv-test",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.heute = timezone.localdate()
        ArbeitszeitEinstellung.objects.update_or_create(
            benutzer=self.user,
            gueltig_ab=self.heute,
            defaults={
                "tages_soll": {str(self.heute.weekday()): 480},
                "fruehstueckspause": 0,
                "mittagspause": 0,
            },
        )

    def get_form_data(self, endzeit, azv=False):
        data = {
            "datum": self.heute.isoformat(),
            "startzeit": "08:00",
            "endzeit": endzeit,
            "notizen": "",
        }
        if azv:
            data["azv"] = "on"
        return data

    def test_azv_speichert_null_differenz_bei_unter_und_ueber_sollzeit(self):
        response = self.client.post(
            reverse("eintrag_erfassen"),
            self.get_form_data("13:00", azv=True),
            follow=True,
        )

        eintrag = ArbeitszeitEintrag.objects.get(benutzer=self.user)
        self.assertEqual(eintrag.arbeitsminuten, 300)
        self.assertTrue(eintrag.azv)
        self.assertEqual(eintrag.differenzminuten, 0)
        self.assertContains(response, 'class="azv-indicator"')
        self.assertContains(response, "Arbeitszeitverkürzung")

        response = self.client.post(
            reverse("eintrag_bearbeiten", args=[eintrag.pk]),
            self.get_form_data("18:00", azv=True),
            follow=True,
        )

        eintrag.refresh_from_db()
        self.assertEqual(eintrag.arbeitsminuten, 600)
        self.assertEqual(eintrag.differenzminuten, 0)
        self.assertContains(response, 'class="azv-indicator"')

    def test_eintrag_ohne_azv_bucht_normale_differenz(self):
        self.client.post(
            reverse("eintrag_erfassen"),
            self.get_form_data("13:00"),
        )

        eintrag = ArbeitszeitEintrag.objects.get(benutzer=self.user)
        self.assertFalse(eintrag.azv)
        self.assertEqual(eintrag.differenzminuten, -180)


class KopfzeilenAbmeldungTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="logout-test",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_kopfzeile_bietet_abmelden_mit_bestaetigung(self):
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, 'class="topbar-logout-form"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, "return confirm('Möchtest du dich wirklich abmelden?');")


class RegistrierungTests(TestCase):
    def test_registrierung_speichert_vorname_und_nachname(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "name-test",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "password1": "Strong-unique-password-847!",
                "password2": "Strong-unique-password-847!",
            },
        )

        self.assertRedirects(response, reverse("login"))
        user = get_user_model().objects.get(username="name-test")
        self.assertEqual(user.first_name, "Ada")
        self.assertEqual(user.last_name, "Lovelace")

    def test_anmeldung_fragt_keine_namen_ab(self):
        response = self.client.get(reverse("login"))

        self.assertNotContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="last_name"')
