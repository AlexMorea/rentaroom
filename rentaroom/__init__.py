"""Package init for the Django project.

Import the Celery app lazily and only if Celery is installed. This prevents
startup failures in environments that don't run Celery (for example lightweight
Gunicorn-only deployments) while still exposing `rentaroom.celery.celery_app`
when available.
"""

try:
	from .celery import app as celery_app
except Exception:
	celery_app = None

# re-export when available
__all__ = ("celery_app",)

