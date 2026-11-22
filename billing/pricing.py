"""
Rooms4You pricing - the single place prices live.

The model, in one line: listing is free forever; landlords pay for Pro
(tools, priced by how many rooms they run) and for Boosts (paid
visibility). Trust - the verified badge, listing at all - is never for
sale.

Pro is priced by ROOMS, not listings: one listing can cover several
identical units (Room.total_units), so "rooms" = the sum of total_units
across everything the landlord has listed.
"""
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

CYCLE_MONTHLY = "monthly"
CYCLE_ANNUAL = "annual"
CYCLES = (CYCLE_MONTHLY, CYCLE_ANNUAL)

# Annual = pay for 10 months, get 12.
ANNUAL_MONTHS_CHARGED = 10

# Founding landlords: this % off Pro for their first
# FOUNDING_DISCOUNT_MONTHS of paid Pro, counted from the end of the free
# founding period (settings.FOUNDING_LANDLORD_FREE_UNTIL), so 30 April
# 2027 -> 30 April 2028. See Membership.founding_lock_active.
FOUNDING_DISCOUNT_PERCENT = 50
FOUNDING_DISCOUNT_MONTHS = 12

# A founding landlord whose paid Pro lapses keeps their locked price for
# this many days, so one failed debit order doesn't cost them the lock.
FOUNDING_LOCK_GRACE_DAYS = 30


@dataclass(frozen=True)
class ProBand:
    code: str
    label: str
    max_rooms: int | None  # None = no upper limit
    monthly_price: Decimal


PRO_BANDS = (
    ProBand("small", "Up to 5 rooms", 5, Decimal(49)),
    ProBand("medium", "6 to 15 rooms", 15, Decimal(99)),
    ProBand("large", "16+ rooms", None, Decimal(199)),
)
PRO_BANDS_BY_CODE = {band.code: band for band in PRO_BANDS}


@dataclass(frozen=True)
class BoostOption:
    code: str
    label: str
    days: int
    price: Decimal


BOOST_OPTIONS = (
    BoostOption("week", "7 days", 7, Decimal(29)),
    BoostOption("month", "30 days", 30, Decimal(79)),
)
BOOST_OPTIONS_BY_CODE = {option.code: option for option in BOOST_OPTIONS}

# Pro includes this many free 7-day boosts per calendar month.
PRO_FREE_BOOSTS_PER_MONTH = 1
PRO_FREE_BOOST_DAYS = 7

# At most this many boosted rooms are pinned to the top of one results
# page, so search stays useful (other boosted rooms rotate in hourly).
FEATURED_SLOTS = 3


def room_count_for(user) -> int:
    from django.db.models import Sum

    from listings.models import Room

    total = Room.objects.filter(owner=user).aggregate(n=Sum("total_units"))["n"]
    return int(total or 0)


def band_for_rooms(rooms: int) -> ProBand:
    for band in PRO_BANDS:
        if band.max_rooms is None or rooms <= band.max_rooms:
            return band
    return PRO_BANDS[-1]


def apply_discount(amount: Decimal, percent: int) -> Decimal:
    """Whole rands, rounded down in the landlord's favour (R49 at 50%
    is R24, not R24.50)."""
    if not percent:
        return amount
    discounted = amount * (Decimal(100) - Decimal(percent)) / Decimal(100)
    return discounted.quantize(Decimal(1), rounding=ROUND_DOWN)


def pro_price(band: ProBand, cycle: str, discount_percent: int = 0) -> Decimal:
    monthly = apply_discount(band.monthly_price, discount_percent)
    if cycle == CYCLE_ANNUAL:
        return monthly * ANNUAL_MONTHS_CHARGED
    return monthly


def cycle_months(cycle: str) -> int:
    return 12 if cycle == CYCLE_ANNUAL else 1
