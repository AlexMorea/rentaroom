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


def send_otp_email(user, otp):
    send_template_email(
        subject="Your Rooms4You OTP Code",
        to_email=user.email,
        template="emails/otp.html",
        context={
            "user": user,
            "otp": otp,
            "year": 2026
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
        subject="Confirm it's you - new sign-in to Rooms4You",
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
            "app_url": "https://rooms4you.co.za",
            "year": 2026,
        }
    )


def send_welcome_whatsapp(user):
    if hasattr(user, "profile"):
        name = (user.first_name or user.username or "").strip()
        send_whatsapp_template(user.profile, settings.WHATSAPP_TEMPLATE_WELCOME, params=[name])


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