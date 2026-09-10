from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.push import notify_user
from listings.models import Room
from utils.email import send_template_email
from utils.whatsapp import send_whatsapp_template


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

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
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
    TERMINAL_STATUSES: ClassVar[set[str]] = {STATUS_PAID, STATUS_CANCELLED}

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

    # Set once flag_stalled_placements has nudged both sides that this
    # placement hasn't moved forward in a while. One-time per stall, not
    # re-sent every day - see that command.
    stall_nudge_sent_at = models.DateTimeField(null=True, blank=True)

    # Set when a landlord reports that a moved-in tenant has gone
    # unreachable/vanished (see Placement.flag_tenant_unreachable). Also
    # doubles as the "already reported" guard against duplicate reports.
    tenant_flagged_unreachable_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["tenant", "room"],
                name="uniq_placement_tenant_room",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
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

        if rent <= 1500:
            return Decimal(100)
        elif rent <= 2500:
            return Decimal(150)
        elif rent <= 4000:
            return Decimal(250)
        else:
            return Decimal(350)

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
        self.status = self.STATUS_SUCCESS_FEE_DUE
        self.save()

        PlacementInvoice.objects.get_or_create(
            placement=self,
            defaults={"amount": self.expected_success_fee},
        )

    # ---------------------------------------------------------------
    # Stall detection / tenant-unreachable reporting
    # ---------------------------------------------------------------
    @property
    def current_status_since(self):
        """When this placement last actually changed status, per the
        append-only PlacementStatusHistory audit trail (written by
        signals.py on every real transition) - unlike updated_at, this
        isn't bumped by unrelated saves that don't change status."""
        latest = self.status_history.order_by("-created_at").first()
        return latest.created_at if latest else self.created_at

    @property
    def days_in_current_status(self) -> int:
        return (timezone.now() - self.current_status_since).days

    # Statuses where "nothing has happened in a while" is actually worth
    # nudging someone about - terminal/awaiting-payment/awaiting-review
    # states already have their own dedicated reminders elsewhere.
    STALLABLE_STATUSES: ClassVar[set[str]] = {
        STATUS_INTERESTED,
        STATUS_VIEWING_SCHEDULED,
        STATUS_VIEWING_COMPLETED,
        STATUS_APPROVED,
    }

    def is_stalled(self, threshold_days: int = 7) -> bool:
        return (
            self.status in self.STALLABLE_STATUSES
            and self.days_in_current_status >= threshold_days
        )

    def flag_tenant_unreachable(self, reported_by):
        """
        Landlord-triggered "this tenant has gone AWOL" report. Files a
        FraudReport for staff triage (reusing the existing Trust Centre
        queue rather than a second admin surface) and records the
        timestamp here so the dashboard can show it was reported and the
        view can't double-file it.
        """
        from trust.models import FraudReport

        if self.tenant_flagged_unreachable_at:
            return None

        self.tenant_flagged_unreachable_at = timezone.now()
        self.save(update_fields=["tenant_flagged_unreachable_at"])

        return FraudReport.objects.create(
            reporter=reported_by,
            room=self.room,
            reported_user=self.tenant,
            category=FraudReport.CATEGORY_TENANT_UNREACHABLE,
            detail=(
                f"Landlord reports tenant has gone unreachable/vanished after "
                f"moving into \"{self.room.title}\" (placement #{self.pk})."
            ),
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
        ordering = ("created_at",)
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

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
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
        ordering: ClassVar[list[str]] = ["-created_at"]

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


class Waitlist(models.Model):
    """
    A tenant waiting for a currently-full room to open up.

    The business case: listing is free, so a landlord has no reason to
    take a room down just because it's occupied - if it's got a known
    or expected re-availability (Room.availability_status == "from"),
    keeping it listed and letting interested tenants queue up means the
    room has a ready audience the moment it actually opens, instead of
    starting from zero. It also doubles as a demand signal: a landlord
    (and Rooms4You) can see exactly how many tenants are waiting on a
    given room.

    Either side can start an entry - a tenant joining themselves off the
    room detail page (added_by=tenant), or a landlord adding a tenant
    who's already shown interest, e.g. via the room's Contact/Message/
    Placement history (added_by=landlord). Landlords can't add a tenant
    they have no relationship with - see placements.views.add_to_waitlist.
    """

    STATUS_WAITING = "waiting"
    STATUS_NOTIFIED = "notified"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (STATUS_WAITING, "Waiting"),
        (STATUS_NOTIFIED, "Notified"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    ADDED_BY_TENANT = "tenant"
    ADDED_BY_LANDLORD = "landlord"

    ADDED_BY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (ADDED_BY_TENANT, "Tenant joined themselves"),
        (ADDED_BY_LANDLORD, "Landlord added them"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="waitlist_entries")
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waitlist_entries",
    )
    # Denormalized (same pattern as Placement.landlord) so a landlord's
    # own waitlists can be queried without a join through room.owner.
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_waitlists",
    )

    added_by = models.CharField(max_length=10, choices=ADDED_BY_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_WAITING)
    notified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["created_at"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["tenant", "room"],
                name="uniq_waitlist_tenant_room",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["room", "status"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["landlord", "status"]),
        ]

    def __str__(self):
        return f"{self.tenant} waiting for {self.room.title} ({self.status})"

    @property
    def position(self) -> int:
        """
        1-based queue position among still-waiting entries for this
        room, oldest first - what "prioritized" concretely means here:
        first in line gets notified (and can act) first.
        """
        return Waitlist.objects.filter(
            room_id=self.room_id,
            status=self.STATUS_WAITING,
            created_at__lte=self.created_at,
        ).count()

    @classmethod
    def notify_all_for_room(cls, room: Room) -> int:
        """
        Called once a room transitions from full to having a vacancy
        again (see placements.signals) - notifies every still-waiting
        entry, in queue order, by email and push. Returns how many were
        notified. Entries are marked "notified" rather than deleted, so
        both sides can still see who was waiting once the room re-fills.
        """
        entries = cls.objects.filter(room=room, status=cls.STATUS_WAITING).select_related("tenant")

        notified = 0
        for entry in entries:
            entry.status = cls.STATUS_NOTIFIED
            entry.notified_at = timezone.now()
            entry.save(update_fields=["status", "notified_at"])

            if entry.tenant.email:
                send_template_email(
                    subject=f'"{room.title}" is available again!',
                    to_email=entry.tenant.email,
                    template="emails/waitlist_room_available.html",
                    context={
                        "tenant": entry.tenant,
                        "room": room,
                        "year": timezone.now().year,
                    },
                )

            if hasattr(entry.tenant, "profile"):
                send_whatsapp_template(
                    entry.tenant.profile,
                    settings.WHATSAPP_TEMPLATE_WAITLIST_AVAILABLE,
                    params=[room.title],
                )

            notify_user(
                entry.tenant,
                title="A room you're waiting for is available!",
                body=f'"{room.title}" just opened up - contact the landlord now.',
                url=reverse("room_detail", args=[room.id]),
            )
            notified += 1

        return notified