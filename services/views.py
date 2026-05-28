import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User
from django.core.mail import send_mail
from .forms import BakkieDriverForm
from django.db import transaction
from django.contrib.auth import get_user_model



from .models import (
    GuardianSession,
    GuardianLocationPing,
    PanicAlert,
    BakkieDriver
)

from .forms import GuardianSessionForm



# GUARDIAN HOME
@login_required
def guardian_home(request):

    active_session = GuardianSession.objects.filter(
        user=request.user,
        is_active=True
    ).first()

    form = GuardianSessionForm()

    return render(request, "services/guardian_home.html", {
        "active_session": active_session,
        "form": form
    })


# START SESSION
@login_required
def start_guardian_session(request):

    if request.method == "POST":

        form = GuardianSessionForm(request.POST)

        if form.is_valid():

            # close any existing session
            GuardianSession.objects.filter(
                user=request.user,
                is_active=True
            ).update(is_active=False, status="ended")

            session = form.save(commit=False)
            session.user = request.user
            session.is_active = True
            session.status = "active"
            session.started_at = timezone.now()
            session.save()

            messages.success(request, "Guardian session started.")

            return redirect("services:guardian_home")

    return redirect("services:guardian_home")



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

    return render(request, "services/bakkie_home.html", {
        "drivers": drivers
    })

# REGISTER DRIVER
def register_bakkie_driver(request):

    if request.method == "POST":

        form = BakkieDriverForm(request.POST, request.FILES)

        if form.is_valid():

            phone = form.cleaned_data["phone_number"].replace(" ", "")
            email = form.cleaned_data["email"].lower().strip()

            if phone.startswith("0"):
                phone = phone[1:]

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
                send_mail(
                    "Your Rooms4You Driver Account",
                    (
                        f"Welcome to Bakkie4You.\n\n"
                        f"Login Email: {email}\n"
                        f"Temporary Password: {temp_password}\n\n"
                        f"Your application is under review."
                    ),
                    None,
                    [email],
                    fail_silently=False,
                )

            except Exception as e:
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

    return render(request, "services/register_driver.html", {
        "form": form
    })


@login_required
def driver_dashboard(request):

    driver = BakkieDriver.objects.filter(user=request.user).first()

    if not driver:
        messages.error(request, "Driver profile not found.")
        return redirect("services:bakkie_home")

    if not driver.is_verified:
        messages.warning(request, "Account still pending approval.")
        return redirect("services:bakkie_home")

    return render(request, "services/driver_dashboard.html", {
        "driver": driver
    })