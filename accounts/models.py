from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid
from django.contrib.auth.models import User



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

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    upgraded_to = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_memberships"
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='starter')

    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)

    trial_start = models.DateTimeField(default=timezone.now)
    trial_end = models.DateTimeField(null=True, blank=True)

    payment_reference = models.CharField(max_length=50, unique=True, blank=True)
    payment_requested = models.BooleanField(default=False)
    payment_requested_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.payment_reference:
            self.payment_reference = "R4Y-" + str(uuid.uuid4()).split("-")[0].upper()

        if not self.trial_end:
            self.trial_end = self.trial_start + timezone.timedelta(days=30)

        super().save(*args, **kwargs)

    def is_trial_expired(self):
        return timezone.now() > self.trial_end
    
    def listing_limit(self):
        limits = {
            'starter': 2,
            'bronze': 5,
            'silver': 10,
            'gold': None  # unlimited
        }
        return limits.get(self.tier)


    def can_create_listing(self, current_count):
        # 🚫 Block if inactive
        if not self.is_active:
            return False

        # 🚫 Block if trial expired and no payment
        if self.is_trial and self.is_trial_expired():
            return False

        limit = self.listing_limit()

        if limit is None:
            return True

        return current_count < limit
    
    def mark_as_paid(self):
        self.status = "pending"
        self.payment_requested = True
        self.payment_requested_at = timezone.now()
        self.save()

    def activate_membership(self, tier, admin_user=None):
        self.tier = tier
        self.status = "active"
        self.is_active = True
        self.approved_by = admin_user
        self.approved_at = timezone.now()
        self.save()

    def reject_payment(self):
        self.status = "suspended"
        self.payment_requested = False
        self.save()