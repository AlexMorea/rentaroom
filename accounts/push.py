"""
Web Push (VAPID) helpers.

Deliberately self-contained: unlike SMS/email, web push needs no
third-party account, API key, or paid service - just a keypair the app
generates itself and stores as env vars (see settings.VAPID_PRIVATE_KEY_PEM
/ VAPID_PUBLIC_KEY). The browser's push service (Google's for Chrome,
Mozilla's for Firefox, etc.) does the actual delivery for free once a
user has subscribed.
"""

import base64
import json
import logging

logger = logging.getLogger(__name__)


def generate_ephemeral_vapid_keys() -> tuple[str, str]:
    """
    Generate a throwaway VAPID keypair for local dev/tests, matching the
    ephemeral-SECRET_KEY pattern already used elsewhere in settings.py.
    Not persisted anywhere - a dev server restart gets a new pair, which
    is fine since it just means locally-created push subscriptions go
    stale (there's nothing else keyed off it).
    """
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    vapid = Vapid()
    vapid.generate_keys()
    assert vapid.public_key is not None  # always set immediately by generate_keys()

    private_pem = vapid.private_pem().decode("utf-8")

    raw_public = vapid.public_key.public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    public_b64url = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode("ascii")

    return private_pem, public_b64url


def send_web_push(subscription, *, title: str, body: str, url: str = "/") -> bool:
    """
    Send one push notification to one subscription. Returns True on
    success. On a 404/410 (the browser/user has revoked the
    subscription - the single most common failure mode) the dead
    subscription is deleted so we stop wasting requests on it; any
    other failure is logged and swallowed, since a failed push should
    never break the request that triggered it (e.g. sending a message).
    """
    from django.conf import settings
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    if not (settings.VAPID_PRIVATE_KEY_PEM and settings.VAPID_PUBLIC_KEY):
        return False

    payload = json.dumps({"title": title, "body": body, "url": url})

    # pywebpush's `vapid_private_key` only handles a raw string as a RAW/DER
    # key or a filesystem path (see Vapid.from_string) - a full PEM block
    # (what generate_ephemeral_vapid_keys()/generate_vapid_keys produce)
    # has to be parsed into a Vapid instance first via from_pem(), or this
    # raises ValueError deep inside `cryptography` instead of the
    # WebPushException this function is built to handle.
    vapid = Vapid.from_pem(settings.VAPID_PRIVATE_KEY_PEM.encode("utf-8"))

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=vapid,
            vapid_claims={
                "sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL}",
            },
        )
        return True
    except WebPushException as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code in (404, 410):
            subscription.delete()
        else:
            logger.warning("Web push failed (%s): %s", status_code, exc)
        return False


def notify_user(user, *, title: str, body: str, url: str = "/") -> int:
    """
    Push to every device a user has subscribed on. Returns how many
    sends succeeded. Safe to call unconditionally - a user with zero
    subscriptions (the common case today, since it's opt-in) just costs
    one empty queryset lookup.
    """
    from .models import PushSubscription

    sent = 0
    for subscription in PushSubscription.objects.filter(user=user):
        if send_web_push(subscription, title=title, body=body, url=url):
            sent += 1
    return sent
