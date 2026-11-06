
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
admin.site.register(AenderungsHistorie)
admin.site.register(LiveErfassung)
