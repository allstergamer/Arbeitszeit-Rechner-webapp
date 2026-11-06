
from django.apps import AppConfig


class ArbeitszeitConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "arbeitszeit"

    def ready(self):
        from . import signals
