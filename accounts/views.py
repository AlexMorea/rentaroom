from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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

    denied = landlord_only(request)
    if denied:
        return denied

    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    if membership.is_trial and membership.is_trial_expired():
        membership.is_active = False
        membership.status = "suspended"
        membership.save(update_fields=["is_active", "status"])

    return render(request, "accounts/membership.html", {
        "membership": membership,
        "listing_limit": membership.listing_limit(),
        "days_left": membership.days_left,
    })


@login_required
def upgrade_view(request):

    denied = landlord_only(request)
    if denied:
        return denied

    membership, _ = Membership.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        new_tier = request.POST.get("tier")

        allowed = ["starter", "bronze", "silver", "gold"]

        if new_tier in allowed:
            membership.tier = new_tier
            membership.save()

            messages.success(
                request,
                "Membership updated successfully."
            )
            return redirect("membership")

    return render(request, "accounts/upgrade.html", {
        "membership": membership
    })


@login_required
def payment_request_view(request):

    denied = landlord_only(request)
    if denied:
        return denied

    membership, _ = Membership.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        membership.payment_requested = True
        membership.payment_requested_at = timezone.now()
        membership.save()

        messages.success(
            request,
            "Payment request submitted. We will activate your account shortly."
        )
        return redirect("membership")

    return render(request, "accounts/payment_request.html", {
        "membership": membership
    })


@login_required
def confirm_payment(request):

    denied = landlord_only(request)
    if denied:
        return denied

    membership, _ = Membership.objects.get_or_create(
        user=request.user
    )

    membership.payment_requested = True
    membership.payment_requested_at = timezone.now()
    membership.status = "pending"
    membership.save()

    messages.success(
        request,
        "Payment submitted. We will verify and activate your account shortly."
    )

    return redirect("membership")


@staff_member_required
def admin_membership_dashboard(request):
    pending = Membership.objects.filter(
        status="pending"
    ).order_by("-payment_requested_at")

    active = Membership.objects.filter(
        status="active"
    )

    return render(request, "admin/membership_dashboard.html", {
        "pending": pending,
        "active": active,
    })


@staff_member_required
@require_POST
def approve_membership(request, pk):
    membership = get_object_or_404(Membership, id=pk)

    tier = request.POST.get(
        "tier",
        membership.tier
    )

    membership.activate_membership(
        tier=tier,
        admin_user=request.user
    )

    messages.success(
        request,
        "Membership approved and activated."
    )

    return redirect("admin_membership_dashboard")


@staff_member_required
@require_POST
def reject_membership(request, pk):
    membership = get_object_or_404(Membership, id=pk)
    membership.reject_payment()

    messages.warning(
        request,
        "Membership rejected."
    )

    return redirect("admin_membership_dashboard")

@login_required
def membership_payment_view(request, tier):

    denied = landlord_only(request)
    if denied:
        return denied

    VALID_TIERS = {
        "bronze": "R49",
        "silver": "R99",
        "gold": "R199"
    }

    tier = tier.lower()

    if tier not in VALID_TIERS:
        messages.error(
            request,
            "Invalid membership tier."
        )
        return redirect("membership")

    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    if membership.status == "pending":
        messages.warning(
            request,
            "You already have a payment under review."
        )
        return redirect("membership")

    if membership.tier == tier and membership.status == "active":
        messages.info(
            request,
            f"You are already subscribed to {tier.title()}4You."
        )
        return redirect("membership")

    if request.method == "POST":

        proof = request.FILES.get("payment_proof")

        if not proof:
            messages.error(
                request,
                "Please upload proof of payment."
            )
            return redirect(
                "membership_payment",
                tier=tier
            )

        if proof.size > 5 * 1024 * 1024:
            messages.error(
                request,
                "Proof of payment must be under 5MB."
            )
            return redirect(
                "membership_payment",
                tier=tier
            )

        allowed = [".jpg", ".jpeg", ".png", ".pdf"]

        filename = proof.name.lower()

        if not any(
            filename.endswith(ext)
            for ext in allowed
        ):
            messages.error(
                request,
                "Only JPG, PNG or PDF files are allowed."
            )
            return redirect(
                "membership_payment",
                tier=tier
            )

        with transaction.atomic():
            membership.mark_payment_submitted(
                tier,
                proof
            )

        messages.success(
            request,
            "✅ Payment submitted successfully. Verification may take a few hours."
        )

        return redirect("membership")

    return render(
        request,
        "accounts/payment_page.html",
        {
            "tier": tier,
            "price": VALID_TIERS[tier],
            "membership": membership
        }
    )