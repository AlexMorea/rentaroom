import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rentaroom.settings")

app = Celery("rentaroom")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# default periodic tasks can be added here or via Django settings CELERY_BEAT_SCHEDULE
@app.task(bind=True)
def debug_task(self):
    print(f"Celery debug task: {self.request!r}")
