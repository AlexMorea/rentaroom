"""
Applies a verified PayFast notification. Kept apart from the view so
the money logic is testable without HTTP, and idempotent: PayFast
re-sends ITNs until it gets a 200, so the same pf_payment_id must never
be applied twice.
"""
import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership
from accounts.push import notify_user
from listings.models import Room

from . import pricing
from .boosts import create_boost
from .models import Boost, Payment

logger = logging.getLogger(__name__)


def _payment_from_reference(m_payment_id: str):
    if not m_payment_id.startswith("R4Y-"):
        return None
    try:
        pk = int(m_payment_id.removeprefix("R4Y-"))
    except ValueError:
        return None
    return Payment.objects.filter(pk=pk).select_related("user").first()


def _apply_pro(payment: Payment):
    membership, _ = Membership.objects.get_or_create(user=payment.user)
    membership.extend_pro(
        band=payment.pro_band,
        cycle=payment.billing_cycle,
        months=pricing.cycle_months(payment.billing_cycle),
    )
    if payment.payfast_token:
        membership.payfast_token = payment.payfast_token
        membership.auto_renew = True
        membership.save(update_fields=["payfast_token", "auto_renew"])

    notify_user(
        payment.user,
        title="You're on Rooms4You Pro",
        body=f"Payment of R{payment.amount} received - thank you!",
        url=reverse("membership"),
    )


def _apply_boost(payment: Payment):
    option = pricing.BOOST_OPTIONS_BY_CODE.get(payment.boost_option)
    room = payment.room
    if option is None or room is None:
        logger.error("Boost payment %s has no room/option - needs staff attention", payment.pk)
        return
    create_boost(room=room, source=Boost.SOURCE_PAID, days=option.days, payment=payment)
    notify_user(
        payment.user,
        title="Your boost is live",
        body=f'"{room.title}" is now Featured for {option.label}.',
        url=reverse("landlord_rooms"),
    )


@transaction.atomic
def handle_notification(data: dict) -> str:
    """Returns a short outcome string (logged / used in tests)."""
    status = (data.get("payment_status") or "").upper()
    pf_payment_id = (data.get("pf_payment_id") or "").strip() or None
    token = (data.get("token") or "").strip()

    payment = _payment_from_reference(data.get("m_payment_id", ""))
    if payment is None:
        # A cancellation may arrive without our reference - match the
        # subscription by its token instead.
        if status == "CANCELLED" and token:
            Membership.objects.filter(payfast_token=token).update(auto_renew=False, payfast_token="")
            return "cancelled"
        return "unknown-payment"

    payment = Payment.objects.select_for_update().get(pk=payment.pk)

    if status == "CANCELLED":
        # Subscription cancelled (by the landlord in PayFast, or via our
        # API call). Pro already paid for carries on until paid_until.
        if payment.kind == Payment.KIND_PRO:
            Membership.objects.filter(user=payment.user).update(auto_renew=False, payfast_token="")
        if payment.status == Payment.STATUS_PENDING:
            payment.status = Payment.STATUS_CANCELLED
            payment.save(update_fields=["status"])
        return "cancelled"

    if status != "COMPLETE":
        if payment.status == Payment.STATUS_PENDING:
            payment.status = Payment.STATUS_FAILED
            payment.raw_notification = data
            payment.save(update_fields=["status", "raw_notification"])
        return "not-complete"

    if pf_payment_id and Payment.objects.filter(pf_payment_id=pf_payment_id).exists():
        return "duplicate"

    from .payfast import amount_matches

    if payment.status == Payment.STATUS_PENDING:
        target = payment
    elif payment.kind == Payment.KIND_PRO and payment.status == Payment.STATUS_COMPLETE:
        # A monthly/annual debit on an existing subscription.
        target = Payment.objects.create(
            user=payment.user,
            kind=Payment.KIND_PRO,
            amount=payment.amount,
            item_name=payment.item_name,
            pro_band=payment.pro_band,
            billing_cycle=payment.billing_cycle,
            discount_percent=payment.discount_percent,
            parent=payment,
        )
    else:
        return "ignored"

    if not amount_matches(target.amount, data.get("amount_gross", "")):
        logger.error("PayFast amount mismatch on payment %s: %s", target.pk, data.get("amount_gross"))
        target.status = Payment.STATUS_FAILED
        target.note = "Amount mismatch - check in PayFast"
        target.raw_notification = data
        target.save()
        return "amount-mismatch"

    target.status = Payment.STATUS_COMPLETE
    target.pf_payment_id = pf_payment_id
    target.payfast_token = token
    target.amount_fee = _decimal_or_none(data.get("amount_fee"))
    target.amount_net = _decimal_or_none(data.get("amount_net"))
    target.raw_notification = data
    target.completed_at = timezone.now()
    target.save()

    if target.kind == Payment.KIND_PRO:
        _apply_pro(target)
    else:
        _apply_boost(target)
    return "applied"


def _decimal_or_none(value):
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def room_for_landlord(user, room_id):
    return Room.objects.filter(pk=room_id, owner=user).first()
