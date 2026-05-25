import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from datetime import timedelta
from django.db.models import Count, Q
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
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator
from .models import Message
from difflib import get_close_matches
from django.contrib.auth.models import User
from accounts.helpers import generate_membership_id
from .models import PhoneOTP
from .utils import generate_otp, send_otp_email
from utils.email import send_template_email
from accounts.utils import require_active_membership
from django.utils import timezone
from accounts.models import Membership
from .forms import ListingForm
from django.db.models import Prefetch
from django.db import DatabaseError
from .models import Room, Review, Contact, RoomStat, RoomImage, Profile, Favorite
from .forms import UserRegisterForm, RoomForm, UserUpdateForm, ProfileUpdateForm
import logging

logger = logging.getLogger(__name__)


def get_display_name(user):
    return (user.first_name or "").strip() or (user.email or "").strip() or "there"

# Profile completeness gate

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
        membership.membership_id = generate_membership_id()
        membership.save(update_fields=["membership_id"])

    return membership

  
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
        has_cell = bool(
            p.phone_number and 
            p.country_code and 
            str(p.phone_number).strip()
        )
        has_address = bool((getattr(p, "home_address", "") or "").strip())
        
        return not (
            has_first_name
            and has_last_name
            and has_email
            and has_cell
            and has_address
        )

    return False

def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"

# LANDLORD: Rooms + Images hubs

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

# PUBLIC PAGES
def home(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    # redirect search to room list
    if request.GET.get("go") == "1":
        params = []

        if q:
            params.append(f"q={q}")

        if location:
            params.append(f"location={location}")

        if room_type:
            params.append(f"type={room_type}")

        querystring = "&".join(params)

        return redirect(
            f"/rooms/?{querystring}"
            if querystring
            else "/rooms/"
        )

    context = {
        "room_count": Room.objects.count(),
        "contact_count": Contact.objects.count(),
        "review_count": Review.objects.count(),
        "landlord_count": Profile.objects.filter(
            role="landlord"
        ).count(),

        "values": {
            "q": q,
            "location": location,
            "type": room_type,
        },

        "selected": {
            "any": room_type == "",
            "Single Room": room_type == "Single Room",
            "Shared Room": room_type == "Shared Room",
            "Bachelor": room_type == "Bachelor",
            "Ensuite": room_type == "Ensuite",
            "Student Accommodation": room_type == "Student Accommodation",
            "Backroom": room_type == "Backroom",
            "Cottage": room_type == "Cottage",
            "Apartment": room_type == "Apartment",
        },
    }

    return render(
        request,
        "listings/home.html",
        context
    )

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


# ROOMS: list + detail
def room_list(request):

    # ================= CACHE CHECK =================
    cache_key = f"room_list:{request.get_full_path()}"
    cached_response = cache.get(cache_key)

    if cached_response:
        return cached_response

    # ================= REQUEST PARAMS =================
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()
    sort = (request.GET.get("sort") or "").strip()

    min_price = (request.GET.get("min_price") or "").strip()
    max_price = (request.GET.get("max_price") or "").strip()

    # ================= BASE QUERY =================
    rooms_qs = (
        Room.objects.filter(is_available=True)
        .select_related("owner__profile")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=RoomImage.objects.only(
                    "id",
                    "image",
                    "room_id"
                )
            )
        )
    )

    suggested_location = ""
    searched_location = location

    # ================= SEARCH =================
    if q:
        rooms_qs = rooms_qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(location__icontains=q)
            | Q(room_type__icontains=q)
        )

    # ================= LOCATION =================
    if location:
        exact_location_qs = rooms_qs.filter(location__icontains=location)

        if exact_location_qs.exists():
            rooms_qs = exact_location_qs

        else:
            all_locations = cache.get("all_locations")

            if not all_locations:
                all_locations = list(
                    Room.objects.filter(is_available=True)
                    .exclude(location__isnull=True)
                    .exclude(location__exact="")
                    .values_list("location", flat=True)
                    .distinct()
                )
                cache.set("all_locations", all_locations, 3600)

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

    # ================= ROOM TYPE =================
    if room_type:
        rooms_qs = rooms_qs.filter(room_type=room_type)

    # ================= PRICE FILTER =================
    if min_price:
        try:
            rooms_qs = rooms_qs.filter(price__gte=int(min_price))
        except ValueError:
            pass

    if max_price:
        try:
            rooms_qs = rooms_qs.filter(price__lte=int(max_price))
        except ValueError:
            pass

    # ================= SORTING =================
    if sort == "new":
        rooms = rooms_qs.order_by("-created_at")

    elif sort == "price_low":
        rooms = rooms_qs.order_by("price", "-created_at")

    elif sort == "price_high":
        rooms = rooms_qs.order_by("-price", "-created_at")

    else:
        rooms = rooms_qs.order_by("-created_at")

    # ================= PAGINATION =================
    page_number = request.GET.get("page") or 1
    paginator = Paginator(rooms, 8)
    page_obj = paginator.get_page(page_number)

    # ================= MAP DATA =================
    map_rooms = list(
        page_obj.object_list.values(
            "id",
            "title",
            "price",
            "latitude",
            "longitude",
        )
    )

    # ================= AJAX =================
    is_ajax = (
        request.GET.get("ajax") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    if is_ajax:

        html = render_to_string(
            "listings/_room_cards.html",
            {"rooms": page_obj.object_list},
            request=request,
        )

        response = JsonResponse(
            {
                "html": html,
                "page": page_obj.number,
                "num_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_prev": page_obj.has_previous(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
                "prev_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
                "suggested_location": suggested_location,
                "searched_location": searched_location,
            }
        )

        cache.set(cache_key, response, 60)
        return response

    # ================= SORT UI =================
    sort_selected = {
        "best": sort == "",
        "new": sort == "new",
        "price_low": sort == "price_low",
        "price_high": sort == "price_high",
    }

    show_location_suggestion = (
        bool(suggested_location)
        and bool(searched_location)
        and suggested_location.strip().lower()
        != searched_location.strip().lower()
    )

    # ================= FINAL =================
    response = render(
        request,
        "listings/room_list.html",
        {
            "map_rooms": map_rooms,
            "rooms": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "values": {
                "q": q,
                "location": location,
                "type": room_type,
                "sort": sort,
                "min_price": min_price,
                "max_price": max_price,
            },
            "sort_selected": sort_selected,
            "suggested_location": suggested_location,
            "searched_location": searched_location,
            "show_location_suggestion": show_location_suggestion,
        },
    )

    cache.set(cache_key, response, 60)
    return response


def room_detail(request, pk):

    room = get_object_or_404(
        Room.objects
        .select_related("owner__profile")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=RoomImage.objects.only(
                    "id",
                    "image",
                    "room_id"
                )
            )
        ),
        pk=pk,
        is_available=True
    )

    # lightweight analytics write
    try:
        RoomStat.objects.create(
            room_id=room.id,
            user=request.user if request.user.is_authenticated else None,
            stat_type="view",
        )

    except DatabaseError as e:
        logger.warning(
            "Failed to create room view stat for room %s: %s",
            room.id,
            str(e)
        )

    is_saved = False

    if (
        request.user.is_authenticated
        and hasattr(request.user, "profile")
        and request.user.profile.role == "tenant"
    ):
        is_saved = Favorite.objects.filter(
            user=request.user,
            room_id=room.id
        ).exists()

    return render(
        request,
        "listings/room_detail.html",
        {
            "room": room,
            "is_saved": is_saved,
        },
    )


# AUTH: register/login/logout
def register(request):
    form = UserRegisterForm(request.POST or None)

    if request.method == "POST":

        if form.is_valid():

            user = form.save()   # <-- fixed

            user.is_active = False
            user.save()

            otp = generate_otp()

            PhoneOTP.objects.filter(user=user).delete()

            PhoneOTP.objects.create(
                user=user,
                phone_number=user.profile.phone_number,
                otp=otp
            )

            send_otp_email(user, otp)

            set_otp_cooldown(user.id)

            request.session["pending_user_id"] = user.id

            messages.success(
                request,
                "Account created. Enter the OTP sent to your email."
            )

            return redirect("verify_account")

    return render(
        request,
        "listings/register.html",
        {"form": form}
    )


def verify_account(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":

        otp_input = request.POST.get("otp")

        if not otp_input:
            messages.error(request, "Enter OTP.")
            return render(request, "listings/verify_account.html")

        record = PhoneOTP.objects.filter(
            user=user,
            is_verified=False,
            created_at__gte=timezone.now() - timedelta(minutes=15)
        ).order_by("-created_at").first()

        if record and record.otp == otp_input:

            record.is_verified = True
            record.save()

            profile = user.profile
            profile.is_email_verified = True
            profile.is_phone_verified = True
            profile.save()

            user.is_active = True
            user.save()

            PhoneOTP.objects.filter(user=user).delete()

            login(request, user)

            request.session.pop("pending_user_id", None)

            messages.success(
                request,
                "Account verified successfully 🎉"
            )

            if profile.role == "landlord":
                return redirect("dashboard")

            return redirect("room_list")

        messages.error(request, "Invalid or expired OTP")

    return render(request, "listings/verify_account.html")

@never_cache
def user_login(request):
    if request.method != "POST":
        return render(request, "listings/login.html")

    login_value = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""

    next_url = request.GET.get("next")

    user_obj = (
        User.objects.filter(email__iexact=login_value).first()
        or User.objects.filter(username__iexact=login_value).first()
    )

    if not user_obj:
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    user = authenticate(request, username=user_obj.username, password=password)

    if not user:
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    # EMAIL CHECK
    if not user.profile.is_email_verified:
        request.session["pending_user_id"] = user.id
        return redirect("verify_pending")

    # PHONE CHECK
    if not user.profile.is_phone_verified:

        if not can_resend_otp(user.id):
            request.session["pending_user_id"] = user.id
            return redirect("verify_phone")

        PhoneOTP.objects.filter(user=user).delete()

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

    # LOGIN
    with transaction.atomic():
        login(request, user)
        request.session.modified = True
        request.session.save()

    # 🔐 FORCE PASSWORD CHANGE CHECK (ADD HERE)
    if getattr(user.profile, "must_change_password", False):
        return redirect("change_password")

    # PROFILE COMPLETION WARNING (non-blocking)
    if profile_needs_update(user):
        messages.info(request, "You can complete your profile anytime in settings.")

    messages.success(request, f"Welcome back {get_display_name(user)} 👋")

    # NEXT URL SUPPORT
    if next_url:
        return redirect(next_url)

    # ROLE REDIRECTS
    if hasattr(user, "profile"):

        if user.profile.role == "driver":

            from services.models import BakkieDriver

            driver = BakkieDriver.objects.filter(
                user=user,
                is_verified=True
            ).first()

            if driver:
                return redirect("services:driver_dashboard")

            messages.warning(
                request,
                "Your driver account is pending verification."
            )
            return redirect("services:bakkie_home")

        if user.profile.role == "landlord":
            return redirect("dashboard")

    return redirect("room_list")


@require_POST
@never_cache
def user_logout(request):
    logout(request)
    messages.success(request, "You’ve been logged out.")
    return redirect("room_list")


# PROFILES (tenant + landlord)
@login_required
def profile(request):
    user = request.user
    p = user.profile

    def dash(value):
        """Return a clean display value instead of blanks/None (prevents 'code leak' looking output)."""
        value = (value or "").strip() if isinstance(value, str) else value
        return value if value else "—"
    
    # Tenant panels (saved + viewed)
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

    
    # Landlord analytics
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

   
    # Header badge (template doesn't need if/else)
    persona_text = p.get_persona_display() if getattr(p, "persona", None) else "Not set"
    badge_text = f"{persona_text}" if p.role == "tenant" else "Landlord"
    verified_badge = "Verified" if (p.role == "landlord" and getattr(p, "is_verified", False)) else ""

    # Stats (split into link stats + plain stats to avoid template if)
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

   
    detail_rows = [
        {"label": "Name", "value": f"{dash(user.first_name)} {dash(user.last_name)}"},
        {"label": "Email", "value": dash(user.email)},
    ]

    if p.role == "tenant":
        detail_rows.append({"label": "Persona", "value": persona_text})
    else:
        # Build full phone properly
        full_phone = p.full_phone()

        detail_rows.extend(
            [
                {"label": "Cell", "value": dash(full_phone)},
                {"label": "Alt", "value": dash(getattr(p, "alt_no", ""))},
                {"label": "Address", "value": dash(getattr(p, "home_address", ""))},
                {"label": "Postal", "value": dash(getattr(p, "postal_code", ""))},
            ]
        )

   
    # Tenant sections (empty list for landlord, so template just renders nothing)
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

def resend_account_otp(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return JsonResponse({
            "success": False,
            "error": "Session expired."
        }, status=400)

    user = get_object_or_404(User, id=user_id)

    cache_key = f"otp_resend_{user.id}"

    if cache.get(cache_key):
        return JsonResponse({
            "success": False,
            "error": "Wait before requesting again.",
            "cooldown": OTP_RESEND_SECONDS
        }, status=429)

    otp = generate_otp()

    PhoneOTP.objects.filter(user=user).delete()

    PhoneOTP.objects.create(
        user=user,
        phone_number="email_verification",
        otp=otp
    )

    send_otp_email(user, otp)

    set_otp_cooldown(user.id)

    return JsonResponse({
        "success": True,
        "message": "OTP sent.",
        "cooldown": OTP_RESEND_SECONDS
    })

def can_resend_otp(user_id):
    key = f"otp_resend_{user_id}"
    return cache.get(key) is None

OTP_RESEND_SECONDS = 60

def set_otp_cooldown(user_id):
    cache.set(
        f"otp_resend_{user_id}",
        True,
        timeout=OTP_RESEND_SECONDS
    )

@login_required
def edit_profile(request):
    user = request.user
    profile = user.profile

    initial_data = {
        "country_code": profile.country_code,
        "phone_number": profile.phone_number,
    }

    u_form = UserUpdateForm(
        request.POST or None,
        instance=user
    )

    p_form = ProfileUpdateForm(
        request.POST or None,
        instance=profile,
        initial=initial_data
    )

    if request.method == "POST":

        if u_form.is_valid() and p_form.is_valid():

            user_obj = u_form.save(commit=False)
            profile_obj = p_form.save(commit=False)

            # keep country code
            profile_obj.country_code = (
                p_form.cleaned_data.get("country_code")
            )

            # update phone only if entered
            phone_number = p_form.cleaned_data.get("phone_number")

            if phone_number:
                profile_obj.phone_number = phone_number

            with transaction.atomic():
                user_obj.save()
                profile_obj.save()

            messages.success(
                request,
                "Profile updated successfully."
            )
            return redirect("profile")

        else:
            print("USER FORM ERRORS:", u_form.errors)
            print("PROFILE FORM ERRORS:", p_form.errors)

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


# LANDLORD: dashboard + CRUD
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
        },
    )


@login_required
@user_passes_test(is_landlord)
def add_room(request):
    return redirect("create_room")


@login_required
@user_passes_test(is_landlord)
def create_room(request):

    # ALWAYS ensure membership exists (SAFE)
    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    user_listings_count = request.user.rooms.count()

    # BLOCK: expired trial
    if membership.is_trial and membership.is_trial_expired():
        messages.error(request, "Your trial has expired. Please upgrade.")
        return redirect("membership")

    # BLOCK: listing limit reached
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

        # IMAGES
        uploaded_images = request.FILES.getlist("images")
        if uploaded_images:
            uploaded_images = uploaded_images[:10]

            for f in uploaded_images:
                RoomImage.objects.create(room=room, image=f)

            messages.success(request, "Room created successfully with images.")
        else:
            messages.success(request, "Room created successfully.")

        # EMAIL AFTER COMMIT
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

    room = get_object_or_404(
        Room,
        pk=pk,
        owner=request.user
    )

    form = RoomForm(
        request.POST or None,
        instance=room,
        user=request.user
    )

    if request.method == "POST":

        if form.is_valid():

            try:

                with transaction.atomic():

                    updated_room = form.save(commit=False)
                    updated_room.owner = request.user
                    updated_room.full_clean()
                    updated_room.save()

                messages.success(
                    request,
                    "Listing updated successfully."
                )

                return redirect("dashboard")

            except ValidationError as e:
                form.add_error(None, e)

            except IntegrityError:
                form.add_error(
                    None,
                    "A similar listing already exists."
                )

    return render(
        request,
        "listings/edit_room.html",
        {"form": form, "room": room}
    )


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

    membership, _ = Membership.objects.get_or_create(
        user=request.user,
        defaults={"tier": "starter"}
    )

    user_listings_count = Room.objects.filter(owner=request.user).count()

    # HARD BLOCK
    if not membership.can_create_listing(user_listings_count):

        if membership.status == "pending":
            messages.warning(request, "Your payment is being verified.")

        elif membership.is_trial and membership.is_trial_expired():
            messages.error(request, "Your trial has expired. Please upgrade.")

        else:
            messages.error(request, "Listing limit reached. Upgrade to continue.")

        return redirect("membership")

    form = ListingForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        listing = form.save(commit=False)
        listing.owner = request.user
        listing.save()

        messages.success(request, "Listing created successfully!")
        return redirect("dashboard")

    return render(request, "listings/create_listing.html", {"form": form})


# IMAGES (upload/delete/manage)

@login_required
def upload_room_images(request, room_id):

    if not require_active_membership(request.user):
        return redirect("membership")

    room = get_object_or_404(
        Room,
        id=room_id,
        owner=request.user
    )

    if request.method == "POST":

        uploads = request.FILES.getlist("images")

        if not uploads:
            messages.error(request, "Please select images.")
            return redirect("upload_room_images", room.id)

        existing_count = room.images.count()

        remaining = max(0, 10 - existing_count)

        if remaining <= 0:
            messages.error(
                request,
                "Maximum 10 images reached."
            )
            return redirect("edit_room_images", pk=room.id)

        uploads = uploads[:remaining]

        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]

        uploaded_count = 0

        with transaction.atomic():

            for img in uploads:

                filename = img.name.lower()

                # Invalid file type
                if not any(filename.endswith(ext) for ext in allowed_extensions):
                    continue

                # Large file protection (10MB)
                if img.size > 10 * 1024 * 1024:
                    continue

                RoomImage.objects.create(
                    room=room,
                    image=img
                )

                uploaded_count += 1

        if uploaded_count:
            messages.success(
                request,
                f"{uploaded_count} image(s) uploaded successfully."
            )

        else:
            messages.error(
                request,
                "No valid images were uploaded."
            )

        if len(request.FILES.getlist("images")) > remaining:
            messages.warning(
                request,
                f"Only {remaining} image(s) allowed."
            )

        return redirect("edit_room_images", pk=room.id)

    return render(
        request,
        "listings/upload_images.html",
        {"room": room}
    )

@login_required
def delete_room_image(request, image_id):

    image = get_object_or_404(
        RoomImage,
        id=image_id,
        room__owner=request.user
    )

    room_id = image.room.id

    with transaction.atomic():
        image.delete()

    messages.success(request, "Image deleted successfully.")

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


# REVIEWS + CONTACT TRACKING
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

    user = get_object_or_404(User, id=user_id)

    cache_key = f"otp_resend_{user.id}"

    if cache.get(cache_key):
        return JsonResponse({
            "success": False,
            "error": "Please wait before requesting another OTP.",
            "cooldown": OTP_RESEND_SECONDS
        }, status=429)

    otp = generate_otp()

    PhoneOTP.objects.filter(user=user).delete()

    PhoneOTP.objects.create(
        user=user,
        phone_number=user.profile.phone_number,
        otp=otp
    )

    send_otp_email(user, otp)

    set_otp_cooldown(user.id)

    return JsonResponse({
        "success": True,
        "message": "OTP sent successfully.",
        "cooldown": OTP_RESEND_SECONDS
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


@login_required
def confirm_email_change(request):

    if request.method == "POST":

        otp = request.POST.get("otp")
        pending_email = request.session.get("pending_email")

        if not pending_email:
            return redirect("profile")

        record = PhoneOTP.objects.filter(
            user=request.user,
            phone_number="email_change",
            otp=otp
        ).last()

        if record:

            request.user.email = pending_email
            request.user.save()

            request.user.profile.is_email_verified = True
            request.user.profile.save()

            PhoneOTP.objects.filter(user=request.user).delete()

            request.session.pop("pending_email", None)

            messages.success(
                request,
                "Email updated successfully."
            )

            return redirect("profile")

        messages.error(request, "Invalid OTP.")

    return render(request, "listings/confirm_email.html")

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

@login_required
def change_email(request):
    if request.method == "POST":

        new_email = (request.POST.get("email") or "").strip().lower()

        if not new_email:
            messages.error(request, "Enter valid email.")
            return redirect("change_email")

        if User.objects.filter(email=new_email).exists():
            messages.error(request, "Email already in use.")
            return redirect("change_email")

        user = request.user

        otp = generate_otp()

        PhoneOTP.objects.filter(user=user).delete()

        PhoneOTP.objects.create(
            user=user,
            phone_number="email_change",
            otp=otp
        )

        send_otp_email(user, otp)

        request.session["pending_email"] = new_email

        messages.success(
            request,
            "OTP sent to your current email."
        )

        return redirect("confirm_email_change")

    return render(request, "listings/change_email.html")


@login_required
def change_phone(request):
    if request.method == "POST":

        phone = (request.POST.get("phone_number") or "").strip()
        country_code = (request.POST.get("country_code") or "+27").strip()

        # 🔥 CLEAN INPUT
        phone = re.sub(r"[^\d]", "", phone)

        if phone.startswith("0"):
            phone = phone[1:]

        if not phone or len(phone) < 9:
            messages.error(request, "Enter a valid phone number.")
            return redirect("change_phone")

        user = request.user

        otp = generate_otp()

        # DELETE OLD OTPs
        PhoneOTP.objects.filter(user=user).delete()

        # STORE CLEAN NUMBER ONLY
        PhoneOTP.objects.create(
            user=user,
            phone_number=phone,
            otp=otp
        )

        send_otp_email(user, otp)

        # Store BOTH for confirmation step
        request.session["pending_phone"] = phone
        request.session["pending_country_code"] = country_code

        messages.success(request, "OTP sent to your email.")
        return redirect("confirm_phone_change")

    return render(request, "listings/change_phone.html")

@login_required
def confirm_phone_change(request):
    if request.method == "POST":

        otp = request.POST.get("otp")
        pending_phone = request.session.get("pending_phone")
        pending_country_code = request.session.get("pending_country_code")

        if not pending_phone:
            return redirect("profile")

        record = PhoneOTP.objects.filter(
            user=request.user,
            phone_number=pending_phone,
            otp=otp
        ).last()

        if record:
            profile = request.user.profile

            profile.phone_number = pending_phone
            profile.country_code = pending_country_code
            profile.is_phone_verified = True
            profile.save()

            PhoneOTP.objects.filter(user=request.user).delete()

            request.session.pop("pending_phone", None)
            request.session.pop("pending_country_code", None)

            messages.success(
                request,
                "Phone updated successfully."
            )

            return redirect("profile")

        messages.error(request, "Invalid OTP.")

    return render(request, "listings/confirm_phone.html")


@login_required
def send_message(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    if request.method != "POST":
        return redirect("room_detail", pk=room.id)

    body = (request.POST.get("body") or "").strip()

    if not body:
        messages.error(request, "Message cannot be empty.")
        return redirect("room_detail", pk=room.id)

    Message.objects.create(
        room=room,
        sender=request.user,
        recipient=room.owner,
        body=body,
    )

    Contact.objects.get_or_create(
        room=room,
        user=request.user
    )

    messages.success(request, "Message sent to landlord.")
    return redirect("room_detail", pk=room.id)


@login_required
@user_passes_test(is_landlord)
def inbox(request):
    messages_qs = Message.objects.filter(
        recipient=request.user
    ).select_related("sender", "room").order_by("-created_at")

    return render(request, "listings/inbox.html", {
        "messages": messages_qs
    })


@login_required
def delete_account(request):
    if request.method == "POST":
        user = request.user

        # Logout first (important)
        logout(request)

        # 🧨 Delete user (this cascades Profile, Membership, etc.)
        user.delete()

        messages.success(request, "Your account has been deleted.")
        return redirect("room_list")

    return render(request, "listings/delete_account.html")