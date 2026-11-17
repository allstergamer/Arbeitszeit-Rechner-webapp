
from django.contrib import admin

from .models import (
    BenutzerProfil,
    ArbeitszeitEinstellung,
    ArbeitszeitEintrag,
    AenderungsHistorie,
    LiveErfassung,
)


admin.site.register(BenutzerProfil)
admin.site.register(ArbeitszeitEinstellung)
admin.site.register(ArbeitszeitEintrag)
admin.site.register(LiveErfassung)


@admin.register(AenderungsHistorie)
class AenderungsHistorieAdmin(admin.ModelAdmin):
    list_display = ("benutzer_anzeigen", "eintrag_id", "aktion", "zeitpunkt")
    list_select_related = ("benutzer",)
    search_fields = (
        "benutzer__username",
        "benutzer__first_name",
        "benutzer__last_name",
    )
    ordering = ("-zeitpunkt",)

    @admin.display(description="Benutzer")
    def benutzer_anzeigen(self, obj):
        benutzername = obj.benutzer.get_full_name()
        if benutzername:
            return f"{benutzername} ({obj.benutzer.username})"
        return obj.benutzer.username
