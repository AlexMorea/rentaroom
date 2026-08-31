from django.apps import AppConfig


class TrustConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trust"

    def ready(self):
        import trust.signals  # noqa
