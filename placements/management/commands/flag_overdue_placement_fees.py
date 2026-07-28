from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Membership
from placements.models import PlacementInvoice

# Days of an unpaid Success Fee invoice before each stage triggers.
# Warning gives the landlord a heads-up before anything happens to
# their account; suspension only fires after that grace period too.
WARNING_AFTER_DAYS = 7
SUSPEND_AFTER_DAYS = 14


class Command(BaseCommand):
    """
    Run daily (e.g. a second Render cron job, alongside check_move_ins).

    Stage 1 (day 7 unpaid): sends one warning email, doesn't touch the
    account. Stage 2 (day 14 unpaid): suspends the landlord's Membership
    using the SAME mechanism already used for membership non-payment
    (Membership.suspend_for_unpaid_placement_fee) - existing listings
    are left in place, but can_create_listing() blocks new ones and the
    landlord dashboard should surface why.

    SAFETY: actual suspension only happens if
    settings.PLACEMENT_FEE_AUTO_SUSPEND is True. It defaults to False
    (see rentaroom/settings.py), so installing this command does NOT
    start suspending real accounts - that's a conscious switch you flip
    when you're ready, not something that ships silently turned on.
    While the flag is off, this command still sends warning emails and
    reports what it WOULD suspend, so you can watch it run safely first.
    """

    help = "Warns about, and optionally suspends, landlords with overdue Success Fee invoices."

    def handle(self, *args, **options):
        auto_suspend = getattr(settings, "PLACEMENT_FEE_AUTO_SUSPEND", False)

        warned = 0
        suspended = 0
        would_suspend = 0

        overdue_invoices = PlacementInvoice.objects.filter(
            status=PlacementInvoice.STATUS_PENDING,
        ).select_related("placement__landlord")

        for invoice in overdue_invoices:
            days = invoice.days_pending
            landlord = invoice.placement.landlord

            if WARNING_AFTER_DAYS <= days < SUSPEND_AFTER_DAYS:
                self._send_warning(invoice, landlord)
                warned += 1

            elif days >= SUSPEND_AFTER_DAYS:
                if not auto_suspend:
                    would_suspend += 1
                    continue

                try:
                    membership = landlord.membership
                except Membership.DoesNotExist:
                    continue

                if membership.is_active:
                    membership.suspend_for_unpaid_placement_fee(invoice)
                    self._send_suspension_notice(invoice, landlord)
                    suspended += 1

        self.stdout.write(self.style.SUCCESS(
            f"Warned: {warned}. Suspended: {suspended}. "
            f"Would-suspend (auto-suspend OFF): {would_suspend}."
        ))

        if would_suspend and not auto_suspend:
            self.stdout.write(self.style.WARNING(
                f"{would_suspend} account(s) have fees {SUSPEND_AFTER_DAYS}+ days "
                f"overdue but PLACEMENT_FEE_AUTO_SUSPEND is False, so nothing was "
                f"suspended. Review /admin/placements/placementinvoice/ and flip "
                f"that setting when you're ready to enforce this automatically."
            ))

    def _send_warning(self, invoice, landlord):
        if not landlord.email:
            return
        send_mail(
            "Rooms4You: your Success Fee is overdue",
            (
                f"Hi {landlord.get_full_name() or landlord.username},\n\n"
                f"Your Success Fee of R{invoice.amount} for \"{invoice.placement.room.title}\" "
                f"is still unpaid. Please settle this soon to avoid your account being "
                f"suspended for new listings.\n\n"
                f"- The Rooms4You Team"
            ),
            None,
            [landlord.email],
            fail_silently=True,
        )

    def _send_suspension_notice(self, invoice, landlord):
        if not landlord.email:
            return
        send_mail(
            "Rooms4You: your account has been suspended",
            (
                f"Hi {landlord.get_full_name() or landlord.username},\n\n"
                f"Your Success Fee of R{invoice.amount} for \"{invoice.placement.room.title}\" "
                f"remained unpaid for {SUSPEND_AFTER_DAYS} days, so your account has been "
                f"suspended - you won't be able to add new listings until this is settled. "
                f"Your existing listings have not been deleted.\n\n"
                f"Please contact support@rooms4you.co.za to arrange payment and reactivate "
                f"your account.\n\n"
                f"- The Rooms4You Team"
            ),
            None,
            [landlord.email],
            fail_silently=True,
        )
