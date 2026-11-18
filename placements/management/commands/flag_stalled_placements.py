from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from accounts.push import notify_user
from placements.models import Placement
from utils.email import send_template_email
from utils.whatsapp import send_whatsapp_template


class Command(BaseCommand):
    """
    Runs daily from the in-process scheduler.

    An enquiry that has sat in an early status (Interested, Viewing
    Scheduled/Completed, Approved) for PLACEMENT_STALL_DAYS is easy to
    lose track of, so both sides get one "where are we with this?"
    reminder per stall (stall_nudge_sent_at).

    Grouped per person: a tenant waiting on four rooms gets ONE email
    listing all four, not four emails, and the same for landlords. Only
    real enquiries exist as placements (see Placement.record_interest),
    so nobody hears about a room they merely viewed or tapped Call on.
    """

    help = "Sends one grouped reminder per person about enquiries that have gone quiet."

    def handle(self, *args, **options):
        threshold = getattr(settings, "PLACEMENT_STALL_DAYS", 7)

        candidates = Placement.objects.filter(
            status__in=Placement.STALLABLE_STATUSES,
            stall_nudge_sent_at__isnull=True,
        ).select_related("tenant", "landlord", "room")
        stalled = [p for p in candidates if p.is_stalled(threshold)]

        by_tenant, by_landlord = defaultdict(list), defaultdict(list)
        for placement in stalled:
            by_tenant[placement.tenant].append(placement)
            by_landlord[placement.landlord].append(placement)

        for tenant, placements in by_tenant.items():
            self._nudge(tenant, placements, is_tenant=True)
        for landlord, placements in by_landlord.items():
            self._nudge(landlord, placements, is_tenant=False)

        if stalled:
            Placement.objects.filter(pk__in=[p.pk for p in stalled]).update(stall_nudge_sent_at=timezone.now())

        self.stdout.write(self.style.SUCCESS(
            f"{len(stalled)} stalled enquiry(ies): reminded {len(by_tenant)} tenant(s) "
            f"and {len(by_landlord)} landlord(s)."
        ))

    def _nudge(self, person, placements, *, is_tenant):
        count = len(placements)
        first = placements[0].room.title
        if is_tenant:
            subject = (f'Still interested in "{first}"?' if count == 1
                       else f"Still interested in these {count} rooms?")
            template = "emails/placement_stalled_tenant.html"
            push_title = "Still interested?"
            push_body = (f'Your enquiry on "{first}" needs an update.' if count == 1
                         else f"{count} of your enquiries need an update.")
            url = reverse("placements:tenant_dashboard")
        else:
            subject = (f'An enquiry about "{first}" is waiting on you' if count == 1
                       else f"{count} enquiries are waiting on you")
            template = "emails/placement_stalled_landlord.html"
            push_title = "An enquiry needs an update" if count == 1 else "Enquiries need an update"
            push_body = (f'"{first}" has an enquiry waiting on you. Tap to follow up.' if count == 1
                         else f"{count} enquiries are waiting on you. Tap to follow up.")
            url = reverse("placements:landlord_dashboard")

        if person.email:
            try:
                send_template_email(
                    subject=subject,
                    to_email=person.email,
                    template=template,
                    context={
                        "person": person,
                        "placements": placements,
                        "threshold_days": getattr(settings, "PLACEMENT_STALL_DAYS", 7),
                        "year": timezone.now().year,
                    },
                )
            except Exception:  # noqa: BLE001
                self.stderr.write(f"Could not email user {person.pk} about stalled enquiries")
        notify_user(person, title=push_title, body=push_body, url=url)
        if hasattr(person, "profile"):
            send_whatsapp_template(
                person.profile,
                settings.WHATSAPP_TEMPLATE_PLACEMENT_STALLED,
                params=[first if count == 1 else f"{count} rooms"],
            )
