import os

# celery is a deliberately optional dependency (see CELERY_BROKER_URL in
# settings.py) - only installed where a worker process actually runs this
# module, not in every environment that analyzes this codebase.
from celery import Celery  # pyright: ignore[reportMissingImports]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rentaroom.settings")

app = Celery("rentaroom")  # pyright: ignore[reportCallIssue]
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# default periodic tasks can be added here or via Django settings CELERY_BEAT_SCHEDULE
@app.task(bind=True)
def debug_task(self):
    print(f"Celery debug task: {self.request!r}")
