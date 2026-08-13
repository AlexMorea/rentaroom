from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from listings.models import Room


class Placement(models.Model):
    """
    A Placement tracks one tenant's journey with one room, from first
    contact through to a confirmed (or disputed) move-in.

    Deliberately kept as its own app rather than bolted onto Room/Contact:
    this is a distinct business process (sales pipeline + billing) with
    its own lifecycle, not just another listing attribute.
    """

    STATUS_INTERESTED = "interested"
    STATUS_VIEWING_SCHEDULED = "viewing_scheduled"
    STATUS_VIEWING_COMPLETED = "viewing_completed"
    STATUS_APPROVED = "approved"
    STATUS_MOVED_IN = "moved_in"
    STATUS_SUCCESS_FEE_DUE = "success_fee_due"
    STATUS_PAID = "paid"
    STATUS_VERIFICATION_REQUIRED = "verification_required"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_INTERESTED, "Interested"),
        (STATUS_VIEWING_SCHEDULED, "Viewing Scheduled"),
        (STATUS_VIEWING_COMPLETED, "Viewing Completed"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_MOVED_IN, "Moved In"),
        (STATUS_SUCCESS_FEE_DUE, "Success Fee Due"),
        (STATUS_PAID, "Paid"),
        (STATUS_VERIFICATION_REQUIRED, "Verification Required"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    # Statuses a staff member/landlord can still freely move between in the
    # normal flow. Cancelled/Paid are treated as terminal in the UI (though
    # staff can still override anything via the admin - see admin.py).
    TERMINAL_STATUSES = {STATUS_PAID, STATUS_CANCELLED}

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="placements_as_tenant",
    )
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="placements_as_landlord",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        related_name="placements",
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_INTERESTED,
    )

    # Set by the landlord as the placement progresses.
    viewing_date = models.DateTimeField(null=True, blank=True)
    move_in_date = models.DateField(null=True, blank=True)

    # Dual move-in confirmation. None = not yet responded.
    tenant_confirmed_move_in = models.BooleanField(null=True, blank=True)
    landlord_confirmed_move_in = models.BooleanField(null=True, blank=True)
    tenant_confirmed_at = models.DateTimeField(null=True, blank=True)
    landlord_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Set once when the move-in check has actually been triggered, so the
    # management command doesn't keep nagging every day forever.
    move_in_check_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "room"],
                name="uniq_placement_tenant_room",
            )
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["landlord", "status"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["move_in_date"]),
        ]

    def __str__(self):
        return f"{self.tenant} → {self.room.title} ({self.get_status_display()})"

    # ---------------------------------------------------------------
    # Success fee calculation
    # ---------------------------------------------------------------
    @staticmethod
    def calculate_success_fee(monthly_rent: Decimal) -> Decimal:
        """
        R800–R1,500   -> R100
        R1,501–R2,500 -> R150
        R2,501–R4,000 -> R250
        Above R4,000  -> R350

        Rent below R800 isn't specified in the brief; we fee it at the
        lowest band rather than charging R0, since every successful
        placement should generate *some* fee. Flag this assumption to
        the business if a room can legitimately rent under R800.
        """
        rent = Decimal(monthly_rent)

        if rent <= Decimal("1500"):
            return Decimal("100")
        elif rent <= Decimal("2500"):
            return Decimal("150")
        elif rent <= Decimal("4000"):
            return Decimal("250")
        else:
            return Decimal("350")

    @property
    def expected_success_fee(self) -> Decimal:
        return self.calculate_success_fee(self.room.price)

    # ---------------------------------------------------------------
    # Move-in confirmation logic
    # ---------------------------------------------------------------
    @property
    def awaiting_move_in_confirmation(self) -> bool:
        return (
            self.move_in_date is not None
            and self.move_in_date <= timezone.localdate()
            and self.status not in self.TERMINAL_STATUSES
            and self.status != self.STATUS_VERIFICATION_REQUIRED
        )

    def confirm_move_in(self, *, as_tenant: bool, confirmed: bool):
        """
        Records one side's answer to "did the tenant move in?" and, once
        both sides have responded, resolves the placement:
          - both True  -> Moved In (then Success Fee Due, fee generated)
          - disagree   -> Verification Required
        Does nothing (and returns) if the other side hasn't answered yet.
        """
        now = timezone.now()

        if as_tenant:
            self.tenant_confirmed_move_in = confirmed
            self.tenant_confirmed_at = now
        else:
            self.landlord_confirmed_move_in = confirmed
            self.landlord_confirmed_at = now

        if self.tenant_confirmed_move_in is None or self.landlord_confirmed_move_in is None:
            # Still waiting on the other party.
            self.save(update_fields=[
                "tenant_confirmed_move_in", "landlord_confirmed_move_in",
                "tenant_confirmed_at", "landlord_confirmed_at",
            ])
            return

        if self.tenant_confirmed_move_in and self.landlord_confirmed_move_in:
            self.status = self.STATUS_MOVED_IN
            self.save()
            # Moving straight to Success Fee Due + invoice generation is
            # the "successful placement" outcome from the brief.
            self.mark_success_fee_due()
        else:
            self.status = self.STATUS_VERIFICATION_REQUIRED
            self.save()

    def mark_success_fee_due(self):
        from .models import PlacementInvoice  # local import avoids circularity concerns if this file grows

        self.status = self.STATUS_SUCCESS_FEE_DUE
        self.save()

        PlacementInvoice.objects.get_or_create(
            placement=self,
            defaults={"amount": self.expected_success_fee},
        )


class PlacementStatusHistory(models.Model):
    """
    Append-only audit trail. Written automatically by a signal whenever
    Placement.status changes (see signals.py) - never written to
    directly from views, so it can be trusted as a real history log.
    """

    placement = models.ForeignKey(
        Placement,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Who/what triggered this change. Null = system (signal/management command).",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "Placement status history"

    def __str__(self):
        return f"{self.placement_id}: {self.from_status or '—'} → {self.to_status}"


class PlacementInvoice(models.Model):
    """
    The Success Fee invoice for one placement. Mirrors the manual
    reconciliation pattern already used by accounts.models.Membership
    (payment_reference / payment_requested / admin marks paid) rather
    than introducing a new payment gateway integration.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_WAIVED = "waived"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_WAIVED, "Waived"),
    ]

    placement = models.OneToOneField(
        Placement,
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    payment_reference = models.CharField(max_length=50, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    marked_paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_marked_paid",
        help_text="Staff member who confirmed payment.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice R{self.amount} for placement #{self.placement_id} ({self.status})"

    def mark_paid(self, staff_user):
        self.status = self.STATUS_PAID
        self.paid_at = timezone.now()
        self.marked_paid_by = staff_user
        self.save()

        self.placement.status = Placement.STATUS_PAID
        self.placement.save()

    @property
    def days_pending(self) -> int:
        if self.status != self.STATUS_PENDING:
            return 0
        return (timezone.now() - self.created_at).days

    def is_overdue(self, grace_period_days: int) -> bool:
        return self.status == self.STATUS_PENDING and self.days_pending >= grace_period_days
