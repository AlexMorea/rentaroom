"""
Founding Landlord programme - the pre-launch offer the street team sells:
every landlord who signs up before the tenant launch gets Gold (unlimited
listings) free until FOUNDING_LANDLORD_FREE_UNTIL, and their first tenant
placed through Rooms4You carries no success fee.

Dates are whole days in South African time (the settings hold plain
dates), so "free until 30 April" means until midnight SAST at the end of
30 April, whatever the server's own TIME_ZONE is.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

SAST = ZoneInfo("Africa/Johannesburg")

# Stored on the waived PlacementInvoice, and also how a landlord's one
# free placement is found again (so the perk can't be used twice).
FOUNDING_WAIVER_REASON = "Founding Landlord: first tenant free"


def _end_of_day(day):
    return datetime.combine(day, time.max, tzinfo=SAST)


def signup_deadline():
    return _end_of_day(settings.FOUNDING_LANDLORD_SIGNUP_DEADLINE)


def free_until():
    return _end_of_day(settings.FOUNDING_LANDLORD_FREE_UNTIL)


def programme_open(now=None):
    return (now or timezone.now()) <= signup_deadline()
