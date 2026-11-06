
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import BenutzerProfil, ArbeitszeitEinstellung


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def benutzer_erstellen(sender, instance, created, **kwargs):
    if not created:
        return

    BenutzerProfil.objects.create(
        benutzer=instance
    )

    ArbeitszeitEinstellung.objects.create(
        benutzer=instance,
        gueltig_ab=timezone.localdate(),
    )
