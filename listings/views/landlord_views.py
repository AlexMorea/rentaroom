import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from placements.models import Placement, Waitlist

from ..models import Contact, Message, Review, Room, RoomImage, RoomStat

logger = logging.getLogger(__name__)

from .helpers import get_or_create_membership, is_landlord


@login_required
def landlord_rooms(request):
    # Use select_related/prefetch to avoid N+1 and add pagination
    rooms_qs = (
        Room.objects.filter(owner=request.user)
        .select_related("owner__profile")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=RoomImage.objects.only("id", "image", "room_id")
            )
        )
        .annotate(
            waiting_count=Count(
                "waitlist_entries",
                filter=Q(waitlist_entries__status=Waitlist.STATUS_WAITING),
            )
        )
        .order_by("-created_at")
    )

    page_number = request.GET.get("page") or 1
    paginator = Paginator(rooms_qs, 10)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "listings/landlord_rooms.html",
        {
            "rooms": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
        },
    )


def landlord_profile(request, user_id):
    """
    Public-facing profile page for a landlord - linked from room cards
    and room_detail so a tenant can see who they'd be renting from
    without that requiring any direct contact info exchange.
    """
    landlord = get_object_or_404(User, id=user_id)

    if not (hasattr(landlord, "profile") and landlord.profile.role == "landlord"):
        raise Http404("This user does not have a landlord profile.")

    rooms = (
        Room.objects.filter(owner=landlord, is_available=True)
        .prefetch_related(
            Prefetch("images", queryset=RoomImage.objects.only("id", "image", "room_id"))
        )
        .annotate(avg_rating_value=Avg("reviews__rating"))
        .order_by("-created_at")
    )

    rating_agg = Review.objects.filter(room__owner=landlord).aggregate(
        avg=Avg("rating"), count=Count("id")
    )

    return render(request, "listings/landlord_profile.html", {
        "landlord": landlord,
        "rooms": rooms,
        "active_room_count": rooms.count(),
        "avg_rating": rating_agg["avg"],
        "review_count": rating_agg["count"] or 0,
    })


def _tenant_has_engaged_with_landlord(tenant_id, landlord_id) -> bool:
    """
    Gates tenant_profile: a landlord can view a tenant's profile only if
    that tenant has actually engaged with one of the landlord's rooms
    (contacted, messaged, or already has a Placement) - not any tenant
    on the site. Mirrors the same privacy guard used when a landlord
    adds a tenant to a room's waitlist (see placements.views.add_to_waitlist).
    """
    return (
        Contact.objects.filter(user_id=tenant_id, room__owner_id=landlord_id).exists()
        or Message.objects.filter(sender_id=tenant_id, room__owner_id=landlord_id).exists()
        or Placement.objects.filter(tenant_id=tenant_id, landlord_id=landlord_id).exists()
    )


@login_required
@user_passes_test(is_landlord)
def tenant_profile(request, user_id):
    """
    Landlord-facing view of a tenant's profile - the counterpart to
    landlord_profile, but access-gated (see _tenant_has_engaged_with_landlord)
    rather than public, since tenants haven't opted into a public profile
    the way landlords have.
    """
    tenant = get_object_or_404(User, id=user_id)

    if not (hasattr(tenant, "profile") and tenant.profile.role == "tenant"):
        raise Http404("This user does not have a tenant profile.")

    if not _tenant_has_engaged_with_landlord(tenant.id, request.user.id):
        raise Http404("You don't have access to this tenant's profile.")

    engaged_rooms = (
        Room.objects.filter(owner=request.user)
        .filter(Q(contacts__user=tenant) | Q(messages__sender=tenant))
        .distinct()
        .order_by("-created_at")
    )

    waitlist_entries = (
        Waitlist.objects.filter(tenant=tenant, landlord=request.user)
        .exclude(status=Waitlist.STATUS_CANCELLED)
        .select_related("room")
    )
    waitlisted_room_ids = {entry.room_id for entry in waitlist_entries}

    # Landlord's own occupied rooms this tenant could still be added to.
    joinable_rooms = (
        Room.objects.filter(owner=request.user, is_available=True, available_units=0)
        .exclude(id__in=waitlisted_room_ids)
        .order_by("-created_at")
    )

    return render(request, "listings/tenant_profile.html", {
        "tenant": tenant,
        "engaged_rooms": engaged_rooms,
        "waitlist_entries": waitlist_entries,
        "joinable_rooms": joinable_rooms,
    })


@login_required
def landlord_images_hub(request):
    """
    Landlord 'Images' stat page:
    shows ALL images across ALL rooms owned by the landlord.
    """
    rooms = Room.objects.filter(owner=request.user).order_by("-created_at")
    images = (
        RoomImage.objects
        .filter(room__owner=request.user)
        .select_related("room")
        .order_by("-created_at")
    )

    return render(
        request,
        "listings/landlord_images.html",
        {
            "rooms": rooms,
            "images": images,
            "image_count": images.count(),
        }
    )


@login_required
@user_passes_test(is_landlord)
def dashboard(request):
    rooms_qs = Room.objects.filter(owner=request.user)

    image_count = RoomImage.objects.filter(room__owner=request.user).count()

    contact_count = RoomStat.objects.filter(
        room__owner=request.user,
        stat_type__startswith="contact"
    ).count()

    rooms = rooms_qs.annotate(
        view_count=Count("roomstat", filter=Q(roomstat__stat_type="view")),
        contact_total=Count("roomstat", filter=Q(roomstat__stat_type__startswith="contact")),
    ).order_by("-created_at")

    for r in rooms:
        r.ctr = round((r.contact_total / r.view_count) * 100, 1) if r.view_count else 0

    show_profile_warning = (
        rooms_qs.count() == 0
        or not (request.user.email or "").strip()
    )

    membership = get_or_create_membership(request.user)

    # SAFE inbox query (CRM-style leads)
    messages_received = (
        Message.objects.filter(recipient=request.user)
        .select_related("sender", "room")
        .order_by("-created_at")[:8]
    )

    # Placements summary - previously invisible from the main dashboard,
    # a landlord could have a success fee sitting unpaid and never see it
    active_placements_count = Placement.objects.filter(landlord=request.user).exclude(
        status__in=[Placement.STATUS_PAID, Placement.STATUS_CANCELLED]
    ).count()
    fees_due_count = Placement.objects.filter(
        landlord=request.user,
        status=Placement.STATUS_SUCCESS_FEE_DUE,
    ).count()

    return render(
        request,
        "listings/dashboard.html",
        {
            "rooms": rooms,
            "image_count": image_count,
            "contact_count": contact_count,
            "show_profile_warning": show_profile_warning,
            "membership": membership,

            # CRM inbox
            "messages_received": messages_received,

            # Placements summary
            "active_placements_count": active_placements_count,
            "fees_due_count": fees_due_count,
        },
    )


@login_required
@user_passes_test(is_landlord)
def contacts_analytics(request):
    rooms_qs = Room.objects.filter(owner=request.user)

    rooms = rooms_qs.annotate(
        view_count=Count("roomstat", filter=Q(roomstat__stat_type="view")),
        contact_total=Count("roomstat", filter=Q(roomstat__stat_type__startswith="contact")),
        phone_count=Count("roomstat", filter=Q(roomstat__stat_type="contact_phone")),
        whatsapp_count=Count("roomstat", filter=Q(roomstat__stat_type="contact_whatsapp")),
        email_count=Count("roomstat", filter=Q(roomstat__stat_type="contact_email")),
        success_count=Count("roomstat", filter=Q(roomstat__stat_type="success")),
    ).order_by("-contact_total", "-view_count", "-created_at")

    totals = {
        "views": RoomStat.objects.filter(room__owner=request.user, stat_type="view").count(),
        "contacts": RoomStat.objects.filter(room__owner=request.user, stat_type__startswith="contact").count(),
        "success": RoomStat.objects.filter(room__owner=request.user, stat_type="success").count(),
    }

    for r in rooms:
        r.ctr = round((r.contact_total / r.view_count) * 100, 1) if r.view_count else 0

    return render(request, "listings/contacts_analytics.html", {"rooms": rooms, "totals": totals})

