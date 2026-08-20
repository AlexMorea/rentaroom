from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from placements.models import Placement


class Command(BaseCommand):
    """
    Run daily (e.g. as a Render cron job: `python manage.py check_move_ins`).

    For every placement whose move_in_date has passed and which is still
    in a state where a move-in confirmation makes sense (Approved or
    Viewing Completed - see Placement.awaiting_move_in_confirmation),
    this sends a one-time email nudge to whichever side hasn't answered
    yet. It does NOT re-send every day - move_in_check_sent_at is set the
    first time so this command is safe to run daily without spamming.

    There's no Celery/task queue in this project, so a management command
    triggered by an external cron scheduler is the right fit for the
    existing infrastructure rather than adding new infra.
    """

    help = "Nudges tenants/landlords to confirm move-in once the move-in date has passed."

    def handle(self, *args, **options):
        candidates = Placement.objects.filter(
            move_in_date__lte=timezone.localdate(),
        ).exclude(
            status__in=Placement.TERMINAL_STATUSES,
        ).exclude(
            status=Placement.STATUS_VERIFICATION_REQUIRED,
        )

        sent = 0
        for placement in candidates:
            if not placement.awaiting_move_in_confirmation:
                continue

            needs_tenant = placement.tenant_confirmed_move_in is None
            needs_landlord = placement.landlord_confirmed_move_in is None

            if not needs_tenant and not needs_landlord:
                continue

            if placement.move_in_check_sent_at is not None:
                # Already nudged once - don't spam daily. A future
                # iteration could add a second reminder after N days.
                continue

            self._send_nudge(placement, to_tenant=needs_tenant, to_landlord=needs_landlord)
            placement.move_in_check_sent_at = timezone.now()
            placement.save(update_fields=["move_in_check_sent_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} move-in confirmation nudge(s)."))

    def _send_nudge(self, placement, *, to_tenant, to_landlord):
        subject = "Rooms4You: please confirm your move-in"
        recipients = []

        if to_tenant and placement.tenant.email:
            recipients.append(placement.tenant.email)
        if to_landlord and placement.landlord.email:
            recipients.append(placement.landlord.email)

        if not recipients:
            return

        message = (
            f"Hi,\n\n"
            f"Your move-in date for \"{placement.room.title}\" has passed. "
            f"Please log in to Rooms4You and confirm whether the move-in "
            f"happened, so we can finalise this placement.\n\n"
            f"- The Rooms4You Team"
        )

        # Fails silently on purpose: a misconfigured email backend
        # shouldn't crash the whole cron run and skip every other
        # placement in the batch.
        send_mail(
            subject,
            message,
            None,  # uses DEFAULT_FROM_EMAIL
            recipients,
            fail_silently=True,
        )
