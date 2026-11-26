import logging

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

logger = logging.getLogger(__name__)


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

        # Only rooms claiming a vacancy matter here. A full room isn't
        # promising anything a tenant could act on, so it's never nudged
        # or hidden for going quiet.
        candidates = Room.objects.filter(
            is_available=True, available_units__gt=0, last_confirmed_at__lte=stale_cutoff
        ).select_related("owner", "owner__profile")

        # Never hide a room without warning: it must be unconfirmed for
        # LISTING_AUTO_HIDE_DAYS *and* have ignored a nudge for at least
        # LISTING_HIDE_GRACE_DAYS. A room that has never been nudged gets
        # the nudge first, however old its last confirmation is.
        # Hiding is opt-in (LISTING_AUTO_HIDE_ENABLED, off by default): an
        # unconfirmed room stays on Browse, labelled and ranked lower, and
        # its landlord keeps getting a nudge every LISTING_STALE_DAYS.
        grace_cutoff = now - timezone.timedelta(days=settings.LISTING_HIDE_GRACE_DAYS)
        if settings.LISTING_AUTO_HIDE_ENABLED:
            to_hide = candidates.filter(
                last_confirmed_at__lte=auto_hide_cutoff,
                last_nudge_sent_at__isnull=False,
                last_nudge_sent_at__lte=grace_cutoff,
            )
        else:
            to_hide = candidates.none()
        # Don't re-nudge every run: only once per LISTING_STALE_DAYS.
        to_nudge = candidates.exclude(pk__in=to_hide.values("pk")).filter(
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

        # Each landlord's email is tried on its own: one failure used to
        # stop the whole run, leaving other landlords un-nudged - or, when
        # hiding, a room hidden without its landlord ever being told.
        nudged = 0
        for room in to_nudge:
            try:
                self._send_nudge(room)
            except Exception:  # noqa: BLE001 - retried on the next daily run
                logger.exception("Could not send the confirm nudge for room %s", room.id)
                continue
            room.last_nudge_sent_at = now
            room.save(update_fields=["last_nudge_sent_at"])
            nudged += 1

        hidden = 0
        for room in to_hide:
            days = room.days_since_confirmed
            # Keep available_units so reactivating restores the vacancy.
            room.is_available = False
            room.save(update_fields=["is_available"])
            try:
                self._send_auto_hidden(room, days)
            except Exception:  # noqa: BLE001 - the room is paused either way
                logger.exception("Could not tell the landlord room %s was paused", room.id)
            hidden += 1

        self.stdout.write(self.style.SUCCESS(f"Nudged {nudged} listing(s), auto-hid {hidden} listing(s)."))

    def _send_nudge(self, room):
        context = {
            "room": room,
            "days": room.days_since_confirmed,
            "auto_hide_days": settings.LISTING_AUTO_HIDE_DAYS,
            "auto_hide_enabled": settings.LISTING_AUTO_HIDE_ENABLED,
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
