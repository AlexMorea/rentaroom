from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from listings.views import is_landlord

from .forms import MoveInConfirmationForm, PlacementUpdateForm
from .models import Placement


def is_tenant(user):
    return hasattr(user, "profile") and user.profile.role == "tenant"


# ---------------------------------------------------------------------
# Landlord dashboard
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_landlord)
def landlord_dashboard(request):
    placements = (
        Placement.objects.filter(landlord=request.user)
        .select_related("tenant", "room", "invoice")
        .prefetch_related("status_history")
    )

    active_placements = placements.exclude(
        status__in=[Placement.STATUS_PAID, Placement.STATUS_CANCELLED]
    )

    return render(request, "placements/landlord_dashboard.html", {
        "active_placements": active_placements,
        "all_placements": placements,
    })


@login_required
@user_passes_test(is_landlord)
def update_placement(request, placement_id):
    placement = get_object_or_404(Placement, id=placement_id, landlord=request.user)

    if request.method == "POST":
        form = PlacementUpdateForm(request.POST, instance=placement)
        if form.is_valid():
            form.save()
            messages.success(request, "Placement updated.")
            return redirect("placements:landlord_dashboard")
    else:
        form = PlacementUpdateForm(instance=placement)

    return render(request, "placements/update_placement.html", {
        "placement": placement,
        "form": form,
    })


@login_required
@user_passes_test(is_landlord)
@require_POST
def report_tenant_unreachable(request, placement_id):
    """
    "This tenant has gone AWOL" - a landlord-triggered flag for a
    placement that's already Moved In, filed as a FraudReport for staff
    triage (see Placement.flag_tenant_unreachable).
    """
    placement = get_object_or_404(Placement, id=placement_id, landlord=request.user)

    if placement.status != Placement.STATUS_MOVED_IN:
        messages.error(request, "This can only be reported for a moved-in placement.")
        return redirect("placements:landlord_dashboard")

    if placement.tenant_flagged_unreachable_at:
        messages.info(request, "You've already reported this - our Trust & Safety team has it.")
        return redirect("placements:landlord_dashboard")

    placement.flag_tenant_unreachable(reported_by=request.user)

    messages.success(
        request,
        "Thanks - we've flagged this for our Trust & Safety team to follow up.",
    )
    return redirect("placements:landlord_dashboard")


# ---------------------------------------------------------------------
# Tenant dashboard
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_tenant)
def tenant_dashboard(request):
    placements = (
        Placement.objects.filter(tenant=request.user)
        .select_related("landlord", "room", "invoice")
        .prefetch_related("status_history")
    )

    # A tenant's "current" placement: whichever active one was touched
    # most recently. Tenants can have historical/cancelled placements
    # too (shown further down the page), but only one is "in progress".
    current_placement = placements.exclude(
        status__in=[Placement.STATUS_PAID, Placement.STATUS_CANCELLED]
    ).order_by("-updated_at").first()

    return render(request, "placements/tenant_dashboard.html", {
        "current_placement": current_placement,
        "all_placements": placements,
    })


# ---------------------------------------------------------------------
# Move-in confirmation (shared by both roles - the form and template are
# identical, only which boolean field gets written differs)
# ---------------------------------------------------------------------
@login_required
def confirm_move_in(request, placement_id):
    placement = get_object_or_404(Placement, id=placement_id)

    is_this_tenant = placement.tenant_id == request.user.id
    is_this_landlord = placement.landlord_id == request.user.id

    if not (is_this_tenant or is_this_landlord):
        messages.error(request, "You don't have access to this placement.")
        return redirect("home")

    if not placement.awaiting_move_in_confirmation:
        messages.info(request, "This placement isn't awaiting move-in confirmation yet.")
        return redirect(
            "placements:tenant_dashboard" if is_this_tenant else "placements:landlord_dashboard"
        )

    already_answered = (
        placement.tenant_confirmed_move_in is not None if is_this_tenant
        else placement.landlord_confirmed_move_in is not None
    )

    if request.method == "POST" and not already_answered:
        form = MoveInConfirmationForm(request.POST)
        if form.is_valid():
            placement.confirm_move_in(
                as_tenant=is_this_tenant,
                confirmed=form.confirmed_bool(),
            )
            messages.success(request, "Thanks - your response has been recorded.")
            return redirect(
                "placements:tenant_dashboard" if is_this_tenant else "placements:landlord_dashboard"
            )
    else:
        form = MoveInConfirmationForm()

    return render(request, "placements/confirm_move_in.html", {
        "placement": placement,
        "form": form,
        "already_answered": already_answered,
        "is_this_tenant": is_this_tenant,
    })
