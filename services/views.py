import json
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import BadHeaderError, send_mail
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST

from .forms import BakkieDriverForm, GuardianSessionForm, MoveBookingForm
from .models import (
    BakkieDriver,
    GuardianLocationPing,
    GuardianSession,
    MoveBooking,
    PanicAlert,
    ServiceAnalyticsEvent,
)


# GUARDIAN HOME
@login_required
def guardian_home(request):

    active_session = GuardianSession.objects.filter(
        user=request.user,
        is_active=True
    ).first()

    form = GuardianSessionForm()

    return render(request, "services/guardian/home.html", {
        "active_session": active_session,
        "form": form
    })


# START SESSION
@login_required
def start_guardian_session(request):

    if request.method == "POST":

        form = GuardianSessionForm(request.POST)

        if form.is_valid():

            GuardianSession.objects.filter(
                user=request.user,
                is_active=True
            ).update(
                is_active=False,
                status="ended"
            )

            session = form.save(commit=False)
            session.user = request.user
            session.is_active = True
            session.status = "active"
            session.started_at = timezone.now()
            session.save()

            ServiceAnalyticsEvent.objects.create(
                event_type="guardian_started",
                user=request.user,
            )

            messages.success(
                request,
                "Guardian protection activated."
            )

            return redirect("services:guardian_home")

    else:

        form = GuardianSessionForm()

    return render(
        request,
        "services/guardian/start_session.html",
        {
            "form": form
        }
    )


# SAVE GPS LOCATION (AJAX)
@login_required
@require_POST
def save_location_ping(request, session_id):

    session = get_object_or_404(
        GuardianSession,
        id=session_id,
        user=request.user,
        is_active=True
    )

    data = json.loads(request.body)

    lat = data.get("latitude")
    lng = data.get("longitude")

    if lat is None or lng is None:
        return JsonResponse({"success": False}, status=400)

    GuardianLocationPing.objects.create(
        session=session,
        latitude=lat,
        longitude=lng
    )

    session.latest_latitude = lat
    session.latest_longitude = lng
    session.save(update_fields=["latest_latitude", "latest_longitude"])

    return JsonResponse({"success": True})


# PANIC BUTTO
@login_required
@require_POST
def trigger_panic_alert(request, session_id):

    session = get_object_or_404(
        GuardianSession,
        id=session_id,
        user=request.user,
        is_active=True
    )

    data = json.loads(request.body)

    lat = data.get("latitude")
    lng = data.get("longitude")

    alert = PanicAlert.objects.create(
        session=session,
        latitude=lat,
        longitude=lng
    )

    session.status = "panic"
    session.save(update_fields=["status"])

    ServiceAnalyticsEvent.objects.create(
        event_type="panic_triggered",
        user=request.user,
    )

    return JsonResponse({
        "success": True,
        "alert_id": alert.id
    })



# END SESSION
@login_required
def end_guardian_session(request, session_id):

    session = get_object_or_404(
        GuardianSession,
        id=session_id,
        user=request.user,
        is_active=True
    )

    session.is_active = False
    session.status = "ended"
    session.ended_at = timezone.now()
    session.save()

    messages.success(request, "Session ended.")

    return redirect("services:guardian_home")



# BAKKIE HOME
@login_required
def bakkie_home(request):

    drivers = BakkieDriver.objects.filter(
        is_verified=True
    ).order_by("-created_at")

    return render(request, "services/bakkie/home.html", {
        "drivers": drivers
    })

# REGISTER DRIVER
def register_bakkie_driver(request):

    if request.method == "POST":

        form = BakkieDriverForm(request.POST, request.FILES)

        if form.is_valid():

            phone = form.cleaned_data["phone_number"].replace(" ", "")
            email = form.cleaned_data["email"].lower().strip()

            phone = phone.removeprefix("0")

            phone = f"+27{phone}"
            username = email

            if User.objects.filter(username=username).exists():
                messages.warning(request, "A driver with this email already exists.")
                return redirect("login")

            temp_password = get_random_string(10)

            with transaction.atomic():

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=temp_password,
                    is_active=True  # allow login but restrict access via verification
                )

                driver = form.save(commit=False)

                driver.user = user
                driver.phone_number = phone
                driver.email = email

                driver.is_verified = False

                driver.terms_accepted = True
                driver.terms_accepted_at = timezone.now()
                driver.privacy_accepted_at = timezone.now()

                driver.save()

                profile = user.profile
                profile.role = "driver"
                profile.phone_number = phone
                profile.is_phone_verified = True
                profile.is_email_verified = True

                # SAFE CHECK (prevents crash if field exists or not)
                if hasattr(profile, "must_change_password"):
                    profile.must_change_password = True

                profile.save()

            # EMAIL
            try:
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
                send_mail(
                    "Your Rooms4You Driver Account",
                    (
                        f"Welcome to Bakkie4You.\n\n"
                        f"Login Email: {email}\n"
                        f"Temporary Password: {temp_password}\n\n"
                        f"Your application is under review."
                    ),
                    from_email,
                    [email],
                    fail_silently=False,
                )

            except (BadHeaderError, SMTPException) as e:
                print("EMAIL ERROR:", e)
                messages.warning(
                    request,
                    f"Driver created. Temp password: {temp_password}"
                )
                return redirect("login")

            messages.success(
                request,
                "Driver registered successfully. Awaiting approval."
            )

            return redirect("login")

        else:
            print("FORM ERRORS:", form.errors)
            messages.error(request, "Please fix the errors below.")

    else:
        form = BakkieDriverForm()

    return render(request, "services/bakkie/register.html", {
        "form": form
    })


@login_required
def driver_dashboard(request):

    driver = BakkieDriver.objects.filter(user=request.user).first()

    if not driver:
        messages.error(request, "Driver profile not found.")
        return redirect("services:bakkie_home")

    if driver.application_status == "pending":
        messages.warning(
            request,
            "Your driver application is still under review."
        )
        return redirect("services:bakkie_home")

    if driver.application_status == "rejected":
        messages.error(
            request,
            "Your application was not approved."
        )
        return redirect("services:bakkie_home")
    
    bookings = MoveBooking.objects.filter(
        driver=driver
    )

    context = {
        "driver": driver,
        "total_bookings": bookings.count(),
        "completed_jobs": bookings.filter(
            status="completed"
        ).count(),
        "pending_jobs": bookings.filter(
            status="pending"
        ).count(),
    }

    return render(request, "services/driver_dashboard.html", context
    )

    
@login_required
@require_POST
def toggle_driver_availability(request):

    driver = get_object_or_404(
        BakkieDriver,
        user=request.user
    )

    driver.is_online = not driver.is_online

    if driver.is_online:
        driver.availability_status = "available"
    else:
        driver.availability_status = "offline"

    driver.last_seen = timezone.now()

    driver.save(
        update_fields=[
            "is_online",
            "availability_status",
            "last_seen",
        ]
    )

    return JsonResponse({
        "success": True,
        "available": driver.is_online,
        "status": driver.availability_status,
    })


def driver_profile(request, driver_id):

    driver = get_object_or_404(
        BakkieDriver,
        id=driver_id,
        is_verified=True
    )

    # Record analytics; if the viewer is anonymous, store `user=None`.
    ServiceAnalyticsEvent.objects.create(
        event_type="driver_view",
        user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        metadata={
            "driver": driver.id
        }
    )

    return render(request, "services/bakkie/driver_profile.html", {
        "driver": driver
    })

@login_required
def create_booking(request, driver_id):

    driver = get_object_or_404(
        BakkieDriver,
        id=driver_id,
        is_verified=True
    )

    if request.method == "POST":

        form = MoveBookingForm(request.POST)

        if form.is_valid():

            booking = form.save(commit=False)

            booking.tenant = request.user
            booking.driver = driver

            booking.save()

            ServiceAnalyticsEvent.objects.create(
                event_type="booking_created",
                user=request.user,
                metadata={
                    "driver": driver.id
                }
            )

            messages.success(
                request,
                "Booking request submitted."
            )

            return redirect(
                "services:my_bookings"
            )

    else:

        form = MoveBookingForm()

    return render(
        request,
        "services/bakkie/booking_form.html",
        {
            "form": form,
            "driver": driver,
        }
    )

@login_required
def my_bookings(request):

    bookings = MoveBooking.objects.filter(
        tenant=request.user
    ).select_related(
        "driver"
    ).order_by("-created_at")

    return render(
        request,
        "services/bakkie/my_bookings.html",
        {
            "bookings": bookings
        }
    )

@login_required
def driver_bookings(request):

    driver = get_object_or_404(
        BakkieDriver,
        user=request.user
    )

    bookings = MoveBooking.objects.filter(
        driver=driver
    ).order_by("-created_at")

    return render(
        request,
        "services/bakkie/driver_bookings.html",
        {
            "driver": driver,
            "bookings": bookings,
        }
    )

def driver_terms(request):
    return render(
        request,
        "services/bakkie/driver_terms.html"
    )