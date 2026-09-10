from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from listings.models import Contact, Message, Room
from listings.views import is_landlord

from .forms import MoveInConfirmationForm, PlacementUpdateForm
from .models import Placement, Waitlist


def is_tenant(user):
    return hasattr(user, "profile") and user.profile.role == "tenant"


def _room_has_vacancy(room: Room) -> bool:
    return room.is_available and room.available_units > 0


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
# Waitlists
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_tenant)
@require_POST
def join_waitlist(request, room_id):
    room = get_object_or_404(Room, id=room_id, is_available=True)

    if room.owner_id == request.user.id:
        messages.error(request, "You can't join the waitlist for your own room.")
        return redirect("room_detail", pk=room.id)

    if _room_has_vacancy(room):
        messages.info(
            request,
            "This room already has vacancies - no need to wait, contact the landlord directly.",
        )
        return redirect("room_detail", pk=room.id)

    entry, created = Waitlist.objects.get_or_create(
        tenant=request.user,
        room=room,
        defaults={"landlord": room.owner, "added_by": Waitlist.ADDED_BY_TENANT},
    )

    if not created and entry.status == Waitlist.STATUS_CANCELLED:
        entry.status = Waitlist.STATUS_WAITING
        entry.added_by = Waitlist.ADDED_BY_TENANT
        entry.notified_at = None
        entry.save(update_fields=["status", "added_by", "notified_at"])
        created = True

    if created:
        messages.success(
            request,
            f"You're #{entry.position} in line for \"{room.title}\" - "
            "we'll email and notify you the moment it opens up.",
        )
    else:
        messages.info(request, "You're already on the waitlist for this room.")

    return redirect("room_detail", pk=room.id)


@login_required
@require_POST
def leave_waitlist(request, room_id):
    entry = get_object_or_404(
        Waitlist, room_id=room_id, tenant=request.user, status__in=[Waitlist.STATUS_WAITING, Waitlist.STATUS_NOTIFIED]
    )
    entry.status = Waitlist.STATUS_CANCELLED
    entry.save(update_fields=["status"])
    messages.success(request, "You've left the waitlist.")
    return redirect("room_detail", pk=room_id)


@login_required
@user_passes_test(is_landlord)
def room_waitlist(request, room_id):
    room = get_object_or_404(Room, id=room_id, owner=request.user)

    entries = (
        Waitlist.objects.filter(room=room, status__in=[Waitlist.STATUS_WAITING, Waitlist.STATUS_NOTIFIED])
        .select_related("tenant__profile")
    )

    already_listed_ids = {entry.tenant_id for entry in entries}

    # Privacy guard: a landlord can only add a tenant who's actually
    # engaged with this specific room (contacted, messaged, or already
    # has a Placement) - not any tenant on the site.
    engaged_tenant_ids = (
        set(Contact.objects.filter(room=room).exclude(user_id=room.owner_id).values_list("user_id", flat=True))
        | set(Message.objects.filter(room=room).exclude(sender_id=room.owner_id).values_list("sender_id", flat=True))
        | set(Placement.objects.filter(room=room).exclude(tenant_id=room.owner_id).values_list("tenant_id", flat=True))
    )
    addable_tenants = User.objects.filter(id__in=engaged_tenant_ids - already_listed_ids)

    return render(request, "placements/room_waitlist.html", {
        "room": room,
        "entries": entries,
        "addable_tenants": addable_tenants,
    })


@login_required
@user_passes_test(is_landlord)
@require_POST
def add_to_waitlist(request, room_id):
    room = get_object_or_404(Room, id=room_id, owner=request.user)
    tenant = get_object_or_404(User, id=request.POST.get("tenant_id"))

    has_engaged = (
        Contact.objects.filter(room=room, user=tenant).exists()
        or Message.objects.filter(room=room, sender=tenant).exists()
        or Placement.objects.filter(room=room, tenant=tenant).exists()
    )
    if not has_engaged:
        messages.error(
            request,
            "You can only waitlist a tenant who's already contacted you about this room.",
        )
        return redirect("placements:room_waitlist", room_id=room.id)

    entry, created = Waitlist.objects.get_or_create(
        tenant=tenant,
        room=room,
        defaults={"landlord": room.owner, "added_by": Waitlist.ADDED_BY_LANDLORD},
    )

    if not created and entry.status == Waitlist.STATUS_CANCELLED:
        entry.status = Waitlist.STATUS_WAITING
        entry.added_by = Waitlist.ADDED_BY_LANDLORD
        entry.notified_at = None
        entry.save(update_fields=["status", "added_by", "notified_at"])
        created = True

    if created:
        messages.success(request, f"{tenant.get_full_name() or tenant.username} added to the waitlist.")
    else:
        messages.info(request, "That tenant is already on the waitlist.")

    return redirect("placements:room_waitlist", room_id=room.id)


@login_required
@user_passes_test(is_landlord)
@require_POST
def remove_from_waitlist(request, entry_id):
    entry = get_object_or_404(Waitlist, id=entry_id, landlord=request.user)
    room_id = entry.room_id
    entry.status = Waitlist.STATUS_CANCELLED
    entry.save(update_fields=["status"])
    messages.success(request, "Removed from the waitlist.")
    return redirect("placements:room_waitlist", room_id=room_id)


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

    waitlist_entries = (
        Waitlist.objects.filter(
            tenant=request.user, status__in=[Waitlist.STATUS_WAITING, Waitlist.STATUS_NOTIFIED]
        )
        .select_related("room", "landlord")
    )

    return render(request, "placements/tenant_dashboard.html", {
        "current_placement": current_placement,
        "all_placements": placements,
        "waitlist_entries": waitlist_entries,
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
