from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Room, Review, Contact, RoomStat, RoomImage, Profile
from django.contrib.auth import login, logout, authenticate
from .forms import UserRegisterForm, RoomForm
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from urllib.parse import quote
from django.contrib import messages
import re


def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"


def home(request):
    """
    Home page:
    - Shows counters
    - Provides search form that redirects to /rooms/ with query params
    """
    # Read filters from GET (home page search)
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    # If user searched on home, redirect to room_list with params
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
        "values": {
            "q": q,
            "location": location,
            "type": room_type,
        },
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
        "contacts_made": RoomStat.objects.filter(
            stat_type__startswith="contact"
        ).count(),
        "success_matches": RoomStat.objects.filter(stat_type="success").count(),
    }
    return render(request, "listings/services.html", context)


def contact(request):
    return render(request, "listings/contact.html")


def room_list(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()
    room_type = (request.GET.get("type") or "").strip()

    rooms_qs = Room.objects.filter(is_available=True)

    # Search logic
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
            review_count=Count("reviews"),
            contact_count=Count(
                "roomstat", filter=Q(roomstat__stat_type__startswith="contact")
            ),
        )
        .select_related("owner__profile")
        .prefetch_related("images")
        .order_by("-created_at")
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
    return render(request, "listings/room_detail.html", {"room": room})


def register(request):
    form = UserRegisterForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        login(request, user)
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
            return redirect("room_list")
        messages.error(request, "Invalid username or password.")
    return render(request, "listings/login.html")


def user_logout(request):
    logout(request)
    return redirect("room_list")


@login_required
@user_passes_test(is_landlord)
def dashboard(request):
    rooms = Room.objects.filter(owner=request.user)
    image_count = RoomImage.objects.filter(room__owner=request.user).count()
    contact_count = RoomStat.objects.filter(
        room__owner=request.user, stat_type__startswith="contact"
    ).count()
    return render(
        request,
        "listings/dashboard.html",
        {
            "rooms": rooms,
            "image_count": image_count,
            "contact_count": contact_count,
        },
    )


@login_required
@user_passes_test(is_landlord)
def add_room(request):
    return redirect("create_room")


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
def edit_room(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)
    form = RoomForm(request.POST or None, instance=room, user=request.user)
    if form.is_valid():
        form.save()
        return redirect("dashboard")
    return render(request, "listings/edit_room.html", {"form": form})


@login_required
def delete_room(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)
    if request.method == "POST":
        room.delete()
        return redirect("dashboard")
    return render(request, "listings/delete_room.html", {"room": room})


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

    # save stat
    RoomStat.objects.create(
        room=room,
        user=request.user,
        stat_type=f"contact_{method}",
    )

    # allow review after at least one contact attempt
    Contact.objects.get_or_create(room=room, user=request.user)

    phone_raw = (room.contact_phone or "").strip()
    whatsapp_raw = (room.contact_whatsapp or "").strip() or phone_raw

    # digits only for wa.me
    phone_digits = re.sub(r"\D", "", whatsapp_raw)

    # prefer explicit contact_email, fallback to owner email
    landlord_email = (room.contact_email or room.owner.email or "").strip()

    if method == "phone":
        tel = phone_raw.replace(" ", "")
        if not tel:
            return redirect("room_detail", pk=room.id)
        return redirect(f"tel:{tel}")

    if method == "whatsapp":
        if not phone_digits:
            return redirect("room_detail", pk=room.id)
        return redirect(f"https://wa.me/{phone_digits}")

    if method == "email":
        if not landlord_email:
            return redirect("room_detail", pk=room.id)
        subject = quote(f"RentARoom enquiry: {room.title}")
        body = quote(
            f"Hi, I’m interested in your room listing ({room.title}) in {room.location}."
        )
        return redirect(f"mailto:{landlord_email}?subject={subject}&body={body}")

    return redirect("room_detail", pk=room.id)


@login_required
def mark_success(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    RoomStat.objects.create(room=room, user=request.user, stat_type="success")
    messages.success(request, "Thanks for confirming!")
    return redirect("room_detail", pk=room.id)


@login_required
def edit_room_images(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)

    if request.method == "POST":
        for img in request.FILES.getlist("images")[:10]:
            RoomImage.objects.create(room=room, image=img)

        if "delete" in request.POST:
            RoomImage.objects.filter(
                id__in=request.POST.getlist("delete"), room=room
            ).delete()

        return redirect("edit_room_images", pk=pk)

    return render(request, "listings/edit_room_images.html", {"room": room})
