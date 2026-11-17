"""
In-process scheduler for the site's recurring jobs. No Celery worker is
deployed (CELERY_BROKER_URL is unset), so without this nothing recurring
ever ran - search ranking was frozen and no nudge emails went out.

How it works: on ordinary requests (checked at most once a minute per
process) the middleware asks the database whether any job's latest slot
has passed without a run. A job is claimed with one conditional UPDATE on
its ScheduledJobRun row, so exactly one process wins a slot - even across
several gunicorn workers, restarts and redeploys - and then it runs in a
background thread. The request that noticed never waits.

Jobs only run when the site gets traffic, so an early-morning job runs
with the first visit after its time. Every email job also has its own
"already sent" guard per room/landlord/placement, except the digest,
which relies on this once-per-slot claim.
"""
import logging
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from accounts.founding import SAST

logger = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 60


@dataclass(frozen=True)
class Job:
    name: str
    command: str
    args: tuple = ()
    # "hourly", "daily" or "weekly"
    every: str = "daily"
    hour: int = 0
    minute: int = 0
    weekday: int = 0  # Monday = 0, weekly jobs only
    sends_email: bool = False

    def latest_slot(self, now: datetime) -> datetime:
        """The most recent moment (SAST) this job was supposed to run."""
        local = now.astimezone(SAST)
        if self.every == "hourly":
            return local.replace(minute=0, second=0, microsecond=0)
        slot = local.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if self.every == "weekly":
            slot -= timedelta(days=(local.weekday() - self.weekday) % 7)
            if slot > local:
                slot -= timedelta(days=7)
        elif slot > local:
            slot -= timedelta(days=1)
        return slot


JOBS = (
    # Search ranking + trust signals (quiet, no emails).
    Job("compute_scores", "compute_scores", ("--force",), every="hourly"),
    Job("compute_response_stats", "compute_response_stats", ("--force",), hour=6, minute=30),
    # Landlord emails / push, all SAST.
    Job("flag_stale_listings", "flag_stale_listings", ("--force",), hour=6, minute=0, sends_email=True),
    Job("flag_landlords_without_listing", "flag_landlords_without_listing", ("--force",),
        hour=6, minute=15, sends_email=True),
    Job("check_move_ins", "check_move_ins", hour=7, minute=0, sends_email=True),
    Job("flag_stalled_placements", "flag_stalled_placements", hour=7, minute=15, sends_email=True),
    Job("send_landlord_digest", "send_landlord_digest", ("--force",),
        every="weekly", weekday=0, hour=8, minute=0, sends_email=True),
)

_next_check = 0.0
_check_lock = threading.Lock()


def _enabled_jobs():
    for job in JOBS:
        if job.sends_email and not settings.SCHEDULED_EMAIL_JOBS_ENABLED:
            continue
        yield job


def _run(job: Job):
    from listings.models import ScheduledJobRun

    ok, error = True, ""
    try:
        call_command(job.command, *job.args, verbosity=0)
    except Exception:  # noqa: BLE001 - a failed job must never take the site down
        ok, error = False, traceback.format_exc()[-4000:]
        logger.exception("Scheduled job %s failed", job.name)
    finally:
        try:
            ScheduledJobRun.objects.filter(name=job.name).update(
                last_finished_at=timezone.now(), last_ok=ok, last_error=error
            )
        finally:
            close_old_connections()


def claim_due_jobs(now=None) -> list[Job]:
    """Claims every job whose latest slot hasn't run yet. Returns the jobs
    this process won (each slot is won by exactly one caller)."""
    from listings.models import ScheduledJobRun

    now = now or timezone.now()
    claimed = []
    for job in _enabled_jobs():
        slot = job.latest_slot(now)
        run, created = ScheduledJobRun.objects.get_or_create(name=job.name)
        if created and job.sends_email:
            # Switching an email job on for the first time: start from
            # the NEXT slot instead of firing at deploy time.
            ScheduledJobRun.objects.filter(pk=run.pk).update(last_started_at=now)
            continue
        won = ScheduledJobRun.objects.filter(pk=run.pk).filter(
            Q(last_started_at__isnull=True) | Q(last_started_at__lt=slot)
        ).update(last_started_at=now)
        if won:
            claimed.append(job)
    return claimed


def run_due_jobs():
    global _next_check
    with _check_lock:
        if time.monotonic() < _next_check:
            return
        _next_check = time.monotonic() + CHECK_EVERY_SECONDS

    for job in claim_due_jobs():
        threading.Thread(target=_run, args=(job,), daemon=True, name=f"job-{job.name}").start()


class ScheduledJobsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.RUN_SCHEDULED_JOBS_IN_PROCESS:
            try:
                run_due_jobs()
            except Exception:  # noqa: BLE001 - e.g. DB hiccup; try again next minute
                logger.exception("Could not check scheduled jobs")
        return response
