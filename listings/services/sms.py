"""
SMS OTP delivery via Twilio Verify.

Twilio Verify owns the whole one-time-code lifecycle: it generates the
code, sends the SMS, enforces expiry (default 10 min), caps delivery
attempts and runs Fraud Guard against SMS-pumping. We only ever make two
calls - `start_verification` (send a code) and `check_verification`
(is this the right code?).

Everything here is a no-op unless `settings.SMS_OTP_ENABLED` is true,
which itself requires TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN /
TWILIO_VERIFY_SERVICE_SID to all be set. Callers should treat a
`SMSNotConfigured` or `SMSSendError` as "fall back to email OTP".
"""

import logging

from django.conf import settings

logger = logging.getLogger("rooms4you_sms")


class SMSNotConfigured(Exception):
    """Twilio credentials are missing or SMS OTP is switched off."""


class SMSSendError(Exception):
    """Twilio accepted the request but could not send / verify."""


def sms_enabled():
    return bool(getattr(settings, "SMS_OTP_ENABLED", False))


def _service():
    """Return the Twilio Verify service resource, or raise SMSNotConfigured."""
    if not sms_enabled():
        raise SMSNotConfigured("SMS OTP is not configured")

    # Imported lazily so the twilio package is only touched when actually used.
    from twilio.rest import Client

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return client.verify.v2.services(settings.TWILIO_VERIFY_SERVICE_SID)


def start_verification(phone, channel="sms"):
    """
    Ask Twilio to generate a code and send it to `phone` (E.164, e.g.
    +27821234567). Returns True when Twilio has the verification pending.
    Raises SMSNotConfigured / SMSSendError so the caller can fall back.
    """
    if not phone:
        raise SMSSendError("No phone number to send to")

    service = _service()

    try:
        verification = service.verifications.create(to=phone, channel=channel)
    except Exception as exc:  # TwilioRestException, connection errors, etc.
        logger.error("Twilio verify start failed for %s: %s", phone, exc)
        raise SMSSendError(str(exc)) from exc

    logger.info("Twilio verify start %s -> %s", phone, verification.status)
    return verification.status in ("pending", "approved")


def check_verification(phone, code):
    """
    Return True if `code` is the valid, unexpired OTP for `phone`.
    A wrong/expired code returns False; a config problem raises
    SMSNotConfigured.
    """
    if not phone or not code:
        return False

    service = _service()

    try:
        check = service.verification_checks.create(to=phone, code=str(code).strip())
    except Exception as exc:
        # A 404 here just means "no pending verification for this number"
        # (already used, expired, or never sent); other errors we also
        # can't act on - treat all as a failed check so the user retries.
        logger.warning("Twilio verify check failed for %s: %s", phone, exc)
        return False

    logger.info("Twilio verify check %s -> %s", phone, check.status)
    return check.status == "approved"


# ---------------------------------------------------------------------------
# Back-compat shim: the old stub exported send_otp_sms(phone, otp). Nothing
# imports it any more, but keep a working version in case something does -
# Verify ignores our generated code and sends its own, so `otp` is unused.
def send_otp_sms(phone, otp=None):
    return start_verification(phone)
