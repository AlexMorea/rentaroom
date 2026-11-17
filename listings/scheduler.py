"""
In-process scheduler for the jobs that keep search ranking and trust
signals fresh, so they actually run without a Celery worker/beat (none is
deployed - CELERY_BROKER_URL is unset, which left Room.score frozen).

How it works: the middleware below checks, on ordinary requests, whether
a job is due (a cache key per job acts as both the "last ran" marker and
the lock). If it is, the job runs once in a background thread - the
request that noticed never waits for it. With several gunicorn workers
and the per-process local-memory cache a job may run once per worker per
period; every job here is idempotent, so that's harmless.

Only jobs that change data quietly live here. Jobs that email users
(stale-listing nudges, digests, move-in checks) are deliberately NOT
scheduled from here - switching those on is a separate decision.
"""
import logging
import threading

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import close_old_connections

logger = logging.getLogger(__name__)

HOUR = 60 * 60

JOBS = (
    # (cache key, period in seconds, management command, args)
    ("jobs:compute_scores", HOUR, "compute_scores", ("--force",)),
    ("jobs:compute_response_stats", 24 * HOUR, "compute_response_stats", ("--force",)),
)


def _run(command, args):
    try:
        call_command(command, *args, verbosity=0)
        logger.info("Scheduled job %s finished", command)
    except Exception:  # noqa: BLE001 - a failed job must never take the site down
        logger.exception("Scheduled job %s failed", command)
    finally:
        close_old_connections()


def run_due_jobs():
    for key, period, command, args in JOBS:
        # cache.add only succeeds if the key is absent -> due and claimed.
        if cache.add(key, "1", period):
            threading.Thread(target=_run, args=(command, args), daemon=True, name=f"job-{command}").start()


class ScheduledJobsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.RUN_SCHEDULED_JOBS_IN_PROCESS:
            try:
                run_due_jobs()
            except Exception:  # noqa: BLE001 - e.g. cache backend down
                logger.exception("Could not check scheduled jobs")
        return response
