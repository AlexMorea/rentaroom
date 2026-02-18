from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.contrib.auth.views import PasswordResetView
from django.core.cache import cache
from urllib.parse import quote
from django.contrib import messages
import re

from .models import Room, Review, Contact, RoomStat, RoomImage, Profile, Favorite
from .forms import UserRegisterForm, RoomForm, UserUpdateForm, ProfileUpdateForm


# -----------------------------
# Profile completeness gate
# -----------------------------
def profile_needs_update(user):
    if not hasattr(user, "profile"):
        return True

    p = user.profile

    # NOTE TO SELF: tenants must have persona
    if p.role == "tenant":
        return not (getattr(p, "persona", "") or "").strip()

    # NOTE TO SELF: landlords must have verification fields
    if p.role == "landlord":
        missing = []
        if not (user.first_name or "").strip():
            missing.append("first name")
        if not (user.last_name or "").strip():
            missing.append("last name")
        if not (user.email or "").strip():
            missing.append("email")

        if not (getattr(p, "cell_no", "") or "").strip():
            missing.append("cell number")
        if not (getattr(p, "home_address", "") or "").strip():
            missing.append("home address")
        if not (getattr(p, "postal_code", "") or "").strip():
            missing.append("postal code")

        if getattr(p, "terms_accepted", False) is not True:
            missing.append("terms agreement")

        return len(missing) > 0

    return False


def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"


# -----------------------------
# LANDLORD: Rooms + Images hubs
# -----------------------------
@login_required
def landlord_rooms(request):
    rooms = Room.objects.filter(owner=request.user).order_by("-created_at")
    return render(request, "listings/landlord_rooms.html", {"rooms": rooms})


@login_required
def landlord_images_hub(request):
    room = Room.objects.filter(owner=request.user).order_by("-created_at").first()
    if not room:
        return redirect("create_room")
    return redirect("edit_room_images", pk=room.id)


# -----------------------------
# PUBLIC PAGES
# -----------------------------
def home(request):
    """
    Home page:
    - Shows counters
    - Provides search form that redirects to /rooms/ with query params
    """
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    if request.GET.get("go") == "1":
        params = []
        if q:
            params.append(f"q={q}")
        if location:
            params.append(f"location={location}")
        if room_type:
            params.append(f"type={room_type}")

        querystring = "&".join(params)
        return redirect(f"/rooms/?{querystring}" if querystring else "/rooms/")

    context = {
        "room_count": Room.objects.count(),
        "contact_count": Contact.objects.count(),
        "review_count": Review.objects.count(),
        "landlord_count": Profile.objects.filter(role="landlord").count(),
        "values": {"q": q, "location": location, "type": room_type},
        "selected": {
            "any": room_type == "",
            "single": room_type == "single",
            "shared": room_type == "shared",
            "flat": room_type == "flat",
        },
    }
    return render(request, "listings/home.html", context)


def about(request):
    return render(request, "listings/about.html")


def services(request):
    context = {
        "rooms_available": Room.objects.filter(is_available=True).count(),
        "total_rooms": Room.objects.count(),
        "contacts_made": RoomStat.objects.filter(stat_type__startswith="contact").count(),
        "success_matches": RoomStat.objects.filter(stat_type="success").count(),
    }
    return render(request, "listings/services.html", context)


def contact(request):
    return render(request, "listings/contact.html")


# -----------------------------
# ROOMS: list + detail
# -----------------------------
def room_list(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    rooms_qs = Room.objects.filter(is_available=True)

    if q:
        rooms_qs = rooms_qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(location__icontains=q)
            | Q(room_type__icontains=q)
        )

    if location:
        rooms_qs = rooms_qs.filter(location__icontains=location)

    if room_type:
        rooms_qs = rooms_qs.filter(room_type=room_type)

    rooms = (
        rooms_qs.annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            contact_count=Count(
                "roomstat",
                filter=Q(roomstat__stat_type__startswith="contact"),
                distinct=True,
            ),
            landlord_review_total=Count("owner__rooms__reviews", distinct=True),
            landlord_contact_total=Count(
                "owner__rooms__roomstat",
                filter=Q(owner__rooms__roomstat__stat_type__startswith="contact"),
                distinct=True,
            ),
        )
        .select_related("owner__profile")
        .prefetch_related("images")
        .order_by(
            "-landlord_contact_total",
            "-landlord_review_total",
            "-contact_count",
            "-review_count",
            "-created_at",
        )
    )

    return render(
        request,
        "listings/room_list.html",
        {
            "rooms": rooms,
            "values": {"q": q, "location": location, "type": room_type},
            "selected": {
                "any": room_type == "",
                "single": room_type == "single",
                "shared": room_type == "shared",
                "flat": room_type == "flat",
            },
        },
    )


def room_detail(request, pk):
    room = get_object_or_404(Room, pk=pk, is_available=True)

    RoomStat.objects.create(
        room=room,
        user=request.user if request.user.is_authenticated else None,
        stat_type="view",
    )

    is_saved = False
    if (
        request.user.is_authenticated
        and hasattr(request.user, "profile")
        and request.user.profile.role == "tenant"
    ):
        is_saved = Favorite.objects.filter(user=request.user, room=room).exists()

    return render(request, "listings/room_detail.html", {"room": room, "is_saved": is_saved})


# -----------------------------
# AUTH: register/login/logout
# -----------------------------
def register(request):
    form = UserRegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)

        messages.success(request, f"Welcome, {user.username} 👋")
        user.refresh_from_db()

        if hasattr(user, "profile") and user.profile.role == "landlord":
            return redirect("dashboard")

        return redirect("room_list")

    return render(request, "listings/register.html", {"form": form})


def user_login(request):
    if request.method == "POST":
        user = authenticate(
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )

        if user:
            login(request, user)
            user.refresh_from_db()

            # NOTE TO SELF: existing users must update profile
            if profile_needs_update(user):
                messages.warning(
                    request,
                    "Quick one: please update your profile details so your account stays trustworthy ✅"
                )
                return redirect("edit_profile")

            messages.success(request, f"Hello, {user.username} 👋")

            next_url = request.POST.get("next") or request.GET.get("next")

            if hasattr(user, "profile") and user.profile.role == "landlord":
                return redirect("dashboard")

            if next_url:
                return redirect(next_url)

            return redirect("room_list")

        messages.error(request, "Invalid username or password.")

    return render(request, "listings/login.html")


def user_logout(request):
    logout(request)
    messages.info(request, "You’ve been logged out.")
    return redirect("room_list")


# -----------------------------
# PROFILES (tenant + landlord)
# -----------------------------
@login_required
def profile(request):
    user = request.user
    p = user.profile

    # NOTE TO SELF: tenant panels (saved + viewed)
    favorites_qs = Favorite.objects.filter(user=user).select_related("room").order_by("-created_at")
    saved_rooms = [f.room for f in favorites_qs]

    viewed_stats = (
        RoomStat.objects.filter(user=user, stat_type="view")
        .select_related("room")
        .order_by("-created_at")
    )

    # NOTE TO SELF: dedupe viewed rooms without breaking sqlite
    seen = set()
    viewed_rooms = []
    for s in viewed_stats:
        if not s.room_id:
            continue
        if s.room_id in seen:
            continue
        seen.add(s.room_id)
        viewed_rooms.append(s.room)

    context = {
        "p": p,
        "saved_rooms": saved_rooms,
        "viewed_rooms": viewed_rooms,
        "saved_count": len(saved_rooms),
        "viewed_count": len(viewed_rooms),
    }

    if p.role == "landlord":
        rooms = Room.objects.filter(owner=user).order_by("-created_at")
        image_count = RoomImage.objects.filter(room__owner=user).count()
        contact_count = RoomStat.objects.filter(room__owner=user, stat_type__startswith="contact").count()

        context.update(
            {
                "rooms": rooms,
                "rooms_count": rooms.count(),
                "image_count": image_count,
                "contact_count": contact_count,
            }
        )

    return render(request, "listings/profile.html", context)


@login_required
def edit_profile(request):
    user = request.user
    p = user.profile

    u_form = UserUpdateForm(request.POST or None, instance=user)
    p_form = ProfileUpdateForm(request.POST or None, instance=p)

    if request.method == "POST":
        ok = u_form.is_valid() and p_form.is_valid()

        # NOTE TO SELF: landlords must keep these filled
        if p.role == "landlord":
            cell = (p_form.cleaned_data.get("cell_no") or "").strip()
            addr = (p_form.cleaned_data.get("home_address") or "").strip()
            pc = (p_form.cleaned_data.get("postal_code") or "").strip()

            if not cell:
                p_form.add_error("cell_no", "Cell number is required.")
                ok = False
            if not addr:
                p_form.add_error("home_address", "Home address is required.")
                ok = False
            if not pc:
                p_form.add_error("postal_code", "Postal code is required.")
                ok = False

        # NOTE TO SELF: tenants must choose persona
        if p.role == "tenant":
            persona = (p_form.cleaned_data.get("persona") or "").strip()
            if not persona:
                p_form.add_error("persona", "Please choose your persona.")
                ok = False

        if ok:
            u_form.save()
            p_form.save()
            messages.success(request, "Profile updated ✅")
            return redirect("profile")

    return render(
        request,
        "listings/edit_profile.html",
        {"u_form": u_form, "p_form": p_form, "p": p},
    )


@login_required
def toggle_favorite(request, room_id):
    room = get_object_or_404(Room, id=room_id, is_available=True)

    # NOTE TO SELF: only tenants save rooms
    if not hasattr(request.user, "profile") or request.user.profile.role != "tenant":
        return HttpResponseForbidden("Only tenants can save rooms.")

    fav = Favorite.objects.filter(user=request.user, room=room).first()
    if fav:
        fav.delete()
        messages.info(request, "Removed from saved rooms.")
    else:
        Favorite.objects.create(user=request.user, room=room)
        messages.success(request, "Saved ✔")

    return redirect("room_detail", pk=room.id)


# -----------------------------
# LANDLORD: dashboard + CRUD
# -----------------------------
@login_required
@user_passes_test(is_landlord)
def dashboard(request):
    rooms_qs = Room.objects.filter(owner=request.user)

    image_count = RoomImage.objects.filter(room__owner=request.user).count()
    contact_count = RoomStat.objects.filter(
        room__owner=request.user, stat_type__startswith="contact"
    ).count()

    rooms = rooms_qs.annotate(
        view_count=Count("roomstat", filter=Q(roomstat__stat_type="view")),
        contact_total=Count("roomstat", filter=Q(roomstat__stat_type__startswith="contact")),
    ).order_by("-created_at")

    for r in rooms:
        r.ctr = round((r.contact_total / r.view_count) * 100, 1) if r.view_count else 0

    show_profile_warning = (rooms_qs.count() == 0) or (not (request.user.email or "").strip())

    return render(
        request,
        "listings/dashboard.html",
        {
            "rooms": rooms,
            "image_count": image_count,
            "contact_count": contact_count,
            "show_profile_warning": show_profile_warning,
        },
    )


@login_required
@user_passes_test(is_landlord)
def add_room(request):
    return redirect("create_room")


@login_required
@user_passes_test(is_landlord)
def create_room(request):
    form = RoomForm(request.POST or None, request.FILES or None, user=request.user)
    if form.is_valid():
        room = form.save(commit=False)
        room.owner = request.user
        room.save()

        for img in request.FILES.getlist("images")[:10]:
            RoomImage.objects.create(room=room, image=img)

        return redirect("dashboard")

    return render(request, "listings/create_room.html", {"form": form})


@login_required
@user_passes_test(is_landlord)
def edit_room(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)
    form = RoomForm(request.POST or None, instance=room, user=request.user)
    if form.is_valid():
        form.save()
        return redirect("dashboard")
    return render(request, "listings/edit_room.html", {"form": form})


@login_required
@user_passes_test(is_landlord)
def delete_room(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)
    if request.method == "POST":
        room.delete()
        return redirect("dashboard")
    return render(request, "listings/delete_room.html", {"room": room})


# -----------------------------
# IMAGES (upload/delete/manage)
# -----------------------------
@login_required
def upload_room_images(request, room_id):
    room = get_object_or_404(Room, id=room_id, owner=request.user)

    if request.method == "POST":
        for img in request.FILES.getlist("images")[:10]:
            RoomImage.objects.create(room=room, image=img)
        return redirect("edit_room_images", pk=room.id)

    return render(request, "listings/upload_images.html", {"room": room})


@login_required
def delete_room_image(request, image_id):
    image = get_object_or_404(RoomImage, id=image_id, room__owner=request.user)
    room_id = image.room.id
    image.delete()
    return redirect("edit_room_images", pk=room_id)


MAX_IMAGES_PER_ROOM = 10


@login_required
def edit_room_images(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)

    if request.method == "POST":
        # --- Delete first (frees up slots) ---
        delete_ids = request.POST.getlist("delete")
        deleted_count = 0
        if delete_ids:
            qs = RoomImage.objects.filter(room=room, id__in=delete_ids)
            deleted_count = qs.count()
            qs.delete()
            if deleted_count:
                messages.success(request, f"Deleted {deleted_count} image(s).")

        # --- Upload next (respect total max) ---
        current_count = RoomImage.objects.filter(room=room).count()
        remaining_slots = max(0, MAX_IMAGES_PER_ROOM - current_count)

        uploads = request.FILES.getlist("images")
        if uploads:
            if remaining_slots <= 0:
                messages.error(
                    request,
                    f"You already have {MAX_IMAGES_PER_ROOM} images. Delete some first to upload new ones.",
                )
            else:
                to_add = uploads[:remaining_slots]
                for img in to_add:
                    RoomImage.objects.create(room=room, image=img)

                messages.success(
                    request,
                    f"Uploaded {len(to_add)} image(s). ({RoomImage.objects.filter(room=room).count()}/{MAX_IMAGES_PER_ROOM})",
                )

                if len(uploads) > remaining_slots:
                    messages.warning(
                        request,
                        f"Only {remaining_slots} image(s) were added (max {MAX_IMAGES_PER_ROOM} per room).",
                    )

        return redirect("edit_room_images", pk=pk)

    return render(
        request,
        "listings/edit_room_images.html",
        {"room": room, "img_count": room.images.count(), "max_images": 10},
    )


# -----------------------------
# REVIEWS + CONTACT TRACKING
# -----------------------------
@login_required
def add_review(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    if not Contact.objects.filter(room=room, user=request.user).exists():
        return HttpResponseForbidden("Contact landlord first.")

    Review.objects.create(
        room=room,
        user=request.user,
        rating=request.POST.get("rating"),
        comment=request.POST.get("comment", ""),
    )
    return redirect("room_detail", pk=room.id)


@login_required
def track_contact(request, room_id, method):
    room = get_object_or_404(Room, id=room_id, is_available=True)

    RoomStat.objects.create(
        room=room,
        user=request.user,
        stat_type=f"contact_{method}",
    )
    Contact.objects.get_or_create(room=room, user=request.user)

    phone_raw = (room.contact_phone or "").strip()
    whatsapp_raw = (room.contact_whatsapp or "").strip() or phone_raw
    phone_digits = re.sub(r"\D", "", whatsapp_raw)
    landlord_email = (room.contact_email or room.owner.email or "").strip()

    if method == "phone":
        tel = phone_raw.replace(" ", "")
        if not tel:
            return redirect("room_detail", pk=room.id)

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Calling landlord…",
                "link": f"tel:{tel}",
                "button_text": "Tap to Call",
                "fallback_text": "If your phone didn’t open the dialer automatically, tap the button below.",
            },
        )

    if method == "whatsapp":
        if not phone_digits:
            return redirect("room_detail", pk=room.id)
        return redirect(f"https://wa.me/{phone_digits}")

    if method == "email":
        if not landlord_email:
            return redirect("room_detail", pk=room.id)

        subject = quote(f"Rooms4You enquiry: {room.title}")
        body = quote(f"Hi, I’m interested in your room listing ({room.title}) in {room.location}.")
        mailto = f"mailto:{landlord_email}?subject={subject}&body={body}"

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Opening email…",
                "link": mailto,
                "button_text": "Open Email",
                "fallback_text": "If your email app didn’t open automatically, tap the button below.",
            },
        )

    return redirect("room_detail", pk=room.id)


@login_required
def mark_success(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    RoomStat.objects.create(room=room, user=request.user, stat_type="success")
    messages.success(request, "Thanks for confirming!")
    return redirect("room_detail", pk=room.id)


# -----------------------------
# Password reset (rate limited)
# -----------------------------
class RateLimitedPasswordResetView(PasswordResetView):
    subject_template_name = "registration/password_reset_subject.txt"
    email_template_name = "registration/password_reset_email.txt"
    html_email_template_name = "registration/password_reset_email.html"

    COOLDOWN_SECONDS = 60
    MAX_PER_HOUR = 5

    def form_valid(self, form):
        email = (form.cleaned_data.get("email") or "").strip().lower()
        ip = (
            self.request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or self.request.META.get("REMOTE_ADDR", "unknown")
        )

        base_key = f"pwreset:{ip}:{email}"

        cooldown_key = base_key + ":cooldown"
        if cache.get(cooldown_key):
            messages.error(self.request, "Please wait a bit before requesting another reset email.")
            return self.form_invalid(form)

        hour_key = base_key + ":hour"
        count = cache.get(hour_key, 0)
        if count >= self.MAX_PER_HOUR:
            messages.error(self.request, "Too many reset attempts. Please try again later.")
            return self.form_invalid(form)

        cache.set(cooldown_key, 1, timeout=self.COOLDOWN_SECONDS)
        cache.set(hour_key, count + 1, timeout=3600)

        return super().form_valid(form)


# -----------------------------
# Landlord analytics + heatmap
# -----------------------------
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


@login_required
def heatmap(request):
    return render(request, "listings/heatmap.html")
