"""
Availability checking for guest house bookings.

The rule: a REQUEST never blocks other guests from requesting the same
dates - two people can both ask about the same weekend, same as real
life. Availability is only enforced at the moment a host CONFIRMS a
request. This avoids two problems at once:
  - false "unavailable" messages for dates that might still open up
    if the other inquiry falls through
  - actual double-bookings, since confirmation is the one moment that
    really commits the dates

Anything importing from this module should treat these two functions
as the single source of truth for "is this date range free" - don't
duplicate the conflict-checking query elsewhere.
"""

from datetime import timedelta

from django.utils import timezone

from .models import BlockedDate, Booking, BookingInvoice


def get_conflicting_bookings(guesthouse, check_in, check_out, exclude_booking_id=None):
    """Confirmed bookings for this guesthouse that overlap the given
    date range. Two ranges overlap if each one starts before the other
    ends."""
    qs = Booking.objects.filter(
        guesthouse=guesthouse,
        status=Booking.STATUS_CONFIRMED,
        check_in__lt=check_out,
        check_out__gt=check_in,
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    return qs


def get_conflicting_blocked_dates(guesthouse, check_in, check_out):
    """Host-blocked date ranges that overlap the given range - same
    overlap logic as confirmed bookings above."""
    return BlockedDate.objects.filter(
        guesthouse=guesthouse,
        start_date__lt=check_out,
        end_date__gt=check_in,
    )


def is_range_available(guesthouse, check_in, check_out, exclude_booking_id=None):
    """The actual availability check - used both when confirming a
    booking and when rendering the calendar so guests can see which
    dates are already taken before they even submit a request."""
    has_booking_conflict = get_conflicting_bookings(
        guesthouse, check_in, check_out, exclude_booking_id
    ).exists()
    has_block_conflict = get_conflicting_blocked_dates(
        guesthouse, check_in, check_out
    ).exists()
    return not (has_booking_conflict or has_block_conflict)


def get_unavailable_ranges(guesthouse, months_ahead=6):
    """All confirmed bookings + blocked dates for the next N months,
    for rendering on a calendar. Returns a list of (start, end) tuples
    - deliberately simple data, not model instances, since the
    calendar UI only needs the date ranges themselves."""
    today = timezone.localdate()
    horizon = today + timedelta(days=months_ahead * 30)

    bookings = Booking.objects.filter(
        guesthouse=guesthouse,
        status=Booking.STATUS_CONFIRMED,
        check_out__gte=today,
        check_in__lte=horizon,
    ).values_list("check_in", "check_out")

    blocks = BlockedDate.objects.filter(
        guesthouse=guesthouse,
        end_date__gte=today,
        start_date__lte=horizon,
    ).values_list("start_date", "end_date")

    return list(bookings) + list(blocks)


def confirm_booking(booking):
    """The actual confirmation action - checks for conflicts one more
    time (in case something changed between the host loading the page
    and clicking confirm), and if clear, confirms this booking and
    auto-declines any other pending requests that now overlap it.

    Returns (success: bool, error_message: str | None).
    """
    if booking.status != Booking.STATUS_REQUESTED:
        return False, "This booking is no longer pending - it may have already been decided."

    if not is_range_available(
        booking.guesthouse, booking.check_in, booking.check_out,
        exclude_booking_id=booking.id,
    ):
        return False, (
            "These dates are no longer available - another booking was "
            "confirmed for an overlapping date range."
        )

    booking.status = Booking.STATUS_CONFIRMED
    booking.decided_at = timezone.now()
    booking.save(update_fields=["status", "decided_at"])

    # Generate the success fee invoice now - confirming a booking IS
    # the success signal for a stay (unlike a room placement, which
    # needs a separate move-in confirmation weeks later since a lease
    # start is ambiguous in a way a booked check-in date isn't).
    BookingInvoice.objects.get_or_create(
        booking=booking,
        defaults={"amount": booking.expected_success_fee},
    )

    overlapping_requests = Booking.objects.filter(
        guesthouse=booking.guesthouse,
        status=Booking.STATUS_REQUESTED,
        check_in__lt=booking.check_out,
        check_out__gt=booking.check_in,
    ).exclude(pk=booking.id)

    for other in overlapping_requests:
        other.status = Booking.STATUS_DECLINED
        other.decline_reason = "These dates were booked by another guest."
        other.decided_at = timezone.now()
        other.save(update_fields=["status", "decline_reason", "decided_at"])

    return True, None