import logging
import re
from datetime import timedelta
from secrets import compare_digest

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.state_engine import get_user_state

from ..forms import UserRegisterForm
from ..models import PhoneOTP, Profile
from ..services.sms import (
    SMSNotConfigured,
    SMSSendError,
    check_verification,
    sms_enabled,
    start_verification,
)
from ..utils import generate_otp, send_otp_email, send_welcome_email
from .helpers import get_display_name, get_or_create_membership

logger = logging.getLogger(__name__)

OTP_RESEND_SECONDS = 90


def _mask_phone(phone):
    p = (phone or "").strip()
    if len(p) < 5:
        return p or "your phone"
    return f"{p[:3]}•••{p[-2:]}"


def _pending_e164(country_code, phone):
    """Build an E.164 number from the raw country_code + local number a
    user typed on the change-phone form."""
    cc = (country_code or "+27").strip()
    digits = re.sub(r"[^\d]", "", phone or "")
    digits = digits.removeprefix(cc.lstrip("+"))
    digits = digits.lstrip("0")
    return f"{cc}{digits}"


def _send_account_otp(user):
    """
    Send a signup / login verification code to ``user``. Prefers SMS via
    Twilio Verify and falls back to email OTP when SMS is unconfigured or
    fails. Returns the channel actually used: ``"sms"``, ``"email"`` or
    ``None`` if nothing could be sent.
    """
    profile = user.profile
    phone = profile.full_phone() if hasattr(profile, "full_phone") else ""

    if sms_enabled() and phone:
        try:
            start_verification(phone)
            return "sms"
        except (SMSNotConfigured, SMSSendError):
            logger.warning(
                "SMS OTP unavailable for user %s - falling back to email", user.pk
            )

    otp = generate_otp()
    PhoneOTP.objects.filter(user=user).delete()
    PhoneOTP.objects.create(
        user=user,
        phone_number=phone or "email_verification",
        otp=otp,
    )
    try:
        send_otp_email(user, otp)
    except Exception:
        logger.exception("Failed to send OTP email for user %s", user.pk)
        return None
    return "email"


def _verify_account_otp(user, channel, otp_input):
    """Return True when ``otp_input`` is the valid code for ``user`` on
    the given ``channel``."""
    if channel == "sms":
        try:
            return check_verification(user.profile.full_phone(), otp_input)
        except SMSNotConfigured:
            return False

    record = (
        PhoneOTP.objects.filter(
            user=user,
            is_verified=False,
            created_at__gte=timezone.now() - timedelta(minutes=15),
        )
        .order_by("-created_at")
        .first()
    )
    if record and compare_digest(record.otp, otp_input):
        record.is_verified = True
        record.save()
        return True
    return False


def register(request):
    form = UserRegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

            user = form.save()   # <-- fixed

            user.is_active = True
            user.save()

            request.session["pending_user_id"] = user.id

            channel = _send_account_otp(user)
            request.session["otp_channel"] = channel or "email"

            if channel == "sms":
                set_otp_cooldown(user.id)
                messages.success(
                    request,
                    "Account created. Enter the code we texted to "
                    f"{_mask_phone(user.profile.full_phone())}."
                )
            elif channel == "email":
                set_otp_cooldown(user.id)
                messages.success(
                    request,
                    "Account created. Enter the OTP sent to your email."
                )
            else:
                messages.warning(
                    request,
                    "Account created, but we couldn't send your verification "
                    "code. Use the resend button on the next page to try again."
                )

            return redirect("verify_account")

    return render(
        request,
        "listings/register.html",
        {"form": form, "sms_otp_enabled": sms_enabled()}
    )


def verify_account(request):
    user_id = request.session.get("pending_user_id")

    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    channel = request.session.get("otp_channel", "email")
    ctx = {"otp_channel": channel}

    if request.method == "POST":

        otp_input = (request.POST.get("otp") or "").strip()

        attempt_key = f"otp_attempts_{user.id}"
        attempts = cache.get(attempt_key, 0)

        if attempts >= 5:
            messages.error(request, "Too many attempts. Try again later.")
            return render(request, "listings/verify_account.html", ctx)

        if not otp_input:
            messages.error(request, "Enter OTP.")
            return render(request, "listings/verify_account.html", ctx)

        if _verify_account_otp(user, channel, otp_input):

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
                logger.exception("Failed to send welcome email for user %s", user.pk)

            login(request, user)

            request.session.pop("pending_user_id", None)
            request.session.pop("otp_channel", None)

            messages.success(
                request,
                "Account verified successfully 🎉"
            )

            cache.delete(attempt_key)

            state = get_user_state(user)
            return redirect(state["next_route"])

        messages.error(request, "Invalid or expired OTP")

        cache.set(attempt_key, attempts + 1, timeout=900)

    return render(request, "listings/verify_account.html", ctx)


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
        # Send a fresh code, but not more often than the resend cooldown
        # (keeps a login-retry loop from burning SMS credit).
        if not cache.get(f"otp_resend_{user.id}"):
            channel = _send_account_otp(user)
            request.session["otp_channel"] = channel or "email"
            if channel:
                set_otp_cooldown(user.id)
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

    state = get_user_state(user)
    return redirect(state["next_route"])


@require_POST
@never_cache
def user_logout(request):
    logout(request)
    messages.success(request, "You’ve been logged out.")
    return redirect("room_list")


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

    channel = _send_account_otp(user)

    if not channel:
        return JsonResponse({
            "level": "error",
            "message": "Couldn't send the code. Please try again shortly."
        }, status=502)

    request.session["otp_channel"] = channel
    set_otp_cooldown(user.id)

    return JsonResponse({
        "level": "success",
        "message": (
            "Code sent by SMS." if channel == "sms"
            else "OTP sent to your email."
        ),
        "cooldown": OTP_RESEND_SECONDS
    })


def set_otp_cooldown(user_id):
    cache.set(
        f"otp_resend_{user_id}",
        True,
        timeout=OTP_RESEND_SECONDS
    )


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
        e164 = _pending_e164(country_code, phone)

        channel = "email"
        if sms_enabled():
            try:
                start_verification(e164)
                channel = "sms"
            except (SMSNotConfigured, SMSSendError):
                logger.warning(
                    "SMS OTP unavailable for phone change (user %s) - using email",
                    user.pk,
                )

        if channel == "email":
            otp = generate_otp()
            PhoneOTP.objects.filter(user=user).delete()
            PhoneOTP.objects.create(user=user, phone_number=phone, otp=otp)
            send_otp_email(user, otp)

        # Store everything the confirm step needs
        request.session["pending_phone"] = phone
        request.session["pending_country_code"] = country_code
        request.session["pending_phone_e164"] = e164
        request.session["pending_phone_channel"] = channel

        messages.success(
            request,
            "Code sent by SMS." if channel == "sms" else "OTP sent to your email."
        )
        return redirect("confirm_phone_change")

    return render(request, "listings/change_phone.html")


@login_required
def confirm_phone_change(request):
    if request.method == "POST":

        otp = (request.POST.get("otp") or "").strip()
        pending_phone = request.session.get("pending_phone")
        pending_country_code = request.session.get("pending_country_code")
        pending_e164 = request.session.get("pending_phone_e164")
        channel = request.session.get("pending_phone_channel", "email")

        if not pending_phone:
            return redirect("profile")

        if channel == "sms":
            try:
                ok = check_verification(pending_e164, otp)
            except SMSNotConfigured:
                ok = False
        else:
            ok = PhoneOTP.objects.filter(
                user=request.user,
                phone_number=pending_phone,
                otp=otp,
                created_at__gte=timezone.now() - timedelta(minutes=15)
            ).exists()

        if ok:
            profile = request.user.profile

            profile.phone_number = pending_phone
            profile.country_code = pending_country_code
            profile.is_phone_verified = True
            profile.save()

            PhoneOTP.objects.filter(user=request.user).delete()

            for key in (
                "pending_phone",
                "pending_country_code",
                "pending_phone_e164",
                "pending_phone_channel",
            ):
                request.session.pop(key, None)

            messages.success(
                request,
                "Phone updated successfully."
            )

            return redirect("profile")

        messages.error(request, "Invalid OTP.")

    return render(
        request,
        "listings/confirm_phone.html",
        {"otp_channel": request.session.get("pending_phone_channel", "email")},
    )


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


def handle_phone_change(user_obj, profile_obj, new_phone):
    if not new_phone or new_phone == profile_obj.phone_number:
        return
    
    profile_obj.phone_number = new_phone
    profile_obj.is_phone_verified = False

