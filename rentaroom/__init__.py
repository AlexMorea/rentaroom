from .celery import app as celery_app

# re-export for `from rentaroom.celery import app` usage
__all__ = ("celery_app",)

