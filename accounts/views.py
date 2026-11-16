from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from listings.models import Profile

from .models import Membership


def landlord_only(request):
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        messages.error(request, "Profile missing.")
        return redirect("room_list")

    if profile.role == "landlord":
        return None

    if profile.role == "tenant":
        messages.error(
            request,
            "Only landlords can access memberships."
        )
        return redirect("room_list")

    if profile.role == "driver":
        messages.error(
            request,
            "Drivers do not have memberships."
        )
        return redirect("driver_dashboard")

    messages.error(request, "Access denied.")
    return redirect("room_list")


@login_required
def membership_view(request):
    """The Plans page: Free (what everyone has) and Pro, priced for this
    landlord's actual room count, with their founding discount applied."""
    from billing import pricing
    from billing.payfast import payments_enabled

    denied = landlord_only(request)
    if denied:
        return denied

    membership, _ = Membership.objects.get_or_create(user=request.user)
    membership.lapse_if_expired()

    rooms = pricing.room_count_for(request.user)
    band = pricing.band_for_rooms(rooms)
    discount = membership.current_discount_percent

    bands = [
        {
            "band": b,
            "monthly": pricing.pro_price(b, pricing.CYCLE_MONTHLY, discount),
            "annual": pricing.pro_price(b, pricing.CYCLE_ANNUAL, discount),
            "is_yours": b.code == band.code,
        }
        for b in pricing.PRO_BANDS
    ]

    return render(request, "accounts/membership.html", {
        "membership": membership,
        "rooms": rooms,
        "band": band,
        "bands": bands,
        "discount": discount,
        "monthly_price": pricing.pro_price(band, pricing.CYCLE_MONTHLY, discount),
        "annual_price": pricing.pro_price(band, pricing.CYCLE_ANNUAL, discount),
        "payments_enabled": payments_enabled(),
        "boosts_enabled": settings.BOOSTS_ENABLED,
        "boost_options": pricing.BOOST_OPTIONS,
        "free_boosts_per_month": pricing.PRO_FREE_BOOSTS_PER_MONTH,
        "payments": request.user.payments.exclude(status="pending")[:5],
    })
