import re
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from datetime import timedelta
from django.db.models import Count, Q, F, IntegerField, ExpressionWrapper, Avg
from django.conf import settings
POPULAR_SCORE_THRESHOLD = getattr(settings, "POPULAR_SCORE_THRESHOLD", 100)
from django.http import HttpResponseForbidden, HttpResponse, Http404
from django.contrib.auth.views import PasswordResetView
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

try:
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.voice_response import VoiceResponse
except Exception:
    # twilio is in requirements.txt, but guarded the same defensive way
    # as this project's existing Celery imports (see tasks.py) - a
    # missing/failed twilio install shouldn't crash the whole app, it
    # should just make call_landlord() fall back to in-app messaging.
    TwilioClient = None
    VoiceResponse = None
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
from .models import Message
from difflib import get_close_matches
from django.contrib.auth.models import User
from accounts.helpers import generate_membership_id
from .models import PhoneOTP
from .utils import generate_otp, send_otp_email, send_welcome_email
from accounts.state_engine import get_user_state
from utils.email import send_template_email
from accounts.utils import require_active_membership
from django.utils import timezone
from accounts.models import Membership
from secrets import compare_digest
from django.utils.html import strip_tags
from PIL import Image
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


def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"

# LANDLORD: Rooms + Images hubs

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


@login_required
def toggle_room_vacancy(request, room_id):
    """
    A single-click vacancy toggle for the landlord's room list, so
    marking a room occupied/vacant doesn't require opening the full
    edit form and finding the right field.

    Always normalizes availability_status to "now": Room.clean() puts
    extra constraints on "from" (requires available_from, forces
    available_units=0) and "mixed" (available_units must be strictly
    between 0 and total_units) - constraints this quick toggle has no
    way to satisfy without more input from the landlord. "now" has no
    such constraint, and available_units<=0 already renders as "Fully
    occupied" regardless of status text (see Room.availability_badge_text/
    availability_state), so this stays visually correct either way.
    """
    room = get_object_or_404(Room, id=room_id, owner=request.user)

    if request.method != "POST":
        return redirect("landlord_rooms")

    if room.is_available and room.available_units > 0:
        room.is_available = False
        room.available_units = 0
        room.availability_status = "now"
        messages.success(request, f'"{room.title}" marked as occupied.')
    else:
        room.is_available = True
        room.available_units = max(room.total_units, 1)
        room.availability_status = "now"
        messages.success(request, f'"{room.title}" marked as available.')

    room.save()
    return redirect("landlord_rooms")


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


def support(request):
    return render(request, "listings/support.html")


def terms(request):
    return render(
        request,
        "listings/terms.html"
    )


def privacy(request):
    return render(
        request,
        "listings/privacy.html"
    )


def safety(request):
    return render(
        request,
        "listings/safety.html"
    )


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
    cache_key = f"room_list:{request.user.id if request.user.is_authenticated else 'anon'}:{request.get_full_path()}"

    # ================= REQUEST PARAMS =================
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()
    sort = (request.GET.get("sort") or "").strip()

    min_price = (request.GET.get("min_price") or "").strip()
    max_price = (request.GET.get("max_price") or "").strip()

    # ================= SANITIZE INPUT =================
    # whitelist sort values and room types to avoid unexpected filters
    valid_sorts = {"", "new", "price_low", "price_high"}
    if sort not in valid_sorts:
        sort = ""

    valid_room_types = [t[0] for t in Room.ROOM_TYPES]
    if room_type and room_type not in valid_room_types:
        room_type = ""

    # ================= AJAX (early) =================
    is_ajax = (
        request.GET.get("ajax") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    # If we have a cached payload for this exact request, return it immediately for AJAX
    cached_payload = cache.get(cache_key)
    if is_ajax and cached_payload:
        return JsonResponse(cached_payload)

    # ================= BASE QUERY =================
    # Limit loaded fields in list view to reduce memory/serialization overhead.
    rooms_qs = (
        Room.objects.filter(is_available=True)
        .select_related("owner__profile")
        .only(
            "id",
            "title",
            "price",
            "location",
            "latitude",
            "longitude",
            "score",
            "hits",
            "created_at",
            "owner_id",
            "available_units",
            "total_units",
            "availability_status",
            "available_from",
        )
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
        # annotate average rating to avoid per-object aggregates in templates
        # use a different name than the `avg_rating` property to avoid
        # AttributeError when Django tries to set the annotated value.
        .annotate(avg_rating_value=Avg("reviews__rating"))
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

    # Optionally use materialized score for fast ordering; falls back to DB-side
    # aggregation when `USE_MATERIALIZED_SCORE` is False.
    USE_MATERIALIZED_SCORE = getattr(settings, "USE_MATERIALIZED_SCORE", True)


    # ================= SORTING =================
    # accept both 'new' and 'newest' from templates
    if sort in {"new", "newest"}:
        rooms = rooms_qs.order_by("-created_at")

    elif sort == "oldest":
        rooms = rooms_qs.order_by("created_at")

    elif sort == "price_low":
        rooms = rooms_qs.order_by("price", "-created_at")

    elif sort == "price_high":
        rooms = rooms_qs.order_by("-price", "-created_at")

    else:
        # Default 'best match' -- order by composite score then newest
        rooms = rooms_qs.order_by("-score", "-created_at")

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

    # cache popular ids to avoid running the aggregate query on every request
    cache_key = f"popular_ids_v1:{'mat' if USE_MATERIALIZED_SCORE else 'calc'}:{POPULAR_SCORE_THRESHOLD}"
    popular_ids = cache.get(cache_key)

    if popular_ids is None:
        if USE_MATERIALIZED_SCORE:
            popular_ids = list(
                Room.objects.filter(is_available=True, score__gte=POPULAR_SCORE_THRESHOLD)
                .order_by("-score", "-hits", "-created_at")
                .values_list("id", flat=True)[:20]
            )
        else:
            # fallback to computed score when materialized score is disabled
            annotated = (
                Room.objects.filter(is_available=True)
                .annotate(
                    views_count=Count(
                        "roomstat",
                        filter=Q(roomstat__stat_type="view"),
                        distinct=False,
                    ),
                    contacts_count=Count(
                        "roomstat",
                        filter=Q(roomstat__stat_type__startswith="contact"),
                        distinct=False,
                    ),
                    favorites_count=Count("favorited_by", distinct=True),
                    reviews_count=Count("reviews", distinct=True),
                )
                .annotate(
                    score=ExpressionWrapper(
                        F("hits") * 3
                        + F("views_count") * 1
                        + F("contacts_count") * 8
                        + F("favorites_count") * 2
                        + F("reviews_count") * 2,
                        output_field=IntegerField(),
                    )
                )
                .filter(score__gte=POPULAR_SCORE_THRESHOLD)
                .order_by("-score", "-hits", "-created_at")
            )

            popular_ids = list(annotated.values_list("id", flat=True)[:20])

        cache.set(cache_key, popular_ids, 300)

    # ================= AJAX RESPONSE =================
    if is_ajax:

        html = render_to_string(
            "listings/_room_cards.html",
            {"rooms": page_obj.object_list, "popular_ids": popular_ids},
            request=request,
        )

        payload = {
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

        # Cache the JSON payload for a short time
        cache.set(cache_key, payload, 60)

        return JsonResponse(payload)

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
            "popular_ids": popular_ids,
        },
    )

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
    # Create view stat asynchronously so the detail page responds quickly.
    try:
        if settings.CELERY_BROKER_URL:
            # If Celery is configured prefer using a task (fast path). We import
            # lazily to avoid hard dependency during tests.
            try:
                from .tasks import create_room_view_stat_task

                create_room_view_stat_task.delay(room.id, request.user.id if request.user.is_authenticated else None)
            except Exception:
                # Fallback to background thread if Celery import fails
                import threading

                def _async_stat(rid, uid):
                    try:
                        RoomStat.objects.create(
                            room_id=rid,
                            user_id=uid,
                            stat_type="view",
                        )
                    except Exception:
                        logger.exception("Failed to write RoomStat in background")

                threading.Thread(target=_async_stat, args=(room.id, request.user.id if request.user.is_authenticated else None), daemon=True).start()
        else:
            # No Celery broker configured — do a lightweight background thread
            import threading

            def _async_stat(rid, uid):
                try:
                    RoomStat.objects.create(
                        room_id=rid,
                        user_id=uid,
                        stat_type="view",
                    )
                except Exception:
                    logger.exception("Failed to write RoomStat in background")

            threading.Thread(target=_async_stat, args=(room.id, request.user.id if request.user.is_authenticated else None), daemon=True).start()
    except Exception as e:
        logger.warning("Failed to schedule background RoomStat write: %s", str(e))

    # increment denormalized hit counter (fast, uses F() to avoid race)
    try:
        Room.objects.filter(pk=room.id).update(hits=F("hits") + 1)
    except DatabaseError as e:
        logger.warning(
            "Failed to increment hits for room %s: %s",
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

            user.is_active = True
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

        attempt_key = f"otp_attempts_{user.id}"
        attempts = cache.get(attempt_key, 0)

        if attempts >= 5:
            messages.error(request, "Too many attempts. Try again later.")
            return render(request, "listings/verify_account.html")

        if not otp_input:
            messages.error(request, "Enter OTP.")
            return render(request, "listings/verify_account.html")

        record = PhoneOTP.objects.filter(
            user=user,
            is_verified=False,
            created_at__gte=timezone.now() - timedelta(minutes=15)
        ).order_by("-created_at").first()

        if record and compare_digest(record.otp, otp_input):

            record.is_verified = True
            record.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.is_email_verified = True
            profile.is_phone_verified = True
            profile.save()

            user.is_active = True
            user.save()

            PhoneOTP.objects.filter(user=user).delete()

            try:
                send_welcome_email(user)
            except Exception:
                pass

            login(request, user)

            request.session.pop("pending_user_id", None)

            messages.success(
                request,
                "Account verified successfully 🎉"
            )

            cache.delete(attempt_key)

            state = get_user_state(user)
            return redirect(state["next_route"])

        messages.error(request, "Invalid or expired OTP")

        cache.set(attempt_key, attempts + 1, timeout=900)

    return render(request, "listings/verify_account.html")

@never_cache
def user_login(request):
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR")
    )
    login_key = f"login_attempts:{ip}"
    attempts = cache.get(login_key, 0)

    if attempts >= 10:
        messages.error(request, "Too many login attempts. Try again later.")
        return redirect("login")

    if request.method != "POST":
        return render(request, "listings/login.html")

    login_value = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""

    user_obj = (
        User.objects.filter(email__iexact=login_value).first()
        or User.objects.filter(username__iexact=login_value).first()
    )

    if not user_obj:
        cache.set(login_key, attempts + 1, timeout=900)
        messages.error(request, "Invalid credentials.")
        return redirect("login")
    

    user = authenticate(request, username=user_obj.username, password=password)

    if not user:
        cache.set(login_key, attempts + 1, timeout=900)
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    profile = user.profile

    # SAFETY ROLE FIX (prevents corruption)
    VALID_ROLES = ["driver", "tenant", "landlord"]

    if profile.role not in VALID_ROLES:
        logger.error(
            "invalid_role_detected",
            extra={
                "user_id": user.id,
                "role": profile.role,
            }
        )
        profile.role = "tenant"
        profile.save(update_fields=["role"])

    # OTP CHECK (ONLY ONE SYSTEM: verify_account)
    if not profile.is_phone_verified:
        request.session["pending_user_id"] = user.id
        logger.info(f"OTP BLOCK: user {user.id}")
        return redirect("verify_account")

    login(request, user)
    cache.delete(login_key)

    messages.success(
        request,
        f"Welcome back {get_display_name(user)} 👋"
    )

    # FORCE PASSWORD CHANGE
    if getattr(profile, "must_change_password", False):
        return redirect("change_password")

    if profile.role == "driver":
        return redirect("services:bakkie/driver_dashboard")

    state = get_user_state(user)
    return redirect(state["next_route"])

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


OTP_RESEND_SECONDS = 90


def resend_account_otp(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return JsonResponse({
            "level": "error",
            "message": "Your session has expired. Please restart the verification process."
        }, status=400)

    user = get_object_or_404(User, id=user_id)

    cache_key = f"otp_resend_{user.id}"

    if cache.get(cache_key):
        return JsonResponse({
            "level": "warning",
            "message": "Please wait before requesting another OTP.",
            "cooldown": OTP_RESEND_SECONDS
        }, status=429)

    # reset failed attempts safely
    cache.delete(f"otp_attempts_{user.id}")

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
        "level": "success",
        "message": "OTP sent successfully.",
        "cooldown": OTP_RESEND_SECONDS
    })


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


@login_required
@require_POST
def toggle_favorite(request, room_id):

    room = get_object_or_404(Room, id=room_id, is_available=True)

    # Role check (safe guard)
    profile = getattr(request.user, "profile", None)

    if not profile or profile.role != "tenant":
        messages.error(request, "Only tenants can save rooms.")
        return redirect("room_detail", pk=room.id)  # ✅ FIXED

    favorite, created = Favorite.objects.get_or_create(
        user=request.user,
        room=room
    )

    if created:
        messages.success(request, "❤️ Room added to saved listings.")
    else:
        favorite.delete()
        messages.info(request, "🗑️ Room removed from saved listings.")

    # IMPORTANT FIX HERE TOO
    return redirect("room_detail", pk=room.id)  # ✅ FIXED


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
def create_room(request):

    # ALWAYS ensure membership exists (SAFE)
    membership = get_or_create_membership(request.user)

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

    # rendering uses the canonical create_room template

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
@require_POST
@user_passes_test(is_landlord)
def delete_room(request, pk):

    room = get_object_or_404(
        Room,
        pk=pk,
        owner=request.user
    )

    room.delete()

    messages.success(
        request,
        "Listing deleted successfully."
    )

    return redirect("dashboard")


# IMAGES (upload/delete/manage)
@login_required
@user_passes_test(is_landlord)
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
                
                try:
                    Image.open(img).verify()
                    img.seek(0)

                except Exception:
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
@require_POST
@user_passes_test(is_landlord)
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
@user_passes_test(is_landlord)
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
@require_POST
def add_review(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    # ROLE CHECK (SYSTEM MESSAGE INSTEAD OF RAW ERROR)
    if hasattr(request.user, "profile") and request.user.profile.role != "tenant":
        messages.warning(request, "Only tenants are allowed to review rooms.")
        return redirect("room_detail", pk=room.id)

    rating = request.POST.get("rating")
    comment = request.POST.get("comment", "")

    if not rating:
        messages.error(request, "Please provide a rating before submitting your review.")
        return redirect("room_detail", pk=room.id)

    Review.objects.update_or_create(
        room=room,
        user=request.user,
        defaults={
            "rating": int(rating),
            "comment": comment
        }
    )

    messages.success(request, "Your review has been submitted successfully.")
    return redirect("room_detail", pk=room.id)


@login_required
def track_contact(request, room_id, method):
    """
    Direct external contact - Call opens the phone dialer, WhatsApp opens
    a chat with the landlord's real WhatsApp, Email opens a mailto:. This
    is the straightforward version: real contact info, no masking yet.

    In-app chat (conversation_thread) stays available as its own separate
    option alongside these - not a replacement for them. Masked calling
    via Twilio (call_landlord/voice_bridge_twiml, further down this file)
    is built and ready but not linked from the UI yet - switch "Call
    Landlord" over to call_landlord once real Twilio credentials are
    configured.
    """
    if method not in ["phone", "whatsapp", "email"]:
        return HttpResponseForbidden("Invalid contact method.")

    room = get_object_or_404(Room, id=room_id, is_available=True)

    if request.user.id == room.owner_id:
        messages.error(request, "You can't contact yourself about your own listing.")
        return redirect("room_detail", pk=room.id)

    cache_key = f"contact:{request.user.id}:{room.id}:{method}"

    if cache.get(cache_key):
        return redirect("room_detail", pk=room.id)

    cache.set(cache_key, True, 300)

    RoomStat.objects.get_or_create(
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
                "fallback_text": "If your phone didn't open the dialer automatically, tap the button below.",
            },
        )

    if method == "whatsapp":
        if not phone_digits or len(phone_digits) < 9:
            return redirect("room_detail", pk=room.id)

        whatsapp_url = f"https://wa.me/{phone_digits}"

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Opening WhatsApp…",
                "link": whatsapp_url,
                "button_text": "Open WhatsApp",
                "fallback_text": "If WhatsApp didn't open automatically, tap the button below.",
            },
        )

    if method == "email":
        if not landlord_email:
            return redirect("room_detail", pk=room.id)

        subject = quote(f"Rooms4You enquiry: {room.title}")
        body = quote(f"Hi, I'm interested in your room listing ({room.title}) in {room.location}.")
        mailto = f"mailto:{landlord_email}?subject={subject}&body={body}"

        try:
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
        except Exception:
            logger.warning("Failed to send new-inquiry notification email for room %s", room.id)

        return render(
            request,
            "listings/external_link.html",
            {
                "title": "Opening email…",
                "link": mailto,
                "button_text": "Open Email",
                "fallback_text": "If your email app didn't open automatically, tap the button below.",
            },
        )

    return redirect("room_detail", pk=room.id)


def call_landlord(request, room_id):
    """
    The real "Call Landlord" behavior - attempts a masked two-leg call
    via Twilio (like Uber/Airbnb: Twilio calls the tenant, and once they
    answer, bridges them to the landlord - neither side ever sees the
    other's real number, only Twilio's).

    Falls back to an in-app message (same as before) if Twilio Voice
    isn't configured yet (settings.TWILIO_VOICE_ENABLED is computed from
    whether real credentials are present - see rentaroom/settings.py) or
    if the tenant hasn't got a phone number on file to call. This means
    the feature is safe to ship now and will start actually placing
    calls the moment Twilio credentials are added, with no code change.
    """
    room = get_object_or_404(Room, id=room_id, is_available=True)

    if request.user.id == room.owner_id:
        messages.error(request, "You can't contact yourself about your own listing.")
        return redirect("room_detail", pk=room.id)

    cache_key = f"contact:{request.user.id}:{room.id}:phone"
    if cache.get(cache_key):
        return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)
    cache.set(cache_key, True, 300)

    RoomStat.objects.get_or_create(room=room, user=request.user, stat_type="contact_phone")
    Contact.objects.get_or_create(room=room, user=request.user)

    tenant_phone = ""
    if hasattr(request.user, "profile"):
        tenant_phone = (request.user.profile.phone_number or "").strip()
    landlord_phone = (room.contact_phone or "").strip()

    can_place_call = (
        settings.TWILIO_VOICE_ENABLED
        and TwilioClient is not None
        and tenant_phone
        and landlord_phone
    )

    if not can_place_call:
        Message.objects.create(
            room=room,
            sender=request.user,
            recipient=room.owner,
            body="Hi, I'd like to arrange a call about this room. What's a good time to reach you?",
        )
        if not settings.TWILIO_VOICE_ENABLED:
            messages.info(
                request,
                "In-app calling isn't switched on yet - we've sent the landlord "
                "a message asking them to arrange a call with you.",
            )
        elif not tenant_phone:
            messages.info(
                request,
                "Add a phone number to your profile so we can connect your call "
                "directly next time. For now, we've messaged the landlord for you.",
            )
        else:
            messages.info(
                request,
                "This landlord hasn't added a phone number yet - we've sent "
                "them a message instead.",
            )
        return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)

    try:
        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        callback_url = request.build_absolute_uri(
            reverse("voice_bridge_twiml", args=[room.id])
        )
        client.calls.create(
            to=tenant_phone,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=callback_url,
        )
        messages.success(
            request,
            "Calling you now - stay on the line and we'll connect you to the landlord.",
        )
    except Exception:
        logger.exception("Failed to place masked call for room %s", room.id)
        Message.objects.create(
            room=room,
            sender=request.user,
            recipient=room.owner,
            body="Hi, I tried to call about this room but the call didn't go through - could you reach out?",
        )
        messages.error(
            request,
            "We couldn't start the call right now. We've sent the landlord a message instead.",
        )

    return redirect("room_detail", pk=room.id)


@csrf_exempt
def voice_bridge_twiml(request, room_id):
    """
    Twilio requests this URL once the tenant answers the outbound call
    placed in call_landlord() above. Returns TwiML telling Twilio to
    dial the landlord's number and bridge the two calls - this is the
    step where masking actually happens: Twilio's number is what shows
    up as caller ID on the landlord's end, never the tenant's real one.

    Must stay unauthenticated and CSRF-exempt - Twilio's servers call
    this directly, not a logged-in browser session.
    """
    room = get_object_or_404(Room, id=room_id)
    landlord_phone = (room.contact_phone or "").strip()

    response = VoiceResponse()
    if landlord_phone:
        response.say("Connecting you to the landlord now.")
        response.dial(landlord_phone, caller_id=settings.TWILIO_PHONE_NUMBER)
    else:
        response.say("Sorry, we could not connect this call. Please try messaging instead.")

    return HttpResponse(str(response), content_type="text/xml")


    return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)


@login_required
def mark_success(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    RoomStat.objects.get_or_create(room=room, user=request.user, stat_type="success")
    messages.success(request, "Thanks for confirming!")
    return redirect("room_detail", pk=room.id)


# Password reset (rate limited)
class RateLimitedPasswordResetView(PasswordResetView):
    subject_template_name = "registration/password_reset_subject.txt"
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "registration/password_reset_email.html"

    COOLDOWN_SECONDS = 60
    MAX_PER_HOUR = 5

    def form_valid(self, form):
        request = self.request

        email = (form.cleaned_data.get("email") or "").strip().lower()

        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )

        base_key = f"pwreset:{ip}:{email}"

        if cache.get(base_key + ":cooldown"):
            messages.error(request, "Please wait before trying again.")
            return self.form_invalid(form)

        count = cache.get(base_key + ":hour", 0)

        if count >= self.MAX_PER_HOUR:
            messages.error(request, "Too many attempts. Try later.")
            return self.form_invalid(form)

        cache.set(base_key + ":cooldown", 1, timeout=self.COOLDOWN_SECONDS)
        cache.set(base_key + ":hour", count + 1, timeout=3600)

        return super().form_valid(form)
    

# Landlord analytics 
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
@require_POST
def report_room(request, pk):
    room = get_object_or_404(Room, pk=pk)

    reason = (request.POST.get("reason") or "").strip()
    detail = (request.POST.get("detail") or "").strip()

    # reason required
    if not reason:
        messages.error(
            request,
            "Please select a reason to report this listing."
        )
        return redirect("room_detail", pk=room.id)

    # if "other", require detail
    if reason.lower() == "other" and not detail:
        messages.error(
            request,
            "Please provide more detail for 'Other'."
        )
        return redirect("room_detail", pk=room.id)

    logger.info(
        f"ROOM REPORT | room={room.id} | "
        f"user={request.user.id if request.user.is_authenticated else 'anonymous'} | "
        f"reason={reason} | detail={detail}"
    )

    messages.success(
        request,
        "Thanks! Your report was received ✅ We’ll review this listing."
    )

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
            otp=otp,
            created_at__gte=timezone.now() - timedelta(minutes=15)
        ).last()
        
        if record and compare_digest(record.otp, otp):

            request.user.email = pending_email
            request.user.save()

            profile = request.user.profile
            profile.is_email_verified = True
            profile.save()

            PhoneOTP.objects.filter(
                user=request.user,
                created_at__gte=timezone.now() - timedelta(minutes=15)
            ).delete()

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
@require_POST
def request_upgrade(request):
    membership = get_or_create_membership(request.user)

    membership.status = "pending"
    membership.save(update_fields=["status"])

    messages.success(request, "Payment request submitted.")
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
            otp=otp,
            created_at__gte=timezone.now() - timedelta(minutes=15)
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
    """
    Kept for backward compatibility with any old links/bookmarks pointing
    here - immediately hands off to the real two-way conversation view.
    New code should link straight to conversation_thread.
    """
    room = get_object_or_404(Room, id=room_id)

    if request.user.id == room.owner_id:
        messages.error(request, "Open a specific conversation to reply to a tenant.")
        return redirect("inbox")

    if request.method == "POST":
        return conversation_thread(request, room_id=room.id, other_user_id=room.owner_id)

    return redirect("conversation_thread", room_id=room.id, other_user_id=room.owner_id)


@login_required
def conversation_thread(request, room_id, other_user_id):
    """
    A single message thread between two specific users about one room.
    Works identically for both roles:
      - Tenant's view: other_user_id is always the room's owner.
      - Landlord's view: other_user_id is whichever tenant they're
        replying to (a room can have many separate tenant conversations).

    This - not a new model - is what actually fixes "messaging should
    work between landlord and tenant": the old send_message() only
    allowed tenant-to-landlord and explicitly forbade the room owner
    from using it, and inbox() was landlord-only, so a landlord had no
    way to reply and a tenant had no way to see a reply even if one
    existed.
    """
    room = get_object_or_404(Room, id=room_id)
    other_user = get_object_or_404(User, id=other_user_id)

    is_owner = request.user.id == room.owner_id

    if is_owner:
        if other_user.id == room.owner_id:
            return HttpResponseForbidden("Invalid conversation.")
    else:
        # A tenant can only have a thread with this room's owner - not
        # with some arbitrary other user.
        if other_user.id != room.owner_id:
            return HttpResponseForbidden("Invalid conversation.")
        if request.user.id == room.owner_id:
            return HttpResponseForbidden()

    if request.method == "POST":
        body = strip_tags((request.POST.get("body") or "").strip())

        if not body:
            messages.error(request, "Message cannot be empty.")
        elif len(body) > 2000:
            messages.error(request, "Message too long.")
        else:
            recent_count = Message.objects.filter(
                sender=request.user,
                created_at__gte=timezone.now() - timedelta(minutes=1)
            ).count()

            if recent_count >= 5:
                messages.error(request, "Too many messages sent. Please wait a minute.")
            else:
                Message.objects.create(
                    room=room,
                    sender=request.user,
                    recipient=other_user,
                    body=body,
                )
                # Contact is always attributed to whichever party isn't
                # the room owner (i.e. the tenant side of the conversation).
                Contact.objects.get_or_create(
                    room=room,
                    user=request.user if not is_owner else other_user,
                )

        return redirect("conversation_thread", room_id=room.id, other_user_id=other_user.id)

    thread_qs = (
        Message.objects.filter(room=room)
        .filter(
            (Q(sender=request.user) & Q(recipient=other_user))
            | (Q(sender=other_user) & Q(recipient=request.user))
        )
        .select_related("sender", "recipient")
        .order_by("created_at")
    )

    # Mark anything sent TO the current user as read now that they've
    # opened the thread.
    Message.objects.filter(
        room=room, sender=other_user, recipient=request.user, is_read=False
    ).update(is_read=True)

    return render(request, "listings/conversation_thread.html", {
        "room": room,
        "other_user": other_user,
        "is_owner": is_owner,
        "thread": thread_qs,
    })


@login_required
def inbox(request):
    """
    Works for both tenants and landlords now (previously landlord-only).
    Groups every message the user has sent or received into one row per
    (room, other person), showing the latest message and an unread count -
    a normal "conversation list" rather than a flat message log.
    """
    msgs = (
        Message.objects.filter(Q(sender=request.user) | Q(recipient=request.user))
        .select_related("room", "sender", "recipient")
        .order_by("-created_at")
    )

    conversations = {}
    for m in msgs:
        other = m.recipient if m.sender_id == request.user.id else m.sender
        key = (m.room_id, other.id)

        if key not in conversations:
            conversations[key] = {
                "room": m.room,
                "other_user": other,
                "last_message": m,
                "unread_count": 0,
            }

        if m.recipient_id == request.user.id and not m.is_read:
            conversations[key]["unread_count"] += 1

    conversation_list = sorted(
        conversations.values(),
        key=lambda c: c["last_message"].created_at,
        reverse=True,
    )

    return render(request, "listings/inbox.html", {
        "conversations": conversation_list,
    })


@login_required
def delete_account(request):
    if request.method == "POST":
        user = request.user

        with transaction.atomic():
            logout(request)
            user.is_active = False
            user.save(update_fields=["is_active"])

        messages.success(request, "Your account has been deactivated.")
        return redirect("room_list")

    return render(request, "listings/delete_account.html")


def offline_page(request):
    """Served by the service worker when a navigation request fails
    while offline and nothing cached matches it."""
    return render(request, "listings/offline.html")


def service_worker_view(request):
    """
    Serves the service worker at the site ROOT (e.g. rooms4you.co.za/service-worker.js)
    rather than from /static/js/. A service worker's default scope is
    limited to the directory it's served from - if this lived at
    /static/js/service-worker.js it would only be able to control
    /static/js/*, not the actual site pages. Serving it via a root-level
    view sidesteps needing a Service-Worker-Allowed header on WhiteNoise.
    """
    sw_path = os.path.join(settings.BASE_DIR, "static", "js", "service-worker.js")
    with open(sw_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HttpResponse(content, content_type="application/javascript")