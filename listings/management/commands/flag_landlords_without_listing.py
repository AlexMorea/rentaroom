from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.push import notify_user
from listings.models import Profile
from utils.email import send_template_email


class Command(BaseCommand):
    """
    One-time nudge for a landlord who signed up but never posted a room -
    the manual, one-off version of this email (sent from the Afrihost
    webmail account) is what prompted adding this as a proper automated
    flow via Brevo. Dry-run by default - use --force to actually send.
    """

    help = (
        "Nudges landlords who signed up but haven't posted a listing yet. "
        "Dry-run by default - use --force to actually send."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually send the nudge. Without this, only reports who would get one.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        cutoff = timezone.now() - timezone.timedelta(
            days=settings.LANDLORD_NO_LISTING_NUDGE_DAYS
        )

        candidates = Profile.objects.filter(
            role="landlord",
            no_listing_nudge_sent_at__isnull=True,
            user__date_joined__lte=cutoff,
            user__is_active=True,
            user__rooms__isnull=True,
        ).select_related("user")

        self.stdout.write(f"{candidates.count()} landlord(s) to nudge.")

        if not force:
            for profile in candidates:
                self.stdout.write(f"  [would nudge] {profile.user.email}")
            self.stdout.write(self.style.WARNING("Dry run only - use --force to apply."))
            return

        sent = 0
        for profile in candidates:
            self._send_nudge(profile)
            profile.no_listing_nudge_sent_at = timezone.now()
            profile.save(update_fields=["no_listing_nudge_sent_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Nudged {sent} landlord(s)."))

    def _send_nudge(self, profile):
        user = profile.user
        if user.email:
            send_template_email(
                subject="Complete Your Rooms4You Listing - Free Pre-Launch Advertising",
                to_email=user.email,
                template="emails/complete_listing_nudge.html",
                context={
                    "user": user,
                    "app_url": "https://rooms4you.co.za/rooms/new/",
                    "year": timezone.now().year,
                },
            )
        notify_user(
            user,
            title="Add your first listing",
            body="You haven't posted a room yet - we're advertising listings free during pre-launch.",
            url="/rooms/new/",
        )
