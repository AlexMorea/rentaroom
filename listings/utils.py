import re
import secrets

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from services.models import BakkieDriver
from utils.email import send_template_email


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