from django.apps import AppConfig


class PlacementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "placements"

    def ready(self):
        # Imported here (not at module level) so Django's app registry is
        # fully loaded before the signal receivers touch other apps' models.
        from . import signals  # noqa: F401
