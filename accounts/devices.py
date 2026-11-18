"""
Remembered devices for the login-time "confirm it's you" code.

A browser gets one random token in a long-lived, HttpOnly cookie. Each
account that completes the emailed code on that browser stores a hash of
the token (TrustedDevice), so several accounts can share one phone or
laptop without knocking each other out. Trust slides: every sign-in from
a remembered device refreshes the cookie, and a device that hasn't been
used for DEVICE_TRUST_DAYS has to confirm again. Changing or resetting a
password, or removing a device in Settings, ends that trust.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import TrustedDevice

DEVICE_COOKIE_NAME = "r4y_device"
DEVICE_TRUST_DAYS = 90
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * DEVICE_TRUST_DAYS


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def describe_device(request) -> str:
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return ua or "Unknown device"


def is_known_device(request, user) -> bool:
    token = request.COOKIES.get(DEVICE_COOKIE_NAME)
    if not token:
        return False

    device = TrustedDevice.objects.filter(user=user, token_hash=hash_token(token)).first()
    if not device:
        return False

    # Unused for too long: confirm again (the stale record goes too).
    if device.last_seen_at < timezone.now() - timedelta(days=DEVICE_TRUST_DAYS):
        device.delete()
        return False

    return True


def remember_device(response, request, user):
    """
    Trusts this browser for `user` and (re)sets the cookie for another
    DEVICE_TRUST_DAYS. Called after a verified login (emailed code, signup
    code, Google sign-up) and on every sign-in from a remembered device.
    Reuses the browser's existing token so other accounts already trusted
    on it stay trusted.
    """
    token = request.COOKIES.get(DEVICE_COOKIE_NAME) or secrets.token_urlsafe(32)

    device, created = TrustedDevice.objects.get_or_create(
        user=user,
        token_hash=hash_token(token),
        defaults={"label": describe_device(request)},
    )
    if not created:
        device.label = describe_device(request)
        device.save(update_fields=["label", "last_seen_at"])

    response.set_cookie(
        DEVICE_COOKIE_NAME,
        token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )
    return response


def forget_devices(user, *, keep_request=None):
    """Ends device trust for `user` after a password change or reset.
    Pass the current request to keep the device the change was made on."""
    devices = TrustedDevice.objects.filter(user=user)
    token = keep_request.COOKIES.get(DEVICE_COOKIE_NAME) if keep_request else None
    if token:
        devices = devices.exclude(token_hash=hash_token(token))
    devices.delete()
