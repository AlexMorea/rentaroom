from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.contrib.auth.views import PasswordResetView
from django.urls import reverse
from django.core.cache import cache
from urllib.parse import quote
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from difflib import get_close_matches
from django.contrib.auth.models import User
import re
import uuid
from .models import PhoneOTP
from django.conf import settings
from .models import EmailVerification
from .utils import generate_otp, send_otp_email
from utils.email import send_template_email
from accounts.utils import require_active_membership
from django.utils import timezone
from datetime import timedelta
from django.contrib.sites.shortcuts import get_current_site
from uuid import uuid4
from accounts.models import Membership
from .forms import ListingForm
from .models import Room, Review, Contact, RoomStat, RoomImage, Profile, Favorite
from .forms import UserRegisterForm, RoomForm, UserUpdateForm, ProfileUpdateForm


def get_display_name(user):
    return (user.first_name or "").strip() or (user.email or "").strip() or "there"


# -----------------------------
# Profile completeness gate
# -----------------------------
def get_or_create_membership(user):
    membership, created = Membership.objects.get_or_create(
        user=user,
        defaults={
            "tier": "starter",
            "is_active": True,
            "is_trial": True,
            "trial_end": timezone.now() + timedelta(days=30)
        }
    )

    # Ensure membership ID always exists
    if not membership.membership_id:
        membership.membership_id = f"R4Y-{uuid.uuid4().hex[:6].upper()}"
        membership.save()

    return membership


    # Ensure membership ID always exists
  
def profile_needs_update(user):
    if not hasattr(user, "profile"):
        return True

    p = user.profile

    # basic user identity fields
    has_first_name = bool((user.first_name or "").strip())
    has_last_name = bool((user.last_name or "").strip())
    has_email = bool((user.email or "").strip())

    if p.role == "tenant":
        has_persona = bool((getattr(p, "persona", "") or "").strip())
        return not (has_first_name and has_last_name and has_email and has_persona)

    if p.role == "landlord":
        has_cell = bool((getattr(p, "phone_number", "") or "").strip())
        has_address = bool((getattr(p, "home_address", "") or "").strip())
        has_postal = bool((getattr(p, "postal_code", "") or "").strip())

        return not (
            has_first_name
            and has_last_name
            and has_email
            and has_cell
            and has_address
            and has_postal
        )

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
    sort = (request.GET.get("sort") or "").strip()

    rooms_qs = Room.objects.filter(is_available=True)

    suggested_location = ""
    searched_location = location

    if q:
        rooms_qs = rooms_qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(location__icontains=q)
            | Q(room_type__icontains=q)
        )

    if location:
        exact_location_qs = rooms_qs.filter(location__icontains=location)

        if exact_location_qs.exists():
            rooms_qs = exact_location_qs
        else:
            all_locations = list(
                Room.objects.filter(is_available=True)
                .exclude(location__isnull=True)
                .exclude(location__exact="")
                .values_list("location", flat=True)
                .distinct()
            )

            lowered_map = {}
            for loc in all_locations:
                key = loc.strip().lower()
                if key and key not in lowered_map:
                    lowered_map[key] = loc.strip()

            location_lower = location.lower()

            partial_matches = [
                original
                for key, original in lowered_map.items()
                if location_lower in key or key in location_lower
            ]

            close_keys = get_close_matches(
                location_lower,
                list(lowered_map.keys()),
                n=5,
                cutoff=0.6,
            )
            close_matches = [lowered_map[key] for key in close_keys]

            candidate_locations = []
            for loc_name in partial_matches + close_matches:
                if loc_name not in candidate_locations:
                    candidate_locations.append(loc_name)

            if candidate_locations:
                location_filter = Q()
                for loc_name in candidate_locations:
                    location_filter |= Q(location__icontains=loc_name)

                rooms_qs = rooms_qs.filter(location_filter)
                suggested_location = candidate_locations[0]
            else:
                rooms_qs = rooms_qs.none()

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
    )

    if sort == "new":
        rooms = rooms.order_by("-created_at")
    elif sort == "price_low":
        rooms = rooms.order_by("price", "-created_at")
    elif sort == "price_high":
        rooms = rooms.order_by("-price", "-created_at")
    elif sort == "rating":
        rooms = rooms.order_by("-avg_rating", "-review_count", "-created_at")
    else:
        rooms = rooms.order_by(
            "-landlord_contact_total",
            "-landlord_review_total",
            "-contact_count",
            "-review_count",
            "-created_at",
        )

    page_number = request.GET.get("page") or 1
    paginator = Paginator(rooms, 6)
    page_obj = paginator.get_page(page_number)

    # MAP DATA
    map_rooms = list(
        page_obj.object_list.values(
            "id",
            "title",
            "price",
            "latitude",
            "longitude",
        )
    )

    is_ajax = request.GET.get("ajax") == "1" or request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest"

    if is_ajax:
        html = render_to_string(
            "listings/_room_cards.html",
            {"rooms": page_obj.object_list},
            request=request,
        )
        return JsonResponse(
            {
                "html": html,
                "page": page_obj.number,
                "num_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_prev": page_obj.has_previous(),
                "next_page": page_obj.next_page_number()
                if page_obj.has_next()
                else None,
                "prev_page": page_obj.previous_page_number()
                if page_obj.has_previous()
                else None,
                "suggested_location": suggested_location,
                "searched_location": searched_location,
            }
        )

    sort_selected = {
        "best": sort == "",
        "new": sort == "new",
        "price_low": sort == "price_low",
        "price_high": sort == "price_high",
        "rating": sort == "rating",
    }

    show_location_suggestion = (
        bool(suggested_location)
        and bool(searched_location)
        and suggested_location.strip().lower()
        != searched_location.strip().lower()
    )

    return render(
        request,
        "listings/room_list.html",
        {
            "map_rooms": map_rooms,
            "rooms": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "values": {"q": q, "location": location, "type": room_type, "sort": sort},
            "selected": {
                "any": room_type == "",
                "single": room_type == "single",
                "shared": room_type == "shared",
                "flat": room_type == "flat",
            },
            "sort_selected": sort_selected,
            "suggested_location": suggested_location,
            "searched_location": searched_location,
            "show_location_suggestion": show_location_suggestion,
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

    if request.method == "POST":
        if form.is_valid():
            user = form.save()

            # 🔑 EMAIL VERIFICATION
            EmailVerification.objects.filter(user=user, is_verified=False).delete()
            verification = EmailVerification.objects.create(user=user)

            def build_domain(request):
                current_site = get_current_site(request)
                scheme = "https" if not settings.DEBUG else "http"
                return f"{scheme}://{current_site.domain}"
            
            domain = build_domain(request)
            verify_link = f"{domain}/verify-email/{verification.token}/"

            send_template_email(
                subject="Verify your Rooms4You account",
                to_email=user.email,
                template="emails/verify_email.html",
                context={
                    "user": user,
                    "verify_link": verify_link,
                    "year": 2026
                }
            )

            messages.success(request, "Check your email to verify your account ✅")
            return redirect("login")

    return render(request, "listings/register.html", {"form": form})


def verify_email(request, token):
    try:
        verification = EmailVerification.objects.get(
            token=token,
            is_verified=False
        )
    except EmailVerification.DoesNotExist:
        messages.error(request, "Invalid or expired verification link.")
        return redirect("login")

    if verification.is_expired():
        messages.error(request, "Verification link expired.")
        return redirect("register")

    user = verification.user
    profile = user.profile

    # ✅ activate everything properly
    verification.is_verified = True
    verification.save()

    profile.is_email_verified = True
    profile.save()

    user.is_active = True
    user.save()

    messages.success(request, "Email verified successfully 🎉")
    return redirect("login")


def verify_phone(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return redirect("login")

    user = User.objects.get(id=user_id)
    profile = user.profile

    if request.method == "POST":
        otp_input = request.POST.get("otp")

        if not otp_input or len(otp_input) != 6:
            messages.error(request, "Enter a valid 6-digit OTP")
            return render(request, "listings/verify_phone.html", {
                "error_state": True,
                "cooldown_active": not can_resend_otp(user.id)
            })

        attempts_key = f"otp_attempts:{user.id}"
        attempts = cache.get(attempts_key, 0)

        if attempts >= 5:
            messages.error(request, "Too many attempts. Try again later.")
            return redirect("login")

        otp_record = PhoneOTP.objects.filter(
            user=user,
            is_verified=False,
            created_at__gte=timezone.now() - timedelta(minutes=5)
        ).order_by("-created_at").first()

        if otp_record and otp_record.otp == otp_input:
            otp_record.is_verified = True
            otp_record.save()

            profile.is_phone_verified = True
            profile.save()

            PhoneOTP.objects.filter(user=user).delete()
            cache.delete(attempts_key)

            login(request, user)
            request.session.pop("pending_user_id", None)

            # 🧹 prevent old OTP/login messages leaking into next session
            storage = messages.get_messages(request)
            list(storage)

            messages.success(request, "Phone verified successfully 🎉")
            return redirect("room_list")

        # ❌ FAIL CASE
        cache.set(attempts_key, attempts + 1, timeout=300)

        messages.error(request, "Invalid or expired OTP")

        return render(request, "listings/verify_phone.html", {
            "error_state": True,
            "cooldown_active": not can_resend_otp(user.id)
        })

    return render(request, "listings/verify_phone.html", {
        "cooldown_active": not can_resend_otp(user.id)
    })


def user_login(request):
    if request.method != "POST":
        return render(request, "listings/login.html")

    login_value = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""

    user_obj = User.objects.filter(email__iexact=login_value).first() \
        or User.objects.filter(username__iexact=login_value).first()

    if not user_obj:
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    user = authenticate(request, username=user_obj.username, password=password)

    if not user:
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    # 🔐 EMAIL CHECK
    if not user.profile.is_email_verified:
        messages.error(request, "Please verify your email first.")
        return redirect("login")

    # 📱 PHONE CHECK
    if not user.profile.is_phone_verified:

        # cooldown protection
        if not can_resend_otp(user.id):
            request.session["pending_user_id"] = user.id
            return redirect("verify_phone")
        
        # CLEAN OLD OTPs
        PhoneOTP.objects.filter(
            user=user,
            created_at__lt=timezone.now() - timedelta(minutes=10)
        ).delete()

        otp = generate_otp()

        PhoneOTP.objects.create(
            user=user,
            phone_number=user.profile.phone_number,
            otp=otp
        )

        send_otp_email(user, otp)
        set_otp_cooldown(user.id)

        request.session["pending_user_id"] = user.id

        messages.warning(request, "We sent you an OTP code.")
        return redirect("verify_phone")

    # 🧠 PROFILE COMPLETION GATE
    if profile_needs_update(user):
        messages.warning(request, "Please complete your profile.")
        return redirect("edit_profile")

    login(request, user)

    storage = messages.get_messages(request)
    list(storage)

    messages.success(request, f"Welcome back {get_display_name(user)} 👋")

    if getattr(user.profile, "role", None) == "landlord":
        return redirect("dashboard")

    return redirect("room_list")

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

    def dash(value):
        """Return a clean display value instead of blanks/None (prevents 'code leak' looking output)."""
        value = (value or "").strip() if isinstance(value, str) else value
        return value if value else "—"

    # =========================
    # Tenant panels (saved + viewed)
    # =========================
    favorites_qs = (
        Favorite.objects.filter(user=user)
        .select_related("room")
        .order_by("-created_at")
    )
    saved_rooms = [f.room for f in favorites_qs]

    viewed_stats = (
        RoomStat.objects.filter(user=user, stat_type="view")
        .select_related("room")
        .order_by("-created_at")
    )

    # dedupe viewed rooms without breaking sqlite
    seen = set()
    viewed_rooms = []
    for s in viewed_stats:
        if not s.room_id:
            continue
        if s.room_id in seen:
            continue
        seen.add(s.room_id)
        viewed_rooms.append(s.room)

    # =========================
    # Landlord analytics
    # =========================
    rooms_count = 0
    image_count = 0
    contact_count = 0

    if p.role == "landlord":
        rooms = Room.objects.filter(owner=user).order_by("-created_at")
        rooms_count = rooms.count()
        image_count = RoomImage.objects.filter(room__owner=user).count()
        contact_count = RoomStat.objects.filter(
            room__owner=user, stat_type__startswith="contact"
        ).count()

    # =========================
    # Header badge (template doesn't need if/else)
    # =========================
    persona_text = p.get_persona_display() if getattr(p, "persona", None) else "Not set"
    badge_text = f"{persona_text}" if p.role == "tenant" else "Landlord"
    verified_badge = "Verified" if (p.role == "landlord" and getattr(p, "is_verified", False)) else ""

    # =========================
    # Stats (split into link stats + plain stats to avoid template if)
    # =========================
    stat_cards = []
    stat_links = []

    if p.role == "tenant":
        stat_cards = [
            {"number": len(saved_rooms), "label": "Saved rooms"},
            {"number": len(viewed_rooms), "label": "Viewed rooms"},
        ]
    else:
        stat_links = [
            {"href": reverse("landlord_rooms"), "number": rooms_count, "label": "Rooms"},
            {"href": reverse("landlord_images_hub"), "number": image_count, "label": "Images"},
            {"href": reverse("contacts_analytics"), "number": contact_count, "label": "Contacts"},
        ]

    # =========================
    # Details rows (both roles)
    # =========================
    detail_rows = [
        {"label": "Name", "value": f"{dash(user.first_name)} {dash(user.last_name)}"},
        {"label": "Email", "value": dash(user.email)},
    ]

    if p.role == "tenant":
        detail_rows.append({"label": "Persona", "value": persona_text})
    else:
        detail_rows.extend(
            [
                {"label": "Cell", "value": dash(getattr(p, "phone_number", ""))},
                {"label": "Alt", "value": dash(getattr(p, "alt_no", ""))},
                {"label": "Address", "value": dash(getattr(p, "home_address", ""))},
                {"label": "Postal", "value": dash(getattr(p, "postal_code", ""))},
            ]
        )

    # =========================
    # Tenant sections (empty list for landlord, so template just renders nothing)
    # =========================
    tenant_sections = []
    if p.role == "tenant":
        tenant_sections = [
            {"title": "Saved rooms", "rooms": saved_rooms},
            {"title": "Viewed rooms", "rooms": viewed_rooms},
        ]

    context = {
        "p": p,

        # header
        "badge_text": badge_text,
        "verified_badge": verified_badge,

        # stats
        "stat_cards": stat_cards,
        "stat_links": stat_links,

        # details
        "detail_rows": detail_rows,

        # tenant lists
        "tenant_sections": tenant_sections,
    }

    return render(request, "listings/profile.html", context)

def can_resend_otp(user_id):
    key = f"otp_resend_{user_id}"
    return cache.get(key) is None

def set_otp_cooldown(user_id, seconds=90):
    cache.set(f"otp_resend_{user_id}", True, timeout=seconds)


@login_required
def edit_profile(request):
    user = request.user
    profile = user.profile

    u_form = UserUpdateForm(request.POST or None, instance=user)
    p_form = ProfileUpdateForm(request.POST or None, instance=profile)

    if request.method == "POST":

        if u_form.is_valid() and p_form.is_valid():

            changes = detect_profile_changes(user, profile, u_form, p_form)

            user_obj = u_form.save(commit=False)
            profile_obj = p_form.save(commit=False)

            if changes["email"]:
                handle_email_change(user_obj, profile_obj, changes["email"], request)

            if changes["phone"]:
                handle_phone_change(user_obj, profile_obj, changes["phone"])

            user_obj.save()
            profile_obj.save()

            # ✅ SUCCESS MESSAGE
            messages.success(request, "Profile updated successfully.")

            return redirect("profile")

        else:
            # ✅ SHOW ERROR MESSAGE (IMPORTANT UX)
            messages.error(request, "Please fix the errors below.")

    return render(request, "listings/edit_profile.html", {
        "u_form": u_form,
        "p_form": p_form,
        "p": profile
    })


@login_required
def toggle_favorite(request, room_id):
    room = get_object_or_404(Room, id=room_id, is_available=True)

    if not hasattr(request.user, "profile") or request.user.profile.role != "tenant":
        return HttpResponseForbidden("Only tenants can save rooms.")

    fav, created = Favorite.objects.get_or_create(
        user=request.user,
        room=room
    )

    if not created:
        fav.delete()
        messages.info(request, "Removed from saved rooms.")
    else:
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

    membership = get_or_create_membership(request.user)

    return render(
        request,
        "listings/dashboard.html",
        {
            "rooms": rooms,
            "image_count": image_count,
            "contact_count": contact_count,
            "show_profile_warning": show_profile_warning,
            "membership": membership,  
        },
    )


@login_required
@user_passes_test(is_landlord)
def add_room(request):
    return redirect("create_room")


@login_required
@user_passes_test(is_landlord)
def create_room(request):

    # ✅ ALWAYS ensure membership exists (SAFE)
    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    user_listings_count = request.user.rooms.count()

    # 🚫 BLOCK: expired trial
    if membership.is_trial and membership.is_trial_expired():
        messages.error(request, "Your trial has expired. Please upgrade.")
        return redirect("membership")

    # 🚫 BLOCK: listing limit reached
    if not membership.can_create_listing(user_listings_count):
        messages.warning(
            request,
            "🚫 You’ve reached your listing limit. Upgrade to add more rooms."
        )
        return redirect("membership")

    form = RoomForm(request.POST or None, request.FILES or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                room = form.save(commit=False)
                room.owner = request.user
                room.full_clean()
                room.save()

        except ValidationError as e:
            form.add_error(None, e)
            return render(request, "listings/create_room.html", {"form": form})

        except IntegrityError:
            form.add_error(
                None,
                "This listing already exists (same title, location, type and price)."
            )
            return render(request, "listings/create_room.html", {"form": form})

        # 📸 IMAGES
        uploaded_images = request.FILES.getlist("images")
        if uploaded_images:
            uploaded_images = uploaded_images[:10]

            for f in uploaded_images:
                RoomImage.objects.create(room=room, image=f)

            messages.success(request, "Room created successfully with images.")
        else:
            messages.success(request, "Room created successfully.")

        # 📧 EMAIL AFTER COMMIT
        transaction.on_commit(lambda: send_template_email(
            subject="Your listing is now live 🎉",
            to_email=request.user.email,
            template="emails/room_live.html",
            context={"room": room, "year": 2026}
        ))

        return redirect("upload_room_images", room.id)

    return render(request, "listings/create_room.html", {"form": form})


@login_required
@user_passes_test(is_landlord)
def edit_room(request, pk):

    if not require_active_membership(request.user):
        return redirect("membership")

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

@login_required
def create_listing(request):

    # ✅ Always ensure membership exists
    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    # 🚫 BLOCK: trial expired
    if membership.is_trial and membership.is_trial_expired():
        messages.error(request, "Your trial has expired. Please upgrade.")
        return redirect("membership")

    # 📊 Count listings (single source of truth)
    user_listings_count = request.user.rooms.count()

    # 🚫 BLOCK: limit reached (uses your model logic)
    if not membership.can_create_listing(user_listings_count):
        messages.warning(
            request,
            "🚫 You’ve reached your listing limit. Upgrade your membership to add more."
        )
        return redirect("membership")

    # 🧾 FORM HANDLING
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)

        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()

            messages.success(request, "Listing created successfully!")
            return redirect("dashboard")

    else:
        form = ListingForm()

    return render(request, "listings/create_listing.html", {"form": form})


# -----------------------------
# IMAGES (upload/delete/manage)
# -----------------------------

@login_required
def upload_room_images(request, room_id):
    if not require_active_membership(request.user):
        return redirect("membership")

    room = get_object_or_404(Room, id=room_id, owner=request.user)

    if request.method == "POST":
        existing_count = RoomImage.objects.filter(room=room).count()
        remaining = max(0, 10 - existing_count)

        new_files = request.FILES.getlist("images")

        # If room already has 10 images
        if remaining == 0:
            messages.warning(request, "This room already has 10 images (max). Delete one to add more.")
            return redirect("edit_room_images", pk=room.id)

        # Save only up to remaining slots
        for img in new_files[:remaining]:
            RoomImage.objects.create(room=room, image=img)

        # If they tried to upload too many
        if len(new_files) > remaining:
            messages.warning(request, f"Only {remaining} more images were allowed (max 10 per room).")
        else:
            messages.success(request, "Images uploaded ✅")

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

        send_template_email(
            subject="New inquiry on your listing",
            to_email=room.owner.email,
            template="emails/new_inquiry.html",
            context={
                "room": room,
                "user": request.user,
                "year": 2026
            }
        )

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

def resend_otp(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return JsonResponse({
            "success": False,
            "error": "Session expired. Please login again."
        }, status=401)

    user = User.objects.get(id=user_id)

    cache_key = f"otp_resend_{user.id}"

    if cache.get(cache_key):
        return JsonResponse({
            "success": False,
            "error": "Wait 60 seconds before requesting another OTP",
            "cooldown": 60
        }, status=429)

    otp = generate_otp()

    PhoneOTP.objects.create(
        user=user,
        phone_number=user.profile.phone_number,
        otp=otp
    )

    send_otp_email(user, otp)

    cache.set(cache_key, True, timeout=60)

    return JsonResponse({
        "success": True,
        "message": "OTP sent",
        "cooldown": 60
    })

@login_required
def heatmap(request):
    return render(request, "listings/heatmap.html")


def terms(request):
    return render(request, "listings/terms.html")

def privacy(request):
    return render(request, "listings/privacy.html")

def safety(request):
    return render(request, "listings/safety.html")

@require_POST
def report_room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    detail = (request.POST.get("detail") or "").strip()

    # ✅ Simple logging-only report for now (safe + no DB changes)
    # Later we can add a Report model.
    if not reason:
        messages.error(request, "Please select a reason to report this listing.")
        return redirect("room_detail", pk=room.id)

    # This is enough for MVP: WE can wire to email/admin later
    messages.success(request, "Thanks! Your report was received ✅ We’ll review this listing.")
    return redirect("room_detail", pk=room.id)

def resend_verification(request):
    if not request.user.is_authenticated:
        return redirect("login")

    user = request.user

    EmailVerification.objects.filter(user=user, is_verified=False).delete()

    verification = EmailVerification.objects.filter(
        user=user,
        is_verified=False
    ).order_by("-created_at").first()

    if not verification:
        verification = EmailVerification.objects.create(user=user)

    def build_domain(request):
        current_site = get_current_site(request)
        scheme = "https" if not settings.DEBUG else "http"
        return f"{scheme}://{current_site.domain}"
    
    domain = build_domain(request)
    verify_link = f"{domain}/verify-email/{verification.token}/"

    send_template_email(
        subject="Verify your Rooms4You account",
        to_email=user.email,
        template="emails/verify_email.html",
        context={
            "user": user,
            "verify_link": verify_link,
            "year": 2026
        }
    )

    messages.success(request, "Verification email sent again ✅")
    return redirect("dashboard")

def handle_email_change(user_obj, profile_obj, new_email, request):
    if not new_email or new_email == user_obj.email:
        return

    profile_obj.pending_email = new_email
    profile_obj.email_change_token = uuid4()
    profile_obj.save()

    domain = get_current_site(request).domain
    scheme = "https" if not settings.DEBUG else "http"
    base = f"{scheme}://{domain}"

    confirm_link = f"{base}/confirm-email-change/{profile_obj.email_change_token}/"

    send_template_email(
        subject="Confirm your new email",
        to_email=new_email,
        template="emails/confirm_email_change.html",
        context={
            "user": user_obj,
            "confirm_link": confirm_link,
        }
    )

@login_required
def confirm_email_change(request, token):
    profile = Profile.objects.filter(email_change_token=token).first()

    if not profile:
        messages.error(request, "Invalid or expired link.")
        return redirect("login")

    if str(profile.email_change_token) != str(token):
        messages.error(request, "Invalid or expired email change link.")
        return redirect("profile")

    request.user.email = profile.pending_email
    request.user.save()

    profile.pending_email = None
    profile.email_change_token = None
    profile.is_email_verified = True
    profile.save()

    return render(request, "listings/email_change_success.html")
    

def detect_profile_changes(user, profile, u_form, p_form):
    u = u_form.cleaned_data
    p = p_form.cleaned_data

    changes = {
        "email": None,
        "phone": None,
    }

    if u.get("email") and u["email"] != user.email:
        changes["email"] = u["email"]

    if p.get("phone_number") and p["phone_number"] != profile.phone_number:
        changes["phone"] = p["phone_number"]

    return changes

def handle_phone_change(user_obj, profile_obj, new_phone):
    if not new_phone or new_phone == profile_obj.phone_number:
        return
    
    profile_obj.phone_number = new_phone
    profile_obj.is_phone_verified = False

@login_required
def request_upgrade(request):
    membership = get_or_create_membership(request.user)

    membership.mark_as_paid()

    messages.success(request, "Payment request submitted. We will verify shortly.")
    return redirect("dashboard")
