"""
WhatsApp Business Platform (Meta Cloud API) notifications.

A *bonus* channel alongside email/push, never a replacement for either -
every call site here is additional to (not instead of) the existing
send_template_email()/notify_user() calls, so nothing regresses if
WhatsApp delivery fails or isn't configured yet.

Dormant by design, same pattern as VAPID push (accounts/push.py) and the
Brevo email backend (listings/email_backend.py): until WHATSAPP_ACCESS_TOKEN
and WHATSAPP_PHONE_NUMBER_ID are set to real values from Meta Business
Manager, every call here is a silent no-op. The day those env vars are
set, every already-wired touchpoint starts actually sending, with no
further code change - see docs/whatsapp_setup.md for how to get them.

WhatsApp only lets a business message someone outside a live
customer-service session using a pre-approved Message Template. Each
logical message below is mapped to a template *name* pulled from
settings (WHATSAPP_TEMPLATE_*) rather than hardcoded, so the actual
approved template can be renamed/resubmitted in Meta Business Manager
without a code change.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v20.0"


def whatsapp_enabled() -> bool:
    return bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def _digits_only(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def send_whatsapp_template(profile, template_name: str, *, params: list | None = None) -> bool:
    """
    Sends one approved WhatsApp template to `profile`'s phone number.
    Returns True only on a confirmed send from Meta. Never raises - a
    WhatsApp failure (unconfigured, no/bad number on file, template not
    approved yet, rate limited) should never break whatever triggered
    it, exactly like accounts.push.send_web_push.
    """
    if not whatsapp_enabled() or not template_name or profile is None:
        return False

    to_phone = _digits_only(profile.whatsapp_full_number())
    if not to_phone:
        return False

    body_params = [{"type": "text", "text": str(p)} for p in (params or [])]
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en"},
            "components": [{"type": "body", "parameters": body_params}] if body_params else [],
        },
    }
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("WhatsApp send failed (template=%s): %s", template_name, exc)
        return False

    if response.status_code >= 300:
        logger.warning(
            "WhatsApp send failed (template=%s): %s %s",
            template_name, response.status_code, response.text,
        )
        return False

    return True
