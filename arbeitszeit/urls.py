from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Arbeitszeiteinträge
    path("eintrag-erfassen/", views.eintrag_erfassen, name="eintrag_erfassen"),
    path("eintraege/", views.eintraege, name="eintraege"),
    path(
        "eintrag/<int:eintrag_id>/bearbeiten/",
        views.eintrag_bearbeiten,
        name="eintrag_bearbeiten",
    ),
    path(
        "eintrag/<int:eintrag_id>/loeschen/",
        views.eintrag_loeschen,
        name="eintrag_loeschen",
    ),

    # Benutzerkonto
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "passwort-aendern/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/profil/",
        ),
        name="password_change",
    ),

    # Auswertungen, Historie und persönliche Einstellungen
    path("auswertungen/", views.auswertungen, name="auswertungen"),
    path("auswertungen/pdf/", views.pdf_export, name="pdf_export"),
    path("historie/", views.historie, name="historie"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("profil/", views.profil, name="profil"),

    # Live-Erfassung
    path("live/start/", views.live_start, name="live_start"),
    path("live/stop/", views.live_stop, name="live_stop"),
]
