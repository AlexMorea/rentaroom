import random
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
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
    return str(random.randint(100000, 999999))


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


