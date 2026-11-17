from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from accounts.push import notify_user
from listings.models import Profile, Room
from utils.email import send_template_email

# Rotates weekly (indexed by ISO week number) rather than randomly, so
# every landlord sees the same tip in the same week - no extra state to
# track, and it means "did you see this week's tip?" is a coherent
# question if support ever needs to reference one.
LANDLORD_TIPS = [
    "Listings with at least three clear photos get far more enquiries than "
    "listings without them. Photos taken on a phone in daylight are all you need.",
    "Try to reply within a few hours. Tenants usually contact several "
    "landlords at once, and the first landlord to reply is often the one "
    "who gets the viewing.",
    "Make sure the rent and deposit on your listing match what you ask for "
    "at the viewing. A difference between the two is the most common reason "
    "tenants report a listing as misleading.",
    "Confirming that your room is still available takes one tap from your "
    "dashboard, and it keeps your listing ranking well in search.",
    "If you use WhatsApp, add your number to the listing. Most tenants prefer "
    "it to a phone call for their first message.",
    "Name the suburb and nearby landmarks, such as a taxi rank, mall or "
    "school, in your description. Tenants can judge the distance to work "
    "without you sharing your street address.",
    "Say what the rent includes, such as water, electricity or Wi-Fi, in the "
    "description. It's the question tenants ask most, so answering it upfront "
    "saves everyone time.",
]


class Command(BaseCommand):
    help = (
        "Send each landlord a weekly performance digest (views/contacts/"
        "favourites) plus stale-listing callouts and a rotating tip. "
        "Dry-run by default - use --force to actually send."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually send the digest. Without this, only reports who would get one.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        since = timezone.now() - timezone.timedelta(days=7)
        tip = LANDLORD_TIPS[timezone.now().isocalendar()[1] % len(LANDLORD_TIPS)]

        landlords = (
            Profile.objects.filter(role="landlord", user__rooms__isnull=False)
            .select_related("user")
            .distinct()
        )

        self.stdout.write(f"{landlords.count()} landlord(s) with at least one listing.")

        if not force:
            for profile in landlords:
                self.stdout.write(f"  [would email] {profile.user.username}")
            self.stdout.write(self.style.WARNING("Dry run only - use --force to apply."))
            return

        sent = 0
        for profile in landlords:
            self._send_digest(profile.user, since, tip)
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} landlord digest(s)."))

    def _send_digest(self, user, since, tip):
        # distinct=True on every Count here is load-bearing, not
        # decorative: annotating roomstat and favorited_by (two separate
        # reverse relations) in the same query without it silently
        # inflates each count by the other relation's row count via the
        # join fan-out - e.g. 1 real favorite reads back as 4 once a room
        # has 4 unrelated RoomStat rows. Verified against raw SQL during
        # development; see the same latent issue in compute_scores.py.
        rooms = Room.objects.filter(owner=user).annotate(
            views_count=Count(
                "roomstat",
                filter=Q(roomstat__stat_type="view", roomstat__created_at__gte=since),
                distinct=True,
            ),
            contacts_count=Count(
                "roomstat",
                filter=Q(roomstat__stat_type__startswith="contact", roomstat__created_at__gte=since),
                distinct=True,
            ),
            favorites_count=Count(
                "favorited_by", filter=Q(favorited_by__created_at__gte=since), distinct=True
            ),
        )

        totals = {
            "views": sum(r.views_count for r in rooms),
            "contacts": sum(r.contacts_count for r in rooms),
            "favorites": sum(r.favorites_count for r in rooms),
        }
        stale_rooms = [r for r in rooms if r.is_stale]

        context = {
            "user": user,
            "rooms": rooms,
            "totals": totals,
            "stale_rooms": stale_rooms,
            "tip": tip,
            "year": timezone.now().year,
        }

        if user.email:
            send_template_email(
                subject="Your week on Rooms4You",
                to_email=user.email,
                template="emails/landlord_weekly_digest.html",
                context=context,
            )

        body = f"{totals['contacts']} contact(s), {totals['views']} view(s) this week."
        if stale_rooms:
            body += f" {len(stale_rooms)} listing(s) need confirming."

        notify_user(
            user,
            title="Your weekly listing summary",
            body=body,
            url=reverse("landlord_rooms"),
        )
