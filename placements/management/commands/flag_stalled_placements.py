from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from placements.models import Placement
from utils.email import send_template_email


class Command(BaseCommand):
    """
    Run daily (e.g. a Render cron job, alongside check_move_ins and
    flag_overdue_placement_fees).

    A Placement that's been sitting in an early status (Interested,
    Viewing Scheduled/Completed, Approved) for PLACEMENT_STALL_DAYS
    without moving forward is easy to lose track of - neither side gets
    told "hey, where are we with this?" anywhere else in the app. This
    sends one nudge to both tenant and landlord asking them to update
    the placement's status, so a rental doesn't just quietly go cold.

    One-time per stall (stall_nudge_sent_at), same convention as
    check_move_ins' move_in_check_sent_at - if the status changes, the
    write_status_history signal resets current_status_since, so a later
    re-stall in a *different* status would need a manual re-check; this
    command only clears the flag implicitly by virtue of no longer
    matching STALLABLE_STATUSES once someone acts on it.
    """

    help = "Nudges tenants/landlords about placements stuck in an early status for too long."

    def handle(self, *args, **options):
        threshold = getattr(settings, "PLACEMENT_STALL_DAYS", 7)

        candidates = Placement.objects.filter(
            status__in=Placement.STALLABLE_STATUSES,
            stall_nudge_sent_at__isnull=True,
        ).select_related("tenant", "landlord", "room")

        sent = 0
        for placement in candidates:
            if not placement.is_stalled(threshold):
                continue

            self._send_nudge(placement, threshold)
            placement.stall_nudge_sent_at = timezone.now()
            placement.save(update_fields=["stall_nudge_sent_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent stall nudges for {sent} placement(s)."))

    def _send_nudge(self, placement, threshold_days):
        context = {
            "placement": placement,
            "room": placement.room,
            "days": placement.days_in_current_status,
            "threshold_days": threshold_days,
            "year": timezone.now().year,
        }

        if placement.tenant.email:
            send_template_email(
                subject=f'Still interested in "{placement.room.title}"?',
                to_email=placement.tenant.email,
                template="emails/placement_stalled_tenant.html",
                context=context,
            )

        if placement.landlord.email:
            send_template_email(
                subject=f'An enquiry on "{placement.room.title}" needs an update',
                to_email=placement.landlord.email,
                template="emails/placement_stalled_landlord.html",
                context=context,
            )
