from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class FraudReport(models.Model):
    """
    A single fraud/scam/safety report, whether filed against a specific
    Room listing (via room_detail's "Report listing" form) or filed
    generally from the Trust Centre's "Report Fraud" page (impersonation,
    fake WhatsApp/emails, a suspicious payment request, etc. - anything
    that isn't tied to one listing).

    Deliberately one model for both entry points rather than two: staff
    triage them together in one queue either way, and a report that
    starts as "general" often turns out to reference a specific room once
    detail is added.
    """

    CATEGORY_SPAM = "spam"
    CATEGORY_SCAM = "scam"
    CATEGORY_ABUSE = "abuse"
    CATEGORY_WRONG_INFO = "wrong_info"
    CATEGORY_FAKE_LANDLORD = "fake_landlord"
    CATEGORY_FAKE_LISTING = "fake_listing"
    CATEGORY_DEPOSIT_SCAM = "deposit_scam"
    CATEGORY_IMPERSONATION = "impersonation"
    CATEGORY_SUSPICIOUS_PAYMENT = "suspicious_payment"
    CATEGORY_TENANT_UNREACHABLE = "tenant_unreachable"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (CATEGORY_SPAM, "Spam"),
        (CATEGORY_SCAM, "Scam"),
        (CATEGORY_ABUSE, "Abuse"),
        (CATEGORY_WRONG_INFO, "Wrong information"),
        (CATEGORY_FAKE_LANDLORD, "Fake landlord"),
        (CATEGORY_FAKE_LISTING, "Fake listing"),
        (CATEGORY_DEPOSIT_SCAM, "Deposit scam"),
        (CATEGORY_IMPERSONATION, "Someone impersonating Rooms4You"),
        (CATEGORY_SUSPICIOUS_PAYMENT, "Suspicious payment request"),
        (CATEGORY_TENANT_UNREACHABLE, "Tenant unreachable / went AWOL"),
        (CATEGORY_OTHER, "Other"),
    ]

    STATUS_NEW = "new"
    STATUS_INVESTIGATING = "investigating"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (STATUS_NEW, "New"),
        (STATUS_INVESTIGATING, "Investigating"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    # Who filed it. Nullable so someone who isn't logged in (e.g. a scam
    # victim who never made it to registering) can still report.
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_reports_filed",
    )
    reporter_contact = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Email or phone, for reporters who aren't logged in.",
    )

    # What's being reported. Both optional - a general "Report Fraud"
    # submission may name neither, just a description.
    room = models.ForeignKey(
        "listings.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_reports_against",
    )

    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    detail = models.TextField(
        blank=True,
        default="",
        help_text="What happened - names/numbers used, dates, payment details requested, etc.",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    resolution_note = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_reports_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status"]),
            models.Index(fields=["room"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        target = self.room.title if self.room else (self.reported_user or "general")
        return f"#{self.pk} {self.get_category_display()} — {target} ({self.status})"

    @property
    def reference_code(self) -> str:
        # Human-readable case reference to hand back to the reporter -
        # "we acknowledge receipt" needs something concrete to point at.
        return f"R4Y-{self.pk:06d}"

    @property
    def related_open_reports(self):
        """Other still-open reports against the same room or the same
        reported user - what actually makes a fresh report worth
        escalating ahead of the queue, not just its own category."""
        if not self.pk or not (self.room_id or self.reported_user_id):
            return FraudReport.objects.none()

        condition = models.Q()
        if self.room_id:
            condition |= models.Q(room_id=self.room_id)
        if self.reported_user_id:
            condition |= models.Q(reported_user_id=self.reported_user_id)

        return (
            FraudReport.objects.exclude(pk=self.pk)
            .filter(condition)
            .filter(status__in=(self.STATUS_NEW, self.STATUS_INVESTIGATING))
        )

    @property
    def is_repeat_offender(self) -> bool:
        return self.related_open_reports.exists()

    def mark_status(self, status: str, *, staff_user=None, note: str = ""):
        self.status = status
        if note:
            self.resolution_note = note
        if status in (self.STATUS_RESOLVED, self.STATUS_DISMISSED):
            self.resolved_by = staff_user
            self.resolved_at = timezone.now()
        self.save()

        if status == self.STATUS_RESOLVED and self.reporter_id:
            from accounts.push import notify_user

            notify_user(
                self.reporter,
                title="Your report has been reviewed",
                body=f"Report {self.reference_code} has been resolved by our Trust & Safety team.",
                url="/trust/report-fraud/",
            )
