import re
import secrets

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from services.models import BakkieDriver
from utils.email import send_template_email
from utils.whatsapp import send_whatsapp_template


def clear_room_list_cache(owner_id="*"):
    """Invalidate cached room-list pages after anything changes what
    they'd show - a room created/edited, or an account getting suspended
    and its listings hidden. `owner_id` narrows the owner-scoped pattern;
    left as "*" it clears every owner's cached view (used when the actor
    isn't the room's own owner, e.g. a staff moderation action)."""
    for pattern in (f"room_list:{owner_id}*", "room_list_ids:*"):
        try:
            cache.delete_pattern(pattern)
        except (AttributeError, TypeError):
            # delete_pattern not available on all cache backends
            pass


# A short list of common disposable/burner email providers used to spin
# up throwaway accounts. Deliberately just a domain-suffix check rather
# than a third-party lookup API - keeps signup working even if such a
# service is down, at the cost of not catching every burner domain that
# exists (this targets the mass-market ones scripted signup abuse
# actually reaches for).
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "sharklasers.com",
    "10minutemail.com", "10minutemail.net", "temp-mail.org", "tempmail.com",
    "yopmail.com", "trashmail.com", "getnada.com", "maildrop.cc", "dispostable.com",
    "throwawaymail.com", "fakeinbox.com", "mailnesia.com", "mintemail.com",
    "moakt.com", "tempinbox.com", "spamgourmet.com", "mytemp.email", "emailondeck.com",
    "discard.email", "mailcatch.com", "burnermail.io", "inboxkitten.com",
})


def is_disposable_email(email: str) -> bool:
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    return domain in DISPOSABLE_EMAIL_DOMAINS


def send_html_email(subject, to_email, template_name, context):
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )

    email.attach_alternative(html_content, "text/html")
    email.send()

def generate_otp():
    return str(secrets.randbelow(900000) + 100000)


def unique_username_for(email):
    """
    New accounts use their email as the username. The username can still
    be taken when the email isn't: someone who changes their email keeps
    the old address as their username, so the next person to sign up with
    that old address used to hit a unique-constraint error (a 500) instead
    of getting an account. Login goes by email first, so a suffix here
    changes nothing for the person signing up.
    """
    from django.contrib.auth.models import User

    base = (email or "").strip().lower()[:150]
    if base and not User.objects.filter(username=base).exists():
        return base
    while True:
        candidate = f"{base[:141]}-{secrets.token_hex(4)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


def send_otp_email(user, otp):
    send_template_email(
        subject="Your Rooms4You verification code",
        to_email=user.email,
        template="emails/otp.html",
        context={
            "user": user,
            "otp": otp
        }
    )


def send_otp_whatsapp(user, otp):
    # Bonus channel alongside the email above, not instead of it - a
    # WhatsApp OTP is often seen faster than an email, especially on a
    # first signup where the inbox isn't open yet.
    if hasattr(user, "profile"):
        send_whatsapp_template(user.profile, settings.WHATSAPP_TEMPLATE_OTP, params=[otp])


def send_new_device_otp_email(user, otp, *, device_label=""):
    send_template_email(
        subject="Confirm it's you: a new sign-in to Rooms4You",
        to_email=user.email,
        template="emails/new_device_otp.html",
        context={
            "user": user,
            "otp": otp,
            "device_label": device_label,
            "year": timezone.now().year,
        },
    )


def send_new_device_otp_whatsapp(user, otp):
    if hasattr(user, "profile"):
        send_whatsapp_template(user.profile, settings.WHATSAPP_TEMPLATE_DEVICE_OTP, params=[otp])


def send_welcome_email(user):
    send_template_email(
        subject="Welcome to Rooms4You",
        to_email=user.email,
        template="emails/welcome.html",
        context={
            "user": user,
            "app_url": "https://rooms4you.co.za"
        }
    )


def send_welcome_whatsapp(user):
    if hasattr(user, "profile"):
        name = (user.first_name or user.username or "").strip()
        send_whatsapp_template(user.profile, settings.WHATSAPP_TEMPLATE_WELCOME, params=[name])


SA_PHONE_INVALID_MESSAGE = "Please enter a valid South African number, e.g. 082 123 4567."
PHONE_INVALID_MESSAGE = "Please enter a valid phone number."


def parse_phone(raw, country_code: str | None = "+27"):
    """
    Turns whatever someone typed into the number we store, or None if it
    can't be a real number.

    South African numbers (the default) need exactly 9 digits after the
    country code. "082 123 4567", "+27 82 123 4567", "27821234567",
    "0027 82 123 4567" and "+27 (0)82 123 4567" all become "+27821234567".
    Two numbers typed into one box, or a digit too few, are rejected here
    rather than saved: they used to be stored as-is, which left tenants
    with a number they couldn't call, and anything over 20 characters
    made the save itself fail on Postgres.

    Other country codes only need a plausible length; they're stored the
    way normalize_sa_phone always stored them, since Profile._format_number
    relies on that shape.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return None

    if (country_code or "+27") != "+27":
        return normalize_sa_phone(digits) if 6 <= len(digits) <= 15 else None

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("27") and len(digits) in (11, 12):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = digits[1:]
    if len(digits) != 9 or digits.startswith("0"):
        return None
    return f"+27{digits}"


def normalize_sa_phone(phone):
    """
    0845643877 -> +27845643877
    +27845643877 -> +27845643877
    27845643877 -> +27845643877
    """

    if not phone:
        return ""

    phone = str(phone).strip()

    # remove spaces/dashes/etc
    phone = re.sub(r"[^\d+]", "", phone)

    # already correct
    if phone.startswith("+27"):
        return phone

    # 2784...
    if phone.startswith("27"):
        return f"+{phone}"

    # 084...
    if phone.startswith("0"):
        return f"+27{phone[1:]}"

    # fallback
    return f"+27{phone}"

def get_user_state(user):
    """
    Single source of truth for user routing.
    """
    profile = user.profile

    driver = None
    if profile.role == "driver":
        driver = BakkieDriver.objects.filter(user=user).first()

    return {
        "role": profile.role,
        "is_verified": profile.is_phone_verified,
        "must_change_password": getattr(profile, "must_change_password", False),
        "driver": driver,
    }