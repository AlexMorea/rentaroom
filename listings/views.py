from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Room, Review, Contact, RoomStat, RoomImage, Profile
from django.contrib.auth import login, logout, authenticate
from .forms import UserRegisterForm, RoomForm
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.contrib import messages


def is_landlord(user):
    return hasattr(user, "profile") and user.profile.role == "landlord"


def home(request):
    context = {
        "room_count": Room.objects.count(),
        "contact_count": Contact.objects.count(),
        "review_count": Review.objects.count(),
        "landlord_count": Profile.objects.filter(role="landlord").count(),
    }
    return render(request, "listings/home.html", context)


def room_list(request):
    rooms = (
        Room.objects.filter(is_available=True)
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews"),
            contact_count=Count(
                "roomstat", filter=Q(roomstat__stat_type__startswith="contact")
            ),
        )
        .select_related("owner__profile")
        .prefetch_related("images")
    )
    return render(request, "listings/room_list.html", {"rooms": rooms})


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
            username=request.POST["username"], password=request.POST["password"]
        )
        if user:
            login(request, user)
            return redirect("room_list")
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
    form = RoomForm(request.POST or None, request.FILES or None)
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
    form = RoomForm(request.POST or None, instance=room)
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
        rating=request.POST["rating"],
        comment=request.POST.get("comment", ""),
    )
    return redirect("room_detail", pk=room.id)


@login_required
def track_contact(request, room_id, method):
    room = get_object_or_404(Room, id=room_id)
    RoomStat.objects.create(room=room, user=request.user, stat_type=f"contact_{method}")
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
