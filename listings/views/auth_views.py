import logging
import re
from datetime import timedelta
from secrets import compare_digest

import requests
from django.conf import settings
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

from accounts.devices import is_known_device, remember_device
from accounts.state_engine import get_user_state

from ..forms import GoogleCompleteProfileForm, UserRegisterForm
from ..models import PhoneOTP, Profile
from ..utils import generate_otp, send_new_device_otp_email, send_otp_email, send_welcome_email
from .helpers import get_display_name, get_or_create_membership

logger = logging.getLogger(__name__)

OTP_RESEND_SECONDS = 90
DEVICE_OTP_PURPOSE = "device_verification"
# Deliberately distinct from the plain "otp_resend_{id}" key used by the
# signup/email-change OTP flows - sharing one key would mean triggering a
# device challenge could leave a stale cooldown that blocks an unrelated
# "resend signup OTP" request for the same user id (or vice versa).
DEVICE_OTP_RESEND_PREFIX = "device_otp_resend"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# Login attempt limits. Two separate counters, not one:
# - IP-based (existing) stops one attacker hammering many accounts from
#   the same machine/botnet node.
# - Account-based (below) stops a targeted credential-stuffing attack on
#   ONE known account (e.g. a landlord's public email) spread across many
#   different IPs/proxies - the IP counter alone never triggers for that,
#   since no single IP crosses its threshold.
# Tighter limit + longer cooldown than the IP counter, since it's scoped
# to a single identifier and a legitimate user rarely needs 7 tries.
ACCOUNT_LOGIN_MAX_ATTEMPTS = 7
ACCOUNT_LOGIN_LOCKOUT_SECONDS = 1800

def register(request):
    form = UserRegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

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

            try:
                send_otp_email(user, otp)
            except Exception:
                logger.exception("Failed to send signup OTP email for user %s", user.pk)
                messages.warning(
                    request,
                    "Account created, but we couldn't send the OTP email. "
                    "Use the resend button on the next page to try again."
                )
            else:
                set_otp_cooldown(user.id)

                messages.success(
                    request,
                    "Account created. Enter the OTP sent to your email."
                )

            request.session["pending_user_id"] = user.id

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
                logger.exception("Failed to send welcome email for user %s", user.pk)

            login(request, user)

            request.session.pop("pending_user_id", None)

            messages.success(
                request,
                "Account verified successfully 🎉"
            )

            cache.delete(attempt_key)

            state = get_user_state(user)
            response = redirect(state["next_route"])
            # This device just completed a real OTP challenge (the signup
            # one) - no need to challenge it again on its very next
            # request, so it's trusted from here on.
            remember_device(response, request, user)
            return response

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

    # Keyed on the raw submitted identifier (lowercased), not on whether
    # it resolves to a real account - checking/incrementing this the same
    # way regardless of account existence means the lockout itself can't
    # be used to probe which emails are registered.
    account_key = f"login_attempts_account:{login_value.lower()}"
    account_attempts = cache.get(account_key, 0)

    if login_value and account_attempts >= ACCOUNT_LOGIN_MAX_ATTEMPTS:
        messages.error(request, "Too many login attempts on this account. Try again later.")
        return redirect("login")

    user_obj = (
        User.objects.filter(email__iexact=login_value).first()
        or User.objects.filter(username__iexact=login_value).first()
    )

    if not user_obj:
        cache.set(login_key, attempts + 1, timeout=900)
        cache.set(account_key, account_attempts + 1, timeout=ACCOUNT_LOGIN_LOCKOUT_SECONDS)
        messages.error(request, "Invalid credentials.")
        return redirect("login")


    user = authenticate(request, username=user_obj.username, password=password)

    if not user:
        cache.set(login_key, attempts + 1, timeout=900)
        cache.set(account_key, account_attempts + 1, timeout=ACCOUNT_LOGIN_LOCKOUT_SECONDS)
        messages.error(request, "Invalid credentials.")
        return redirect("login")

    cache.delete(account_key)

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

    cache.delete(login_key)

    # NEW DEVICE CHECK - a device that hasn't completed this challenge
    # before doesn't get a session yet, no matter how correct the
    # password was. It has to prove it's really this person first.
    if not is_known_device(request, user):
        return _start_device_challenge(request, user)

    login(request, user)

    messages.success(
        request,
        f"Welcome back {get_display_name(user)} 👋"
    )

    # FORCE PASSWORD CHANGE
    if getattr(profile, "must_change_password", False):
        return redirect("change_password")

    state = get_user_state(user)
    return redirect(state["next_route"])


def _start_device_challenge(request, user):
    """
    Shared by the password login path and the Google sign-in path for an
    existing account: sends a one-time code to the account's email and
    parks the pending user id in session until verify_device confirms it.
    """
    otp = generate_otp()

    PhoneOTP.objects.filter(user=user).delete()

    PhoneOTP.objects.create(
        user=user,
        phone_number=DEVICE_OTP_PURPOSE,
        otp=otp,
    )

    try:
        send_new_device_otp_email(user, otp)
    except Exception:
        logger.exception("Failed to send new-device OTP email for user %s", user.pk)
        messages.error(
            request,
            "We couldn't send a verification code. Please try logging in again shortly."
        )
        return redirect("login")

    set_otp_cooldown(user.id, prefix=DEVICE_OTP_RESEND_PREFIX)

    request.session["pending_device_user_id"] = user.id

    messages.info(
        request,
        "We don't recognise this device. Enter the code we just emailed you to continue."
    )

    return redirect("verify_device")


def verify_device(request):
    user_id = request.session.get("pending_device_user_id")

    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":

        otp_input = request.POST.get("otp")

        attempt_key = f"device_otp_attempts_{user.id}"
        attempts = cache.get(attempt_key, 0)

        if attempts >= 5:
            messages.error(request, "Too many attempts. Try logging in again later.")
            return render(request, "listings/verify_device.html")

        if not otp_input:
            messages.error(request, "Enter the code.")
            return render(request, "listings/verify_device.html")

        record = PhoneOTP.objects.filter(
            user=user,
            phone_number=DEVICE_OTP_PURPOSE,
            is_verified=False,
            created_at__gte=timezone.now() - timedelta(minutes=15),
        ).order_by("-created_at").first()

        if record and compare_digest(record.otp, otp_input):
            record.is_verified = True
            record.save()

            PhoneOTP.objects.filter(user=user, phone_number=DEVICE_OTP_PURPOSE).delete()

            login(request, user)

            request.session.pop("pending_device_user_id", None)
            cache.delete(attempt_key)

            messages.success(request, f"Welcome back {get_display_name(user)} 👋")

            state = get_user_state(user)
            response = redirect(state["next_route"])
            remember_device(response, request, user)
            return response

        messages.error(request, "Invalid or expired code.")
        cache.set(attempt_key, attempts + 1, timeout=900)

    return render(request, "listings/verify_device.html")


def resend_device_otp(request):
    user_id = request.session.get("pending_device_user_id")

    if not user_id:
        return JsonResponse({
            "level": "error",
            "message": "Your session has expired. Please log in again."
        }, status=400)

    user = get_object_or_404(User, id=user_id)

    cache_key = f"{DEVICE_OTP_RESEND_PREFIX}_{user.id}"

    if cache.get(cache_key):
        return JsonResponse({
            "level": "warning",
            "message": "Please wait before requesting another code.",
            "cooldown": OTP_RESEND_SECONDS
        }, status=429)

    cache.delete(f"device_otp_attempts_{user.id}")

    otp = generate_otp()

    PhoneOTP.objects.filter(user=user).delete()

    PhoneOTP.objects.create(
        user=user,
        phone_number=DEVICE_OTP_PURPOSE,
        otp=otp,
    )

    try:
        send_new_device_otp_email(user, otp)
    except Exception:
        logger.exception("Failed to send device-verification resend for user %s", user.pk)
        return JsonResponse({
            "level": "error",
            "message": "Couldn't send the code. Please try again shortly."
        }, status=502)

    set_otp_cooldown(user.id, prefix=DEVICE_OTP_RESEND_PREFIX)

    return JsonResponse({
        "level": "success",
        "message": "Code sent successfully.",
        "cooldown": OTP_RESEND_SECONDS
    })


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

    otp = generate_otp()

    PhoneOTP.objects.filter(user=user).delete()

    PhoneOTP.objects.create(
        user=user,
        phone_number="email_verification",
        otp=otp
    )

    try:
        send_otp_email(user, otp)
    except Exception:
        logger.exception("Failed to send resend OTP email for user %s", user.pk)
        return JsonResponse({
            "level": "error",
            "message": "Couldn't send the OTP email. Please try again shortly."
        }, status=502)

    set_otp_cooldown(user.id)

    return JsonResponse({
        "level": "success",
        "message": "OTP sent successfully.",
        "cooldown": OTP_RESEND_SECONDS
    })


def set_otp_cooldown(user_id, prefix="otp_resend"):
    cache.set(
        f"{prefix}_{user_id}",
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


# ---------------------------------------------------------------------
# "Continue with Google"
# ---------------------------------------------------------------------
def _verify_google_credential(credential):
    """
    Verifies a Google Identity Services ID token by asking Google's own
    tokeninfo endpoint about it, rather than pulling in a whole OAuth
    client library for one signature check. Returns the decoded claims
    dict on success, or None on any failure (network, bad token, wrong
    audience, unverified email) - callers just treat None as "sign-in
    failed", they don't need to know why.
    """
    if not credential:
        return None

    try:
        resp = requests.get(
            GOOGLE_TOKENINFO_URL,
            params={"id_token": credential},
            timeout=8,
        )
    except requests.RequestException:
        logger.exception("Google tokeninfo request failed")
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()

    if data.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID:
        logger.warning("Google credential audience mismatch")
        return None

    if data.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None

    if str(data.get("email_verified", "")).lower() != "true":
        return None

    return data


@require_POST
@never_cache
def google_auth(request):
    """
    Receives the ID token from the "Continue with Google" button on
    login/register (see listings/templates/listings/login.html) and
    either logs the matching existing account in (still subject to the
    same new-device challenge as a password login) or, for a brand new
    email, parks it in session and sends them to
    google_complete_profile to pick a role/phone before an account is
    fully usable.
    """
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        messages.error(request, "Google sign-in isn't available right now.")
        return redirect("login")

    data = _verify_google_credential(request.POST.get("credential"))

    if not data:
        messages.error(request, "Google sign-in failed. Please try again.")
        return redirect("login")

    email = (data.get("email") or "").strip().lower()
    if not email:
        messages.error(request, "Google sign-in failed. Please try again.")
        return redirect("login")

    user = User.objects.filter(email__iexact=email).first()

    if user is None:
        first_name = (data.get("given_name") or "").strip()
        last_name = (data.get("family_name") or "").strip()

        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.is_active = True
        user.save()

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_email_verified = True
        profile.save(update_fields=["is_email_verified"])

        request.session["google_pending_user_id"] = user.id
        return redirect("google_complete_profile")

    profile = getattr(user, "profile", None)

    if profile is None or not profile.is_phone_verified:
        # An account that exists but never finished onboarding (e.g. it
        # was created outside the normal signup flow) - finish it the
        # same way a fresh Google signup would.
        request.session["google_pending_user_id"] = user.id
        return redirect("google_complete_profile")

    if not user.is_active:
        messages.error(request, "This account has been deactivated.")
        return redirect("login")

    if is_known_device(request, user):
        login(request, user)
        messages.success(request, f"Welcome back {get_display_name(user)} 👋")
        state = get_user_state(user)
        return redirect(state["next_route"])

    return _start_device_challenge(request, user)


def google_complete_profile(request):
    user_id = request.session.get("google_pending_user_id")

    if not user_id:
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = GoogleCompleteProfileForm(request.POST)

        if form.is_valid():
            form.apply_to(user)

            login(request, user)
            request.session.pop("google_pending_user_id", None)

            messages.success(request, f"Welcome to Rooms4You, {get_display_name(user)} 🎉")

            state = get_user_state(user)
            response = redirect(state["next_route"])
            # Google's own auth just verified this person, and this
            # profile step stands in for the OTP step - this device is
            # trusted from here on, same as a fresh normal signup.
            remember_device(response, request, user)
            return response
    else:
        form = GoogleCompleteProfileForm()

    return render(request, "listings/google_complete_profile.html", {"form": form})

