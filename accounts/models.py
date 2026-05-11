from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
import uuid
from cloudinary.models import CloudinaryField


class Membership(models.Model):
    TIER_CHOICES = [
        ('starter', 'Starter4You'),
        ('bronze', 'Bronze4You'),
        ('silver', 'Silver4You'),
        ('gold', 'Gold4You'),
    ]

    STATUS_CHOICES = [
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
            self.membership_id = f"R4Y-{uuid.uuid4().hex[:6].upper()}"

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

    def mark_payment_submitted(self, tier, proof_file):
        self.status = "pending"
        self.payment_requested = True
        self.payment_requested_at = timezone.now()
        self.requested_tier = tier
        self.proof_of_payment = proof_file
        self.save()

    def activate_membership(self, admin_user=None):
        if not self.requested_tier:
            return

        self.tier = self.requested_tier
        self.status = "active"
        self.is_active = True

        # CRITICAL FIX
        self.is_trial = False

        self.payment_requested = False
        self.requested_tier = None

        self.approved_by = admin_user
        self.approved_at = timezone.now()

        self.save()

    def reject_payment(self):
        self.status = "suspended"
        self.payment_requested = False
        self.proof_of_payment = None
        self.save()

    @property
    def days_left(self):
        if self.trial_end:
            delta = self.trial_end - timezone.now()
            return max(delta.days, 0)
        return 0