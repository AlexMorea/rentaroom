import logging
from urllib.parse import parse_qsl

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Membership
from listings.models import Room
from listings.views.helpers import is_landlord

from . import payfast, pricing
from .boosts import (
    NOT_VERIFIED_MESSAGE,
    active_boost_for,
    boost_blocker,
    create_boost,
    is_verified_landlord,
    pro_credits_left,
)
from .models import Boost, Payment
from .services import handle_notification

logger = logging.getLogger(__name__)


def _day(value, fmt="j F Y") -> str:
    return date_format(timezone.localtime(value), fmt)


def _absolute(path: str) -> str:
    return f"{settings.PAYFAST_SITE_URL}{path}"


def _buyer_fields(user) -> dict:
    return {
        "name_first": (user.first_name or "")[:100],
        "name_last": (user.last_name or "")[:100],
        "email_address": (user.email or "")[:100],
    }


def _render_checkout(request, payment: Payment, extra: dict):
    fields = payfast.checkout_fields({
        "return_url": _absolute(reverse("billing:payment_return", args=[payment.pk])),
        "cancel_url": _absolute(reverse("billing:payment_cancelled", args=[payment.pk])),
        "notify_url": _absolute(reverse("billing:payfast_notify")),
        **_buyer_fields(request.user),
        "m_payment_id": payment.m_payment_id,
        "amount": payfast.format_amount(payment.amount),
        "item_name": payment.item_name,
        **extra,
    })
    return render(request, "billing/redirect_to_payfast.html", {
        "action": payfast.process_url(),
        "fields": fields,
        "payment": payment,
        "sandbox": settings.PAYFAST_SANDBOX,
    })


# ---------------------------------------------------------------------
# Pro
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_landlord)
@require_POST
def pro_checkout(request):
    if not payfast.payments_enabled():
        messages.info(request, "Online payments open soon, and nothing is due right now.")
        return redirect("membership")

    membership, _ = Membership.objects.get_or_create(user=request.user)

    if membership.on_pro_trial:
        messages.info(
            request,
            f"Pro is free for you until {_day(membership.trial_end)}, "
            "so there's nothing to pay yet.",
        )
        return redirect("membership")

    if membership.auto_renew and membership.payfast_token:
        messages.info(request, "You already have an active Pro subscription.")
        return redirect("membership")

    if not is_verified_landlord(request.user):
        messages.info(request, NOT_VERIFIED_MESSAGE)
        return redirect("membership")

    cycle = request.POST.get("cycle", pricing.CYCLE_MONTHLY)
    if cycle not in pricing.CYCLES:
        cycle = pricing.CYCLE_MONTHLY

    band = pricing.band_for_rooms(pricing.room_count_for(request.user))
    discount = membership.current_discount_percent
    amount = pricing.pro_price(band, cycle, discount)

    payment = Payment.objects.create(
        user=request.user,
        kind=Payment.KIND_PRO,
        amount=amount,
        item_name=f"Rooms4You Pro ({band.label}, {cycle})",
        pro_band=band.code,
        billing_cycle=cycle,
        discount_percent=discount,
    )

    return _render_checkout(request, payment, {
        "subscription_type": 1,
        "recurring_amount": payfast.format_amount(amount),
        "frequency": payfast.FREQUENCY_ANNUAL if cycle == pricing.CYCLE_ANNUAL else payfast.FREQUENCY_MONTHLY,
        "cycles": 0,
    })


@login_required
@user_passes_test(is_landlord)
@require_POST
def cancel_pro(request):
    membership = get_object_or_404(Membership, user=request.user)

    if not (membership.auto_renew and membership.payfast_token):
        messages.info(request, "You don't have a recurring Pro subscription to cancel.")
        return redirect("membership")

    if payfast.cancel_subscription(membership.payfast_token):
        membership.auto_renew = False
        membership.payfast_token = ""
        membership.save(update_fields=["auto_renew", "payfast_token"])
        until = f" until {_day(membership.paid_until)}" if membership.paid_until else ""
        messages.success(request, f"Your subscription is cancelled. You keep Pro{until}, then move to Free.")
    else:
        logger.error("Pro cancel failed for user %s - needs staff follow-up", request.user.pk)
        messages.error(
            request,
            "We couldn't reach PayFast to cancel just now. Please try again in a few minutes, "
            "or email support@rooms4you.co.za and we'll cancel it for you.",
        )
    return redirect("membership")


# ---------------------------------------------------------------------
# Boosts
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_landlord)
def boost_room(request, room_id):
    room = get_object_or_404(Room, pk=room_id, owner=request.user)
    membership, _ = Membership.objects.get_or_create(user=request.user)
    blocker = boost_blocker(room)
    credits = pro_credits_left(membership)

    if request.method == "POST" and not blocker:
        choice = request.POST.get("option", "")

        if choice == "pro_credit":
            if credits <= 0:
                messages.error(request, "You've used this month's free Pro boosts.")
                return redirect("billing:boost_room", room_id=room.pk)
            boost = create_boost(room=room, source=Boost.SOURCE_PRO_CREDIT, days=pricing.PRO_FREE_BOOST_DAYS)
            messages.success(request, f'"{room.title}" is Featured until {_day(boost.ends_at, "j F")}.')
            return redirect("landlord_rooms")

        option = pricing.BOOST_OPTIONS_BY_CODE.get(choice)
        if option is None:
            messages.error(request, "Please choose a boost.")
            return redirect("billing:boost_room", room_id=room.pk)

        if not payfast.payments_enabled():
            messages.info(request, "Online payments open soon.")
            return redirect("billing:boost_room", room_id=room.pk)

        payment = Payment.objects.create(
            user=request.user,
            kind=Payment.KIND_BOOST,
            amount=option.price,
            item_name=f"Boost: {room.title[:60]} ({option.label})",
            room=room,
            boost_option=option.code,
        )
        return _render_checkout(request, payment, {})

    return render(request, "billing/boost_room.html", {
        "room": room,
        "blocker": blocker,
        "options": pricing.BOOST_OPTIONS,
        "credits": credits,
        "has_pro": membership.has_pro,
        "free_boost_days": pricing.PRO_FREE_BOOST_DAYS,
        "active_boost": active_boost_for(room),
        "payments_enabled": payfast.payments_enabled(),
    })


# ---------------------------------------------------------------------
# PayFast return / cancel / notify
# ---------------------------------------------------------------------
@login_required
def payment_return(request, payment_id):
    """Where PayFast sends the browser after paying. Changes nothing -
    only the verified ITN completes a payment - it just tells the
    landlord what's happening."""
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    if payment.status == Payment.STATUS_COMPLETE:
        messages.success(request, "Payment received. Thank you!")
    else:
        messages.info(request, "Thanks! We're confirming your payment with PayFast, which usually takes less than a minute.")
    return redirect("membership" if payment.kind == Payment.KIND_PRO else "landlord_rooms")


@login_required
def payment_cancelled(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    if payment.status == Payment.STATUS_PENDING:
        payment.status = Payment.STATUS_CANCELLED
        payment.save(update_fields=["status"])
    messages.info(request, "Payment cancelled. You haven't been charged.")
    return redirect("membership" if payment.kind == Payment.KIND_PRO else "landlord_rooms")


@csrf_exempt
@require_POST
def payfast_notify(request):
    pairs = parse_qsl(request.body.decode("utf-8"), keep_blank_values=True)

    if not payfast.itn_signature_valid(pairs):
        logger.warning("PayFast ITN rejected: bad signature")
        return HttpResponseBadRequest("bad signature")

    data = dict(pairs)
    is_cancellation = (data.get("payment_status") or "").upper() == "CANCELLED"

    # PayFast's validate endpoint only confirms *payments* - it answers
    # "not valid" for a subscription-cancelled notification. A
    # cancellation can only switch auto-renew off (it never grants Pro or
    # money), so for those the passphrase signature above is enough.
    # Anything that could activate a purchase must pass both checks.
    if not is_cancellation and not payfast.itn_confirmed_by_payfast(pairs):
        logger.warning("PayFast ITN rejected: not confirmed by PayFast")
        return HttpResponseBadRequest("not confirmed")

    if data.get("merchant_id", settings.PAYFAST_MERCHANT_ID) != settings.PAYFAST_MERCHANT_ID:
        logger.warning("PayFast ITN rejected: merchant mismatch")
        return HttpResponseBadRequest("merchant mismatch")

    outcome = handle_notification(data)
    logger.info("PayFast ITN %s: %s", data.get("m_payment_id"), outcome)
    return HttpResponse("OK")
