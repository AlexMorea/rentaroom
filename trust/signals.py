import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from utils.email import send_template_email

from .models import FraudReport

logger = logging.getLogger(__name__)


@receiver(post_save, sender=FraudReport)
def notify_staff_of_new_report(sender, instance, created, **kwargs):
    """
    A FraudReport that only ever sits in the Django admin until someone
    remembers to check is functionally the same as no report system at
    all - "we investigate reports" (the Trust Centre's own promise) needs
    someone to actually find out a report exists. Failure here is
    swallowed (logged, not raised) so a broken email backend can never
    block a user's report from being saved.
    """
    if not created:
        return

    is_repeat = instance.is_repeat_offender

    context = {
        "report": instance,
        "is_repeat_offender": is_repeat,
        "related_count": instance.related_open_reports.count(),
        "admin_url": "https://www.rooms4you.co.za"
        + reverse("admin:trust_fraudreport_change", args=[instance.pk]),
        "year": timezone.now().year,
    }

    subject = f"New fraud report: {instance.get_category_display()}"
    if is_repeat:
        subject = f"🚨 REPEAT — {subject}"

    try:
        send_template_email(
            subject=subject,
            to_email=settings.SAFETY_TEAM_EMAIL,
            template="emails/staff_new_fraud_report.html",
            context=context,
        )
    except Exception:
        logger.exception("Failed to notify staff of new fraud report #%s", instance.pk)
