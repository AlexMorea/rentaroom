from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Membership


@login_required
def membership_view(request):
    membership, _ = Membership.objects.get_or_create(user=request.user)

    if request.method == "POST":
        membership.payment_requested = True
        membership.payment_requested_at = timezone.now()
        membership.save()

        messages.success(
            request,
            "Payment request received. We will verify and activate your membership shortly."
        )

    return render(request, "accounts/membership.html", {
        "membership": membership
    })

@login_required
def upgrade_view(request):
    membership, _ = Membership.objects.get_or_create(user=request.user)

    if request.method == "POST":
        new_tier = request.POST.get("tier")

        allowed = ["starter", "bronze", "silver", "gold"]

        if new_tier in allowed:
            membership.tier = new_tier
            membership.save()
            messages.success(request, "Membership updated successfully.")
            return redirect("membership")

    return render(request, "accounts/upgrade.html", {
        "membership": membership
    })

@login_required
def payment_request_view(request):
    membership, _ = Membership.objects.get_or_create(user=request.user)

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
    membership, _ = Membership.objects.get_or_create(user=request.user)

    membership.payment_requested = True
    membership.payment_requested_at = timezone.now()
    membership.status = "pending"
    membership.save()

    messages.success(
        request,
        "Payment submitted. We will verify and activate your account shortly."
    )

    return redirect("dashboard")

@staff_member_required
def admin_membership_dashboard(request):
    pending = Membership.objects.filter(status="pending").order_by("-payment_requested_at")
    active = Membership.objects.filter(status="active")

    return render(request, "admin/membership_dashboard.html", {
        "pending": pending,
        "active": active,
    })

@staff_member_required
def approve_membership(request, pk):
    membership = Membership.objects.get(id=pk)

    tier = request.POST.get("tier", membership.tier)

    membership.activate_membership(tier=tier, admin_user=request.user)

    messages.success(request, "Membership approved and activated.")
    return redirect("admin_membership_dashboard")

def check_trial(self):
    if self.is_trial and self.is_trial_expired():
        self.is_active = False
        self.status = "suspended"
        self.save()

@staff_member_required
def reject_membership(request, pk):
    membership = Membership.objects.get(id=pk)

    membership.reject_payment()

    messages.warning(request, "Membership rejected.")
    return redirect("admin_membership_dashboard")

@login_required
def request_payment(request):
    membership = request.user.membership
    membership.mark_as_paid()
    return redirect('dashboard')

@login_required
def membership_payment_view(request, tier):

    tier = tier.lower()

    VALID_TIERS = ["bronze", "silver", "gold"]

    if tier not in VALID_TIERS:
        messages.error(request, "Invalid membership tier.")
        return redirect("membership")

    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    # 💰 Pricing
    prices = {
        "bronze": "R55",
        "silver": "R75",
        "gold": "R129"
    }

    if request.method == "POST":
        # 🧾 mark as pending upgrade (simple version)
        membership.requested_tier = tier
        membership.save()

        messages.success(
            request,
            f"✅ Payment submitted for {tier.title()} plan. We’ll verify and activate shortly."
        )
        return redirect("dashboard")

    return render(request, "accounts/payment_page.html", {
        "tier": tier,
        "price": prices[tier],
        "membership": membership
    })