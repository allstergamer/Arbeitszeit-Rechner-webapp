# Chrona – Arbeitszeitverwaltung

Chrona ist eine Django-Web-App zur Erfassung und Auswertung von Arbeitszeiten. Sie ist eine eigenständige Web-App-Recreation des ursprünglichen [Arbeitszeit-Rechner-Projekts](https://github.com/allstergamer/Arbeitszeit-Rechner), keine offizielle Version davon.

Die Anwendung ist eine serverseitig gerenderte Multi-Page Application (MPA). Django rendert die Seiten mit Templates; JavaScript ergänzt einzelne Interaktionen.

## Funktionen

- Benutzerregistrierung, Anmeldung und persönliches Profil
- Arbeitszeiten manuell eintragen, bearbeiten und löschen
- Live-Erfassung mit Starten, Beenden und Abbrechen
- Berechnung von Nettoarbeitszeit, Tagessoll und Zeitdifferenz
- Individuelle Wochen- und Tagessollzeiten, Pausen und Arbeitszeitmodelle; Einstellungen können ab einem Stichtag gelten
- Kennzeichnung von Arbeitszeitverkürzung (AZV)
- Dashboard, Wochen- und Monatsauswertungen sowie PDF-Export
- Änderungshistorie für erstellte, bearbeitete und gelöschte Einträge
- Warnhinweise bei Arbeitszeitspannen über elf Stunden
- Hell-, Dunkel- und Systemdarstellung

## Voraussetzungen

- Python
- Django 6.1.2
- ReportLab für den PDF-Export (optional)

Die Datenbank ist standardmäßig SQLite (`db.sqlite3`).

## Lokal starten (Windows / PowerShell)

Alle Befehle im Projektverzeichnis ausführen:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "Django==6.1.2" reportlab
python manage.py migrate
python manage.py runserver
```

Die Anwendung ist anschließend unter <http://127.0.0.1:8000/> erreichbar. Falls PowerShell das Aktivieren der virtuellen Umgebung blockiert, kann die Ausführungsrichtlinie für das aktuelle Terminal angepasst werden:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

ReportLab ist optional. Ohne das Paket funktioniert die Anwendung weiterhin; der PDF-Export ist dann nicht verfügbar.

## Administrationskonto

Ein Django-Administrationskonto lässt sich mit folgendem Befehl erstellen:

```powershell
python manage.py createsuperuser
```

Das Admin-Panel ist unter <http://127.0.0.1:8000/admin/> erreichbar.

## Tests

```powershell
python manage.py test
```

## Sicherheit und Bereitstellung

Die enthaltene Django-Konfiguration ist für die lokale Entwicklung gedacht. Vor einem öffentlichen Produktivbetrieb müssen insbesondere `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS und die Datenbankkonfiguration gemäß der [Django-Deployment-Checkliste](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/) angepasst werden. `runserver` ist kein Produktionsserver.
