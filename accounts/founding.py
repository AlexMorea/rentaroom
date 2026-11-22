"""
Founding Landlord programme - the pre-launch offer the street team sells:
every landlord who signs up before the tenant launch gets Pro free until
FOUNDING_LANDLORD_FREE_UNTIL, then Pro at the founding discount
(billing.pricing.FOUNDING_DISCOUNT_PERCENT) for their first
billing.pricing.FOUNDING_DISCOUNT_MONTHS months, while they stay
subscribed. Listing itself is free for everyone, forever.

Dates are whole days in South African time (the settings hold plain
dates), so "free until 30 April" means until midnight SAST at the end of
30 April, whatever the server's own TIME_ZONE is.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

SAST = ZoneInfo("Africa/Johannesburg")

# Stored on a waived PlacementInvoice. Only reachable while the (now
# switched-off) room success fee is enabled - see
# settings.PLACEMENT_SUCCESS_FEE_ENABLED.
FOUNDING_WAIVER_REASON = "Founding Landlord: first tenant free"


def _end_of_day(day):
    return datetime.combine(day, time.max, tzinfo=SAST)


def signup_deadline():
    return _end_of_day(settings.FOUNDING_LANDLORD_SIGNUP_DEADLINE)


def free_until():
    return _end_of_day(settings.FOUNDING_LANDLORD_FREE_UNTIL)


def discount_until():
    """End of the founding discount window: FOUNDING_DISCOUNT_MONTHS
    calendar months after the free founding period ends (30 April 2027
    -> end of 30 April 2028)."""
    import calendar

    from billing.pricing import FOUNDING_DISCOUNT_MONTHS

    start = settings.FOUNDING_LANDLORD_FREE_UNTIL
    month_index = start.month - 1 + FOUNDING_DISCOUNT_MONTHS
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return _end_of_day(start.replace(year=year, month=month, day=day))


def programme_open(now=None):
    return (now or timezone.now()) <= signup_deadline()
