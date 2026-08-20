import logging
from difflib import get_close_matches

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import (
    Avg,
    Case,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Prefetch,
    Q,
    When,
)
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from accounts.utils import require_active_membership
from utils.email import send_template_email

from ..forms import RoomForm
from ..models import Favorite, Room, RoomImage, RoomStat
from .helpers import get_or_create_membership, is_landlord

POPULAR_SCORE_THRESHOLD = getattr(settings, "POPULAR_SCORE_THRESHOLD", 100)

logger = logging.getLogger(__name__)


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

    # ================= FULL-PAGE CACHE (non-AJAX) =================
    # This is the page every first-time visitor, every social media
    # click, and every single Google crawl actually hits - previously
    # NEVER cached, unlike the AJAX filter-refresh path above. We only
    # cache the matching room IDs (not rendered HTML - the navbar has
    # a CSRF-protected logout form, so caching full HTML would risk
    # serving one session's stale CSRF token to a different session).
    # Reconstructing a real queryset from cached IDs means Paginator
    # keeps working exactly as before, no special-casing needed.
    full_page_cache_key = f"room_list_ids:{cache_key}"
    cached_ids_payload = None if is_ajax else cache.get(full_page_cache_key)

    if cached_ids_payload is not None:
        cached_ids = cached_ids_payload["ids"]
        suggested_location = cached_ids_payload["suggested_location"]
        searched_location = cached_ids_payload["searched_location"]

        preserved_order = Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)]
        )
        rooms = (
            Room.objects.filter(id__in=cached_ids)
            .select_related("owner__profile")
            .only(
                "id", "title", "price", "location", "latitude", "longitude",
                "score", "hits", "created_at", "owner_id",
                "available_units", "total_units", "availability_status",
                "available_from",
            )
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=RoomImage.objects.only("id", "image", "room_id")
                )
            )
            .annotate(avg_rating_value=Avg("reviews__rating"))
            .order_by(preserved_order)
        )

        page_number = request.GET.get("page") or 1
        paginator = Paginator(rooms, 8)
        page_obj = paginator.get_page(page_number)

        map_rooms = list(
            page_obj.object_list.values("id", "title", "price", "latitude", "longitude")
        )

        cache_key_popular = f"popular_ids_v1:{'mat' if getattr(settings, 'USE_MATERIALIZED_SCORE', True) else 'calc'}:{POPULAR_SCORE_THRESHOLD}"
        popular_ids = cache.get(cache_key_popular)
        if popular_ids is None:
            popular_ids = list(
                Room.objects.filter(is_available=True, score__gte=POPULAR_SCORE_THRESHOLD)
                .order_by("-score", "-hits", "-created_at")
                .values_list("id", flat=True)[:20]
            )
            cache.set(cache_key_popular, popular_ids, 300)

        sort_selected = {
            "best": sort == "",
            "new": sort == "new",
            "price_low": sort == "price_low",
            "price_high": sort == "price_high",
        }
        show_location_suggestion = (
            bool(suggested_location)
            and bool(searched_location)
            and suggested_location.strip().lower() != searched_location.strip().lower()
        )

        return render(
            request,
            "listings/room_list.html",
            {
                "map_rooms": map_rooms,
                "rooms": page_obj.object_list,
                "page_obj": page_obj,
                "paginator": paginator,
                "values": {
                    "q": q, "location": location, "type": room_type,
                    "sort": sort, "min_price": min_price, "max_price": max_price,
                },
                "sort_selected": sort_selected,
                "suggested_location": suggested_location,
                "searched_location": searched_location,
                "show_location_suggestion": show_location_suggestion,
                "popular_ids": popular_ids,
            },
        )
    # ================= END FULL-PAGE CACHE fast path =================

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

    # Populate the full-page cache for next time - store the matching
    # room IDs (not rendered HTML, see the fast-path comment above for
    # why). Short TTL since new listings/price changes should show up
    # reasonably quickly.
    if not is_ajax:
        cache.set(
            full_page_cache_key,
            {
                "ids": list(paginator.object_list.values_list("id", flat=True)),
                "suggested_location": suggested_location,
                "searched_location": searched_location,
            },
            60,
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
                from listings.tasks import create_room_view_stat_task

                create_room_view_stat_task.delay(room.id, request.user.id if request.user.is_authenticated else None)
            except (ImportError, ConnectionError, TimeoutError, OSError):
                # Fallback to background thread if Celery import fails
                import threading

                def _async_stat(rid, uid):
                    try:
                        RoomStat.objects.create(
                            room_id=rid,
                            user_id=uid,
                            stat_type="view",
                        )
                    except DatabaseError:
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
                except DatabaseError:
                    logger.exception("Failed to write RoomStat in background")

            threading.Thread(target=_async_stat, args=(room.id, request.user.id if request.user.is_authenticated else None), daemon=True).start()
    except (ConnectionError, DatabaseError, RuntimeError, TimeoutError, OSError) as e:
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

        # Clear room list cache after room creation
        cache_keys_to_delete = [
            f"room_list:{request.user.id}*",
            "room_list_ids:*",
        ]
        for pattern in cache_keys_to_delete:
            try:
                cache.delete_pattern(pattern)
            except (AttributeError, TypeError):
                # delete_pattern not available on all cache backends; use delete for individual keys
                pass

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

    if request.method == "POST" and form.is_valid():

            try:

                with transaction.atomic():

                    updated_room = form.save(commit=False)
                    updated_room.owner = request.user
                    updated_room.full_clean()
                    updated_room.save()

                # Clear room list cache after room edit
                cache_keys_to_delete = [
                    f"room_list:{request.user.id}*",
                    "room_list_ids:*",
                ]
                for pattern in cache_keys_to_delete:
                    try:
                        cache.delete_pattern(pattern)
                    except (AttributeError, TypeError):
                        pass

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

    try:
        room.delete()
    except ProtectedError:
        messages.error(
            request,
            "This listing can't be deleted because it has placement or "
            "invoice history attached (a tenant was matched through it). "
            "Mark it as occupied/unavailable instead to keep it out of "
            "search results."
        )
        return redirect("dashboard")

    messages.success(
        request,
        "Listing deleted successfully."
    )

    return redirect("dashboard")


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

