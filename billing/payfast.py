"""
PayFast integration - checkout form signing, ITN (payment notification)
verification, and subscription cancellation.

Security model: a payment only counts once PayFast's server-to-server
notification (ITN) passes ALL of:
  1. our MD5 signature check (with the shared passphrase),
  2. PayFast's own /eng/query/validate confirming they sent it,
  3. the amount matching what we asked for.
The browser landing on the return URL proves nothing and changes
nothing.

Docs: https://developers.payfast.co.za/docs
"""
import hashlib
import logging
from collections.abc import Iterable
from decimal import Decimal
from urllib.parse import quote_plus

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

LIVE_HOST = "www.payfast.co.za"
SANDBOX_HOST = "sandbox.payfast.co.za"
API_BASE = "https://api.payfast.co.za"

# PayFast subscription frequency codes.
FREQUENCY_MONTHLY = 3
FREQUENCY_ANNUAL = 6

# Field order PayFast signs checkout data in - the signature is only
# valid if the fields are concatenated in exactly this order.
CHECKOUT_FIELD_ORDER = (
    "merchant_id", "merchant_key", "return_url", "cancel_url", "notify_url",
    "name_first", "name_last", "email_address", "cell_number",
    "m_payment_id", "amount", "item_name", "item_description",
    "custom_int1", "custom_int2", "custom_int3", "custom_int4", "custom_int5",
    "custom_str1", "custom_str2", "custom_str3", "custom_str4", "custom_str5",
    "email_confirmation", "confirmation_address", "payment_method",
    "subscription_type", "billing_date", "recurring_amount", "frequency", "cycles",
)


def payments_enabled() -> bool:
    return bool(settings.PAYFAST_MERCHANT_ID and settings.PAYFAST_MERCHANT_KEY and settings.PAYFAST_PASSPHRASE)


def host() -> str:
    return SANDBOX_HOST if settings.PAYFAST_SANDBOX else LIVE_HOST


def process_url() -> str:
    return f"https://{host()}/eng/process"


def validate_url() -> str:
    return f"https://{host()}/eng/query/validate"


def _encode(value) -> str:
    return quote_plus(str(value).strip())


def _with_passphrase(param_string: str) -> str:
    passphrase = settings.PAYFAST_PASSPHRASE
    if passphrase:
        return f"{param_string}&passphrase={_encode(passphrase)}"
    return param_string


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()  # noqa: S324 - PayFast's mandated scheme


def format_amount(amount: Decimal) -> str:
    return f"{Decimal(amount):.2f}"


# ---------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------
def checkout_fields(data: dict) -> list[tuple[str, str]]:
    """Returns the signed, ordered (name, value) pairs for the hidden
    checkout form. Empty values are dropped (PayFast ignores them when
    signing too)."""
    fields = {
        "merchant_id": settings.PAYFAST_MERCHANT_ID,
        "merchant_key": settings.PAYFAST_MERCHANT_KEY,
        **data,
    }
    ordered = [
        (name, str(fields[name]).strip())
        for name in CHECKOUT_FIELD_ORDER
        if name in fields and str(fields[name]).strip() != ""
    ]
    param_string = "&".join(f"{k}={_encode(v)}" for k, v in ordered)
    ordered.append(("signature", _md5(_with_passphrase(param_string))))
    return ordered


# ---------------------------------------------------------------------
# ITN verification
# ---------------------------------------------------------------------
def itn_param_string(pairs: Iterable[tuple[str, str]]) -> str:
    """ITN data is signed over every posted field except `signature`, in
    the order PayFast posted them, blank values included."""
    return "&".join(f"{k}={_encode(v)}" for k, v in pairs if k != "signature")


def itn_signature_valid(pairs: list[tuple[str, str]]) -> bool:
    posted = dict(pairs).get("signature", "")
    expected = _md5(_with_passphrase(itn_param_string(pairs)))
    return bool(posted) and posted.lower() == expected


def itn_confirmed_by_payfast(pairs: list[tuple[str, str]]) -> bool:
    """Asks PayFast whether they really sent this notification."""
    try:
        response = requests.post(
            validate_url(),
            data=itn_param_string(pairs),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    except requests.RequestException:
        logger.exception("PayFast ITN validation request failed")
        return False
    return response.status_code == 200 and response.text.strip() == "VALID"


def amount_matches(expected: Decimal, posted: str) -> bool:
    try:
        return abs(Decimal(expected) - Decimal(posted)) <= Decimal("0.01")
    except (ArithmeticError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------
# Subscriptions API
# ---------------------------------------------------------------------
def _api_headers(body: dict | None = None) -> dict:
    headers = {
        "merchant-id": settings.PAYFAST_MERCHANT_ID,
        "version": "v1",
        "timestamp": timezone.localtime().replace(microsecond=0).isoformat(),
    }
    signed = {**headers, **(body or {}), "passphrase": settings.PAYFAST_PASSPHRASE}
    param_string = "&".join(f"{k}={_encode(v)}" for k, v in sorted(signed.items()))
    headers["signature"] = _md5(param_string)
    return headers


def _api_params():
    return {"testing": "true"} if settings.PAYFAST_SANDBOX else None


def subscription_is_cancelled(token: str) -> bool:
    """Asks PayFast for the subscription's current state. Used when the
    cancel call itself didn't give a clear answer."""
    url = f"{API_BASE}/subscriptions/{token}/fetch"
    try:
        response = requests.get(url, headers=_api_headers(), params=_api_params(), timeout=15)
        payload = response.json()
    except (requests.RequestException, ValueError):
        logger.exception("PayFast subscription fetch failed for token %s", token)
        return False
    details = (payload.get("data") or {}).get("response") or {}
    if not isinstance(details, dict):
        return False
    status_text = str(details.get("status_text", "")).upper()
    return status_text == "CANCELLED" or details.get("status") == 2


def cancel_subscription(token: str) -> bool:
    """Stops future debits. Pro carries on until the period already paid
    for runs out.

    PayFast notifies our ITN endpoint *while* handling this call; on a
    server with a single worker that notification queues behind this very
    request, so the call can time out even though PayFast went on to
    cancel. Whenever the answer isn't a clear success, we check the
    subscription's actual status before reporting failure."""
    url = f"{API_BASE}/subscriptions/{token}/cancel"
    try:
        response = requests.put(url, headers=_api_headers(), params=_api_params(), timeout=20)
        if 200 <= response.status_code < 300:
            return True
        logger.warning("PayFast subscription cancel answered %s: %s", response.status_code, response.text[:300])
    except requests.RequestException:
        logger.warning("PayFast subscription cancel got no answer for token %s - checking status", token)

    if subscription_is_cancelled(token):
        return True
    logger.error("PayFast subscription %s still not cancelled - needs staff follow-up", token)
    return False
