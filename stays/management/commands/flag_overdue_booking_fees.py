from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from stays.models import BookingInvoice

# Days of an unpaid guest house success fee invoice before a warning
# fires. Mirrors placements/management/commands/flag_overdue_placement_fees
# exactly - same "we never touch payment ourselves, just remind and
# reconcile manually" model, just for the stays/guest-house side, which
# never got its own reminder even though BookingInvoice already carries
# the same is_overdue()/days_pending helpers as PlacementInvoice.
#
# Deliberately warning-only, with no auto-suspend step: unlike
# Membership, there's no equivalent "suspend this host's account" hook
# for guest houses yet, so this only ever nudges.
WARNING_AFTER_DAYS = 7


class Command(BaseCommand):
    """
    Run daily (e.g. a Render cron job, alongside flag_overdue_placement_fees).
    """

    help = "Warns hosts with overdue guest house booking Success Fee invoices."

    def handle(self, *args, **options):
        warned = 0

        overdue_invoices = BookingInvoice.objects.filter(
            status=BookingInvoice.STATUS_PENDING,
        ).select_related("booking__guesthouse__host")

        for invoice in overdue_invoices:
            if invoice.is_overdue(WARNING_AFTER_DAYS):
                self._send_warning(invoice)
                warned += 1

        self.stdout.write(self.style.SUCCESS(f"Warned: {warned}."))

    def _send_warning(self, invoice):
        host = invoice.booking.guesthouse.host
        if not host.email:
            return

        send_mail(
            "Rooms4You: your Success Fee is overdue",
            (
                f"Hi {host.get_full_name() or host.username},\n\n"
                f"Your Success Fee of R{invoice.amount} for the booking at "
                f"\"{invoice.booking.guesthouse.name}\" is still unpaid. "
                f"Please settle this soon.\n\n"
                f"- The Rooms4You Team"
            ),
            None,
            [host.email],
            fail_silently=True,
        )
