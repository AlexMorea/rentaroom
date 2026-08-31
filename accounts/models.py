from typing import ClassVar

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from accounts.helpers import generate_membership_id


class Membership(models.Model):
    TIER_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ('starter', 'Starter4You'),
        ('bronze', 'Bronze4You'),
        ('silver', 'Silver4You'),
        ('gold', 'Gold4You'),
    ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("active", "Active"),
        ("pending", "Pending Payment"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='starter')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    membership_id = models.CharField(max_length=20, unique=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)

    trial_start = models.DateTimeField(default=timezone.now)
    trial_end = models.DateTimeField(null=True, blank=True)

    payment_reference = models.CharField(max_length=50, unique=True, null=True, blank=True)

    # NEW: PAYMENT FLOW
    payment_requested = models.BooleanField(default=False)
    payment_requested_at = models.DateTimeField(null=True, blank=True)
    requested_tier = models.CharField(max_length=20, blank=True, null=True)

    # PROOF OF PAYMENT
    proof_of_payment = CloudinaryField(
    resource_type="auto",
    folder="payments",
    null=True,
    blank=True
)
    # ADMIN APPROVAL
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_memberships"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.membership_id:
            self.membership_id = generate_membership_id()

        if not self.trial_end:
            self.trial_end = self.trial_start + timezone.timedelta(days=30)

        if not self.payment_reference:
            self.payment_reference = self.membership_id

        super().save(*args, **kwargs)

    def is_trial_expired(self):
        return self.trial_end and timezone.now() > self.trial_end

    def listing_limit(self):
        return {
            'starter': 2,
            'bronze': 5,
            'silver': 10,
            'gold': None
        }.get(self.tier)

    def can_create_listing(self, current_count):
        # inactive users blocked
        if not self.is_active:
            return False

        # trial expired → must pay
        if self.is_trial and self.is_trial_expired():
            return False

        # payment pending → block abuse
        if self.status == "pending":
            return False

        limit = self.listing_limit()

        # unlimited
        if limit is None:
            return True

        return current_count < limit

    # PAYMENT FLOW METHODS

    def reject_payment(self):
            self.status = "suspended"
            self.payment_requested = False

            if self.proof_of_payment:
                self.proof_of_payment.delete(save=False)

            self.proof_of_payment = None
            self.save()


    def mark_payment_submitted(self, tier, proof_file):
        self.status = "pending"
        self.payment_requested = True
        self.payment_requested_at = timezone.now()
        self.requested_tier = tier
        self.proof_of_payment = proof_file
        self.save()

    def activate_membership(self, tier=None, admin_user=None):
        if tier:
            self.requested_tier = tier

        if not self.requested_tier:
            return

        self.tier = self.requested_tier
        self.status = "active"
        self.is_active = True
        self.is_trial = False

        self.payment_requested = False
        self.requested_tier = None

        self.approved_by = admin_user
        self.approved_at = timezone.now()

        self.save()

    def suspend_for_unpaid_placement_fee(self, invoice):
        """
        Reuses the same suspension mechanism as reject_payment() (status
        + is_active), rather than inventing separate suspension logic
        for placement fees. can_create_listing() already blocks new
        listings once is_active is False - existing listings are left
        untouched (not deleted), and the landlord regains access as
        soon as an admin marks the invoice paid and reactivates them.

        Deliberately NOT called automatically from anywhere yet - see
        placements/management/commands/flag_overdue_placement_fees.py,
        which is gated behind settings.PLACEMENT_FEE_AUTO_SUSPEND
        (defaults to False) so this can't start suspending real
        landlord accounts without a conscious decision to turn it on.
        """
        self.status = "suspended"
        self.is_active = False
        self.save()

    @property
    def days_left(self):
        if self.trial_end:
            delta = self.trial_end - timezone.now()
            return max(delta.days, 0)
        return 0


class PushSubscription(models.Model):
    """
    One browser/device's Web Push subscription for one user. A user can
    have several (phone + laptop, or after reinstalling the PWA), which
    is why this isn't a OneToOneField - accounts.push.notify_user() just
    sends to all of them.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )

    # The PushSubscription object's fields, straight from the browser's
    # pushManager.subscribe() call - endpoint is unique per
    # browser+device+site, so it doubles as a natural dedupe key.
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)

    user_agent = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"Push subscription for {self.user} ({self.endpoint[:40]}...)"