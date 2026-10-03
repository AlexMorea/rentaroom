from django.apps import AppConfig


class ClipsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clips"

    def ready(self):
        from . import signals  # noqa: F401
