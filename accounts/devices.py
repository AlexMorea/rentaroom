import hashlib
import secrets

from django.conf import settings

from .models import TrustedDevice

DEVICE_COOKIE_NAME = "r4y_device"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def describe_device(request) -> str:
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return ua or "Unknown device"


def is_known_device(request, user) -> bool:
    token = request.COOKIES.get(DEVICE_COOKIE_NAME)
    if not token:
        return False

    device = TrustedDevice.objects.filter(
        user=user, token_hash=hash_token(token)
    ).first()

    if not device:
        return False

    device.save(update_fields=["last_seen_at"])
    return True


def remember_device(response, request, user):
    """
    Issues a fresh device token, stores its hash against this user, and
    sets it as a long-lived cookie on the response. Called once a login
    has been fully verified (password + OTP challenge, or a brand new
    signup's very first login) - never before that point.
    """
    token = secrets.token_urlsafe(32)

    TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token(token),
        label=describe_device(request),
    )

    response.set_cookie(
        DEVICE_COOKIE_NAME,
        token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )
    return response
