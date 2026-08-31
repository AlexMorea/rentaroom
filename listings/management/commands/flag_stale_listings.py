from django.conf import settings
from django.core import signing
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.push import notify_user
from listings.models import Room
from utils.email import send_template_email

SITE_URL = "https://www.rooms4you.co.za"


def _sign(room_id: int, action: str) -> str:
    return signing.dumps({"room_id": room_id, "action": action}, salt="room-availability-confirm")


def _link(room_id: int, action: str) -> str:
    token = _sign(room_id, action)
    return f"{SITE_URL}{reverse('confirm_availability_via_link', args=[token])}"


class Command(BaseCommand):
    help = (
        "Nudge landlords to confirm still-available listings that have gone "
        "quiet, and auto-hide ones that never respond. Dry-run by default - "
        "use --force to actually send notifications and change data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually send nudges/auto-hide. Without this, only reports what would happen.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        now = timezone.now()
        stale_cutoff = now - timezone.timedelta(days=settings.LISTING_STALE_DAYS)
        auto_hide_cutoff = now - timezone.timedelta(days=settings.LISTING_AUTO_HIDE_DAYS)

        # Only rooms currently claiming to be available are this command's
        # concern - a room the landlord already marked occupied isn't
        # "stale", it's just correctly not-available, and naturally drops
        # out of this queryset the moment it's auto-hidden below (is_available
        # flips to False), so there's no separate "already handled" flag needed.
        candidates = Room.objects.filter(
            is_available=True, last_confirmed_at__lte=stale_cutoff
        ).select_related("owner", "owner__profile")

        to_hide = candidates.filter(last_confirmed_at__lte=auto_hide_cutoff)
        # Don't re-nudge every single run once already stale - only after
        # another full LISTING_STALE_DAYS has passed since the last nudge
        # (or if we've never nudged this one before).
        to_nudge = candidates.exclude(last_confirmed_at__lte=auto_hide_cutoff).filter(
            Q(last_nudge_sent_at__isnull=True) | Q(last_nudge_sent_at__lte=stale_cutoff)
        )

        self.stdout.write(f"{to_nudge.count()} listing(s) to nudge, {to_hide.count()} to auto-hide.")

        if not force:
            for room in to_nudge:
                self.stdout.write(f"  [would nudge] #{room.id} {room.title} ({room.days_since_confirmed}d)")
            for room in to_hide:
                self.stdout.write(f"  [would hide]  #{room.id} {room.title} ({room.days_since_confirmed}d)")
            self.stdout.write(self.style.WARNING("Dry run only - use --force to apply."))
            return

        nudged = 0
        for room in to_nudge:
            self._send_nudge(room)
            room.last_nudge_sent_at = now
            room.save(update_fields=["last_nudge_sent_at"])
            nudged += 1

        hidden = 0
        for room in to_hide:
            days = room.days_since_confirmed
            room.is_available = False
            room.available_units = 0
            room.save(update_fields=["is_available", "available_units"])
            self._send_auto_hidden(room, days)
            hidden += 1

        self.stdout.write(self.style.SUCCESS(f"Nudged {nudged} listing(s), auto-hid {hidden} listing(s)."))

    def _send_nudge(self, room):
        context = {
            "room": room,
            "days": room.days_since_confirmed,
            "auto_hide_days": settings.LISTING_AUTO_HIDE_DAYS,
            "confirm_url": _link(room.id, "confirm"),
            "vacate_url": _link(room.id, "vacate"),
            "year": timezone.now().year,
        }
        if room.owner.email:
            send_template_email(
                subject=f'Is "{room.title}" still available?',
                to_email=room.owner.email,
                template="emails/confirm_availability.html",
                context=context,
            )
        notify_user(
            room.owner,
            title="Please confirm your listing",
            body=f'Is "{room.title}" still available? Tap to confirm.',
            url=reverse("landlord_rooms"),
        )

    def _send_auto_hidden(self, room, days):
        context = {
            "room": room,
            "days": days,
            "reactivate_url": _link(room.id, "confirm"),
            "year": timezone.now().year,
        }
        if room.owner.email:
            send_template_email(
                subject=f'We\'ve paused "{room.title}"',
                to_email=room.owner.email,
                template="emails/listing_auto_hidden.html",
                context=context,
            )
        notify_user(
            room.owner,
            title="A listing was paused",
            body=f'"{room.title}" was hidden after {days} days unconfirmed. Tap to reactivate.',
            url=reverse("landlord_rooms"),
        )
