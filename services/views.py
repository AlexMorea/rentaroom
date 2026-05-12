import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone

from .models import (
    GuardianSession,
    GuardianLocationPing,
    PanicAlert,
    BakkieDriver
)

from .forms import GuardianSessionForm, BakkieDriverForm



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


# PANIC BUTTON

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

    existing = None
    if request.user.is_authenticated:
        existing = BakkieDriver.objects.filter(
            user=request.user
        ).first()

    if existing:
        messages.info(request, "You are already registered.")
        return redirect("services:bakkie_home")

    if request.method == "POST":
        form = BakkieDriverForm(request.POST, request.FILES)

        if form.is_valid():
            driver = form.save(commit=False)

            if request.user.is_authenticated:
                driver.user = request.user

            driver.is_verified = False
            driver.save()

            messages.success(
                request,
                "Driver submitted for verification. Please login after approval."
            )

            return redirect("login")

    else:
        form = BakkieDriverForm()

    return render(request, "services/register_driver.html", {
        "form": form
    })

@login_required
def driver_dashboard(request):

    driver = BakkieDriver.objects.filter(
        user=request.user,
        is_verified=True
    ).first()

    if not driver:
        messages.error(
            request,
            "Your driver account is pending verification."
        )
        return redirect("services:bakkie_home")

    return render(
        request,
        "services/driver_dashboard.html",
        {
            "driver": driver
        }
    )