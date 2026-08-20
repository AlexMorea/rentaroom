import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse

from ..forms import ProfileUpdateForm, UserUpdateForm
from ..models import Favorite, Room, RoomImage, RoomStat

logger = logging.getLogger(__name__)


@login_required
def profile(request):
    user = request.user
    p = user.profile

    def dash(value):
        value = (value or "").strip() if isinstance(value, str) else value
        return value if value else "—"

    # ---------------- TENANT DATA ----------------
    favorites_qs = (
        Favorite.objects
        .filter(user=user)
        .select_related(
            "room",
            "room__owner__profile"
        )
        .prefetch_related("room__images")
        .order_by("-created_at")
    )
    saved_rooms = [f.room for f in favorites_qs]

    viewed_stats = (
        RoomStat.objects.filter(
            user=user,
            stat_type="view"
        )
        .select_related(
            "room",
            "room__owner__profile"
        )
        .order_by("-created_at")
    )

    seen = set()
    viewed_rooms = []

    for s in viewed_stats:
        if not s.room_id:
            continue
        if s.room_id in seen:
            continue
        seen.add(s.room_id)
        viewed_rooms.append(s.room)

    # ---------------- LANDLORD STATS ----------------
    rooms_count = 0
    image_count = 0
    contact_count = 0

    if p.role == "landlord":
        rooms = Room.objects.filter(owner=user)

        rooms_count = rooms.count()
        image_count = RoomImage.objects.filter(
            room__owner=user
        ).count()

        contact_count = RoomStat.objects.filter(
            room__owner=user,
            stat_type__startswith="contact"
        ).count()

    # ---------------- HEADER ----------------
    persona_text = (
        p.get_persona_display()
        if p.persona
        else "Not set"
    )

    badge_text = (
        persona_text
        if p.role == "tenant"
        else "Landlord"
    )

    verified_badge = (
        "Verified"
        if (
            p.role == "landlord"
            and getattr(p, "is_verified", False)
        )
        else ""
    )

    # ---------------- STATS ----------------
    stat_cards = []
    stat_links = []

    if p.role == "tenant":
        stat_cards = [
            {
                "number": len(saved_rooms),
                "label": "Saved rooms"
            },
            {
                "number": len(viewed_rooms),
                "label": "Viewed rooms"
            },
        ]
    else:
        stat_links = [
            {
                "href": reverse("landlord_rooms"),
                "number": rooms_count,
                "label": "Rooms"
            },
            {
                "href": reverse("landlord_images_hub"),
                "number": image_count,
                "label": "Images"
            },
            {
                "href": reverse("contacts_analytics"),
                "number": contact_count,
                "label": "Contacts"
            },
        ]

    # ---------------- DETAILS ----------------
    detail_rows = [
        {
            "label": "Name",
            "value": f"{dash(user.first_name)} {dash(user.last_name)}"
        },
        {
            "label": "Email",
            "value": dash(user.email)
        },
        {
            "label": "Cell",
            "value": dash(p.full_phone())   # <-- now works for BOTH
        },
    ]

    if p.role == "tenant":
        detail_rows.append({
            "label": "Persona",
            "value": persona_text
        })

    else:
        detail_rows.extend([
            {
                "label": "Alt",
                "value": dash(p.alt_no)
            },
            {
                "label": "Address",
                "value": dash(p.home_address)
            },
            {
                "label": "Postal",
                "value": dash(p.postal_code)
            },
        ])

    # ---------------- TENANT SECTIONS ----------------
    tenant_sections = []

    if p.role == "tenant":
        tenant_sections = [
            {
                "title": "Saved rooms",
                "rooms": saved_rooms
            },
            {
                "title": "Viewed rooms",
                "rooms": viewed_rooms
            },
        ]

    return render(
        request,
        "listings/profile.html",
        {
            "p": p,
            "badge_text": badge_text,
            "verified_badge": verified_badge,
            "stat_cards": stat_cards,
            "stat_links": stat_links,
            "detail_rows": detail_rows,
            "tenant_sections": tenant_sections,
        },
    )


@login_required
def edit_profile(request):
    user = request.user
    profile = user.profile

    u_form = UserUpdateForm(
        request.POST or None,
        instance=user
    )

    p_form = ProfileUpdateForm(
        request.POST or None,
        instance=profile
    )

    # hide landlord-only fields for tenants
    if profile.role == "tenant":
        for field in ["alt_no", "home_address", "postal_code"]:
            p_form.fields.pop(field, None)

    # hide tenant-only field for landlords
    if profile.role == "landlord":
        p_form.fields.pop("persona", None)

    if request.method == "POST":

        u_valid = u_form.is_valid()
        p_valid = p_form.is_valid()

        if u_valid and p_valid:

            user_obj = u_form.save(commit=False)
            profile_obj = p_form.save(commit=False)

            # preserve country code
            profile_obj.country_code = p_form.cleaned_data.get(
                "country_code",
                profile.country_code
            )

            # preserve phone
            phone = p_form.cleaned_data.get("phone_number")
            if phone:
                profile_obj.phone_number = phone

            with transaction.atomic():
                user_obj.save()
                profile_obj.save()

            messages.success(
                request,
                "Profile updated successfully."
            )
            return redirect("profile")

        else:
            logger.error(u_form.errors)
            logger.error(p_form.errors)
            messages.error(
                request,
                "Please fix the errors below."
            )

    return render(
        request,
        "listings/edit_profile.html",
        {
            "u_form": u_form,
            "p_form": p_form,
            "p": profile,
        },
    )

