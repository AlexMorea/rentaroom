from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from listings.models import Room


class Payment(models.Model):
    """
    One PayFast transaction (or a staff comp, amount 0). Created as
    "pending" when the landlord is sent to checkout, and only ever
    completed by a *verified* PayFast notification (ITN) - never by the
    browser coming back to the return URL, which anyone could fake.

    For a Pro subscription, PayFast sends a fresh ITN for every monthly
    debit with the same m_payment_id; each one is recorded as its own
    Payment row (parent = the original) keyed by pf_payment_id, so a
    re-sent notification can never extend Pro twice.
    """

    KIND_PRO = "pro"
    KIND_BOOST = "boost"
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (KIND_PRO, "Pro subscription"),
        (KIND_BOOST, "Boost"),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETE = "complete"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETE, "Complete"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    item_name = models.CharField(max_length=100)

    # Pro
    pro_band = models.CharField(max_length=10, blank=True)
    billing_cycle = models.CharField(max_length=10, blank=True)
    discount_percent = models.PositiveSmallIntegerField(default=0)

    # Boost
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    boost_option = models.CharField(max_length=10, blank=True)

    # Recurring debits point back at the checkout that set them up.
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="renewals")

    # PayFast
    pf_payment_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    payfast_token = models.CharField(max_length=64, blank=True)
    amount_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount_net = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    raw_notification = models.JSONField(default=dict, blank=True)

    note = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user", "kind", "status"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} R{self.amount} - {self.user} ({self.status})"

    @property
    def m_payment_id(self) -> str:
        """Our reference sent to PayFast (and printed on their receipt)."""
        return f"R4Y-{self.pk}"


class BoostQuerySet(models.QuerySet):
    def active(self, now=None):
        now = now or timezone.now()
        return self.filter(starts_at__lte=now, ends_at__gt=now)


class Boost(models.Model):
    """
    A paid (or Pro-credit) stretch of "Featured" placement for one room.
    Boosts never change Room.score - they're applied at query time in
    the room list (see billing.boosts.featured_room_ids), so the organic
    ranking stays honest and a boost simply stops when it ends.
    """

    SOURCE_PAID = "paid"
    SOURCE_PRO_CREDIT = "pro_credit"
    SOURCE_STAFF = "staff"
    SOURCE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (SOURCE_PAID, "Paid"),
        (SOURCE_PRO_CREDIT, "Pro monthly credit"),
        (SOURCE_STAFF, "Staff / complimentary"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="boosts")
    landlord = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boosts")
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES)
    payment = models.OneToOneField(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="boost")

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BoostQuerySet.as_manager()

    class Meta:
        ordering: ClassVar[list[str]] = ["-starts_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["room", "ends_at"]),
            models.Index(fields=["landlord", "source", "created_at"]),
        ]

    def __str__(self):
        return f"Boost for {self.room} until {self.ends_at:%d %b %Y}"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.starts_at <= now < self.ends_at
