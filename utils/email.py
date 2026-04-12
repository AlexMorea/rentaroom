from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_template_email(subject, to_email, template, context):
    html_content = render_to_string(template, context)
    text_content = "Rooms4You Notification"

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        to=[to_email],
    )

    email.attach_alternative(html_content, "text/html")
    email.send()