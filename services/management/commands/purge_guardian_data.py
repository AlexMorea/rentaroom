"""
Guardian mode data retention (POPIA: keep personal information no longer
than needed).

Live location is only useful while someone is on a viewing, so:

- Location pings are deleted 30 days after they were recorded.
- After 30 days a session's last known position and its emergency
  contact's name and number are cleared. The session row itself stays
  (destination, times, status) so usage numbers still add up.
- Sessions with a panic alert or emergency event are safety records:
  their pings, position and contact details are kept for 12 months from
  the session start, then cleared the same way, and the alerts/events
  themselves are deleted 12 months after they were raised.

Report-only by default, like every other scheduled command; pass --force
to delete. Runs daily from listings/scheduler.py.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from services.models import (
    EmergencyEvent,
    GuardianLocationPing,
    GuardianSession,
    PanicAlert,
)

LOCATION_RETENTION_DAYS = 30
SAFETY_RECORD_RETENTION_DAYS = 365


class Command(BaseCommand):
    help = (
        "Delete Guardian location data after 30 days, and panic/emergency "
        "records after 12 months. Report-only unless --force."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually delete/clear the data (default is report-only).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        now = timezone.now()
        location_cutoff = now - timedelta(days=LOCATION_RETENTION_DAYS)
        safety_cutoff = now - timedelta(days=SAFETY_RECORD_RETENTION_DAYS)

        has_safety_record = Q(alerts__isnull=False) | Q(emergency_events__isnull=False)
        safety_session_ids = set(
            GuardianSession.objects.filter(has_safety_record).values_list("id", flat=True)
        )

        # A session is "expired" once its retention window has passed:
        # 30 days for ordinary sessions, 12 months for safety records.
        expired_sessions = GuardianSession.objects.filter(
            (Q(started_at__lt=location_cutoff) & ~Q(id__in=safety_session_ids))
            | (Q(started_at__lt=safety_cutoff) & Q(id__in=safety_session_ids))
        )

        pings = GuardianLocationPing.objects.filter(
            (Q(created_at__lt=location_cutoff) & ~Q(session_id__in=safety_session_ids))
            | (Q(created_at__lt=safety_cutoff) & Q(session_id__in=safety_session_ids))
        )
        alerts = PanicAlert.objects.filter(created_at__lt=safety_cutoff)
        events = EmergencyEvent.objects.filter(created_at__lt=safety_cutoff)
        sessions_to_clear = expired_sessions.filter(
            ~Q(latest_latitude__isnull=True)
            | ~Q(latest_longitude__isnull=True)
            | ~Q(emergency_contact_name="")
            | ~Q(emergency_contact_phone="")
        )

        counts = {
            "location pings": pings.count(),
            "panic alerts": alerts.count(),
            "emergency events": events.count(),
            "sessions to clear": sessions_to_clear.count(),
        }
        summary = ", ".join(f"{n} {label}" for label, n in counts.items())

        if not force:
            self.stdout.write(f"Report only (pass --force to delete): {summary}")
            return

        # Clear sessions before deleting alerts, so the 12-month sessions
        # are still recognised as safety records on this pass.
        sessions_to_clear.update(
            latest_latitude=None,
            latest_longitude=None,
            emergency_contact_name="",
            emergency_contact_phone="",
        )
        pings.delete()
        alerts.delete()
        events.delete()

        self.stdout.write(f"Guardian retention applied: {summary}")
