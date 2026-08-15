from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from .models import GuestHouse, GuestHouseImage, Booking
from .forms import GuestHouseForm, BookingForm
from .availability import get_unavailable_ranges, confirm_booking


def guesthouse_list(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()

    guesthouses = GuestHouse.objects.filter(is_active=True).prefetch_related(
        Prefetch("images", queryset=GuestHouseImage.objects.only("id", "image", "guesthouse_id"))
    ).order_by("-created_at")

    if q:
        guesthouses = guesthouses.filter(name__icontains=q)
    if location:
        guesthouses = guesthouses.filter(location__icontains=location)

    paginator = Paginator(guesthouses, 12)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(request, "stays/guesthouse_list.html", {
        "page_obj": page_obj,
        "q": q,
        "location": location,
    })


def guesthouse_detail(request, pk):
    guesthouse = get_object_or_404(
        GuestHouse.objects.select_related("host").prefetch_related(
            Prefetch("images", queryset=GuestHouseImage.objects.only("id", "image", "guesthouse_id"))
        ),
        pk=pk, is_active=True,
    )

    unavailable_ranges = get_unavailable_ranges(guesthouse) 

    form = None
    if request.user.is_authenticated and request.user != guesthouse.host:
        form = BookingForm(guesthouse=guesthouse)

    return render(request, "stays/guesthouse_detail.html", {
        "guesthouse": guesthouse,
        "unavailable_ranges": unavailable_ranges,
        "form": form,
        "is_host": request.user == guesthouse.host,
    })


@login_required
def create_guesthouse(request):
    if request.method == "POST":
        form = GuestHouseForm(request.POST)
        if form.is_valid():
            guesthouse = form.save(commit=False)
            guesthouse.host = request.user
            guesthouse.save()
            messages.success(request, "Your listing is live. Add some photos to help guests picture the place.")
            return redirect("stays:upload_guesthouse_images", pk=guesthouse.id)
    else:
        form = GuestHouseForm()

    return render(request, "stays/create_guesthouse.html", {"form": form})


@login_required
def edit_guesthouse(request, pk):
    guesthouse = get_object_or_404(GuestHouse, pk=pk, host=request.user)

    if request.method == "POST":
        form = GuestHouseForm(request.POST, instance=guesthouse)
        if form.is_valid():
            form.save()
            messages.success(request, "Listing updated.")
            return redirect("stays:my_guesthouses")
    else:
        form = GuestHouseForm(instance=guesthouse)

    return render(request, "stays/edit_guesthouse.html", {"form": form, "guesthouse": guesthouse})


@login_required
def my_guesthouses(request):
    guesthouses = GuestHouse.objects.filter(host=request.user).prefetch_related(
        Prefetch("images", queryset=GuestHouseImage.objects.only("id", "image", "guesthouse_id"))
    ).order_by("-created_at")

    pending_count = Booking.objects.filter(
        guesthouse__host=request.user, status=Booking.STATUS_REQUESTED
    ).count()

    return render(request, "stays/my_guesthouses.html", {
        "guesthouses": guesthouses,
        "pending_count": pending_count,
    })


@login_required
def upload_guesthouse_images(request, pk):
    guesthouse = get_object_or_404(GuestHouse, pk=pk, host=request.user)

    if request.method == "POST":
        uploads = request.FILES.getlist("images")
        if not uploads:
            messages.error(request, "Please select at least one image.")
            return redirect("stays:upload_guesthouse_images", pk=guesthouse.id)

        existing_count = guesthouse.images.count()
        remaining = max(0, 15 - existing_count)

        uploaded_count = 0
        for f in uploads[:remaining]:
            GuestHouseImage.objects.create(guesthouse=guesthouse, image=f)
            uploaded_count += 1

        if uploaded_count:
            messages.success(request, f"{uploaded_count} image(s) uploaded.")
        if len(uploads) > remaining:
            messages.warning(request, f"Only {remaining} image(s) were added (max 15 per listing).")

        return redirect("stays:my_guesthouses")

    return render(request, "stays/upload_guesthouse_images.html", {"guesthouse": guesthouse})


@login_required
def request_booking(request, pk):
    guesthouse = get_object_or_404(GuestHouse, pk=pk, is_active=True)

    if request.user == guesthouse.host:
        messages.error(request, "You can't book your own listing.")
        return redirect("stays:guesthouse_detail", pk=pk)

    if request.method != "POST":
        return redirect("stays:guesthouse_detail", pk=pk)

    form = BookingForm(request.POST, guesthouse=guesthouse)
    if form.is_valid():
        booking = form.save(commit=False)
        booking.guesthouse = guesthouse
        booking.guest = request.user
        booking.save()
        messages.success(
            request,
            "Your request has been sent to the host. You'll be notified once they respond."
        )
        return redirect("stays:my_bookings")

    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, error)
    return redirect("stays:guesthouse_detail", pk=pk)


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(guest=request.user).select_related(
        "guesthouse"
    ).order_by("-created_at")

    return render(request, "stays/my_bookings.html", {"bookings": bookings})


@login_required
def host_bookings(request):
    bookings = Booking.objects.filter(guesthouse__host=request.user).select_related(
        "guesthouse", "guest"
    ).order_by("-created_at")

    return render(request, "stays/host_bookings.html", {"bookings": bookings})


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("guesthouse", "guest", "guesthouse__host"),
        pk=pk,
    )

    if request.user != booking.guest and request.user != booking.guesthouse.host:
        messages.error(request, "You don't have access to that booking.")
        return redirect("stays:guesthouse_list")

    is_host = request.user == booking.guesthouse.host

    return render(request, "stays/booking_detail.html", {
        "booking": booking,
        "is_host": is_host,
        "show_contact": booking.status == Booking.STATUS_CONFIRMED,
    })


@login_required
def accept_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk, guesthouse__host=request.user)

    if request.method != "POST":
        return redirect("stays:booking_detail", pk=pk)

    success, error = confirm_booking(booking)
    if success:
        messages.success(request, "Booking confirmed. Contact details are now visible to both of you.")
    else:
        messages.error(request, error)

    return redirect("stays:booking_detail", pk=pk)


@login_required
def decline_booking(request, pk):
    booking = get_object_or_404(
        Booking, pk=pk, guesthouse__host=request.user, status=Booking.STATUS_REQUESTED
    )

    if request.method != "POST":
        return redirect("stays:booking_detail", pk=pk)

    booking.status = Booking.STATUS_DECLINED
    booking.decline_reason = request.POST.get("reason", "").strip()
    booking.decided_at = timezone.now()
    booking.save(update_fields=["status", "decline_reason", "decided_at"])

    messages.success(request, "Request declined.")
    return redirect("stays:host_bookings")


@login_required
def cancel_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)

    if request.user != booking.guest and request.user != booking.guesthouse.host:
        messages.error(request, "You don't have access to that booking.")
        return redirect("stays:guesthouse_list")

    if request.method != "POST":
        return redirect("stays:booking_detail", pk=pk)

    if booking.status not in (Booking.STATUS_REQUESTED, Booking.STATUS_CONFIRMED):
        messages.error(request, "This booking can no longer be cancelled.")
        return redirect("stays:booking_detail", pk=pk)

    booking.status = Booking.STATUS_CANCELLED
    booking.save(update_fields=["status"])

    messages.success(request, "Booking cancelled.")
    if request.user == booking.guest:
        return redirect("stays:my_bookings")
    return redirect("stays:host_bookings")
