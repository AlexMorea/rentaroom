"""
Boost rules. The trust line: you can pay for visibility, never for
trust - only a verified landlord can buy Pro or a Boost (so a scammer
can't pay to be seen), only a listing that's genuinely available and
recently confirmed can be boosted, and a boost is always labelled
"Featured".
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts import founding

from . import pricing
from .models import Boost


NOT_VERIFIED_MESSAGE = (
    "Only verified landlords can buy Pro or Boosts, so scammers can't pay to be seen. "
    "Verification is free."
)


def is_verified_landlord(user) -> bool:
    """The admin-checked landlord badge (Profile.is_verified_landlord).
    Payment never sets or changes it."""
    profile = getattr(user, "profile", None)
    return bool(profile is not None and profile.is_verified_landlord)


def boost_blocker(room) -> str | None:
    """Why this room can't be boosted right now, or None if it can."""
    if not settings.BOOSTS_ENABLED:
        return "Boosts open when Rooms4You launches to tenants."
    if not is_verified_landlord(room.owner):
        return NOT_VERIFIED_MESSAGE
    if not room.is_available or room.available_units <= 0:
        return "Only rooms with a vacancy can be boosted."
    if room.is_stale:
        return "Please confirm this listing is still accurate before boosting it."
    membership = getattr(room.owner, "membership", None)
    if membership is not None and not membership.can_create_listing():
        return "Your account is suspended."
    return None


def active_boost_for(room):
    return Boost.objects.filter(room=room).active().order_by("-ends_at").first()


def boost_window(room, days: int):
    """A new boost starts now, or straight after one already running -
    buying twice extends it instead of overlapping."""
    now = timezone.now()
    current = active_boost_for(room)
    starts = current.ends_at if current else now
    return starts, starts + timedelta(days=days)


def _month_start_sast():
    now = timezone.now().astimezone(founding.SAST)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def pro_credits_left(membership) -> int:
    if not membership.has_pro:
        return 0
    used = Boost.objects.filter(
        landlord_id=membership.user_id,
        source=Boost.SOURCE_PRO_CREDIT,
        created_at__gte=_month_start_sast(),
    ).count()
    return max(pricing.PRO_FREE_BOOSTS_PER_MONTH - used, 0)


def create_boost(*, room, source, days, payment=None) -> Boost:
    starts, ends = boost_window(room, days)
    return Boost.objects.create(
        room=room,
        landlord=room.owner,
        source=source,
        payment=payment,
        starts_at=starts,
        ends_at=ends,
    )


def featured_room_ids(room_ids_in_order, limit: int = pricing.FEATURED_SLOTS) -> list[int]:
    """
    Which rooms get pinned to the top of a results list: up to `limit`
    of the currently-boosted rooms among `room_ids_in_order` (the
    already-filtered search results). When more rooms are boosted than
    there are slots, the pinned set rotates every hour so every paying
    landlord gets a fair turn - and stays stable within the hour so
    pagination doesn't shuffle under a tenant's feet.
    """
    if not settings.BOOSTS_ENABLED:
        return []

    ids = list(room_ids_in_order)
    if not ids:
        return []

    # A landlord whose verification is withdrawn stops being Featured at
    # once, even mid-way through a boost they already paid for.
    boosted = set(
        Boost.objects.active()
        .filter(room_id__in=ids, landlord__profile__is_verified_landlord=True)
        .values_list("room_id", flat=True)
    )
    candidates = sorted(boosted)
    if len(candidates) <= limit:
        return candidates

    hour = int(timezone.now().timestamp() // 3600)
    offset = hour % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return rotated[:limit]
