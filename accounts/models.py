from typing import ClassVar

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from accounts import founding
from accounts.helpers import generate_membership_id


class Membership(models.Model):
    """
    A landlord's plan. Two tiers:

    - Free: unlimited listings, verification, enquiries, placement
      tracking. Never expires - listing on Rooms4You is free forever.
    - Pro: the paid toolkit (boost credits, ranking lift, and the tools
      added over time), priced by number of rooms - see billing/pricing.py.

    Pro is held either as a free trial (is_trial + trial_end - this is
    how Founding Landlords get Pro free until the programme date) or as
    a paid period (paid_until, extended by each PayFast payment). When
    either runs out, the account drops back to Free; listings stay up.

    status/is_active are Trust & Safety controls only ("suspended" blocks
    new listings) - they no longer have anything to do with payment.
    """

    TIER_FREE = "free"
    TIER_PRO = "pro"

    TIER_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (TIER_FREE, "Free"),
        (TIER_PRO, "Pro"),
    ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("active", "Active"),
        ("pending", "Pending Payment"),  # legacy EFT flow, no longer set
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_FREE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    membership_id = models.CharField(max_length=20, unique=True, blank=True)

    is_active = models.BooleanField(default=True)

    # Pro trial (Founding Landlords: Pro free until the programme date).
    is_trial = models.BooleanField(default=False)
    trial_start = models.DateTimeField(default=timezone.now)
    trial_end = models.DateTimeField(null=True, blank=True)

    # Paid Pro. Extended by each successful PayFast payment.
    paid_until = models.DateTimeField(null=True, blank=True)
    pro_band = models.CharField(max_length=10, blank=True, help_text="Room band paid for (small/medium/large).")
    billing_cycle = models.CharField(max_length=10, blank=True, help_text="monthly or annual.")
    # PayFast subscription token - present while a recurring debit is set up.
    payfast_token = models.CharField(max_length=64, blank=True)
    auto_renew = models.BooleanField(default=False)

    # Founding discount: % off Pro for the first 12 months after the free
    # founding period, while subscribed (see founding_lock_active).
    founding_discount_percent = models.PositiveSmallIntegerField(default=0)

    payment_reference = models.CharField(max_length=50, unique=True, null=True, blank=True)

    # LEGACY: manual EFT + proof-of-payment flow, replaced by PayFast.
    # Kept so historical rows and the staff dashboard still load.
    payment_requested = models.BooleanField(default=False)
    payment_requested_at = models.DateTimeField(null=True, blank=True)
    requested_tier = models.CharField(max_length=20, blank=True, null=True)
    proof_of_payment = CloudinaryField(
        resource_type="auto",
        folder="payments",
        null=True,
        blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_memberships"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # FOUNDING LANDLORD PROGRAMME (see accounts/founding.py)
    is_founding = models.BooleanField(default=False)
    founding_since = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.membership_id:
            self.membership_id = generate_membership_id()

        # Enrolling here rather than at each signup path: memberships are
        # created via get_or_create in half a dozen places (register,
        # Google sign-in, the post_save signal, membership pages).
        if self._state.adding and not self.is_founding and founding.programme_open():
            self.apply_founding()

        if not self.payment_reference:
            self.payment_reference = self.membership_id

        super().save(*args, **kwargs)

    # ---------------------------------------------------------------
    # Plan state
    # ---------------------------------------------------------------
    def is_trial_expired(self):
        return bool(self.is_trial and self.trial_end and timezone.now() > self.trial_end)

    @property
    def on_pro_trial(self) -> bool:
        return self.tier == self.TIER_PRO and self.is_trial and not self.is_trial_expired()

    @property
    def on_paid_pro(self) -> bool:
        return self.tier == self.TIER_PRO and bool(self.paid_until and self.paid_until > timezone.now())

    @property
    def has_pro(self) -> bool:
        if not self.is_active or self.status == "suspended":
            return False
        return self.on_pro_trial or self.on_paid_pro

    @property
    def pro_ends_at(self):
        """When the current Pro access runs out (whichever is later)."""
        ends = [d for d in (self.trial_end if self.on_pro_trial else None, self.paid_until) if d]
        return max(ends) if ends else None

    @property
    def founding_discount_ends_at(self):
        """When the founding discount window closes (None if this
        membership has no founding discount)."""
        if not self.founding_discount_percent:
            return None
        return founding.discount_until()

    @property
    def founding_lock_active(self) -> bool:
        """The founding discount holds for the first
        FOUNDING_DISCOUNT_MONTHS after the free founding period, and ends
        early if a paid Pro period lapses for longer than the grace
        period. Before they ever pay (still on the free founding trial),
        it holds."""
        from billing.pricing import FOUNDING_LOCK_GRACE_DAYS

        if not self.founding_discount_percent:
            return False
        if timezone.now() > founding.discount_until():
            return False
        if self.paid_until is None or self.has_pro:
            return True
        return timezone.now() <= self.paid_until + timezone.timedelta(days=FOUNDING_LOCK_GRACE_DAYS)

    @property
    def current_discount_percent(self) -> int:
        return self.founding_discount_percent if self.founding_lock_active else 0

    def lapse_if_expired(self) -> bool:
        """Drops an expired Pro back to Free. Listings are untouched -
        Free has no listing limit. Returns True if anything changed."""
        if self.tier != self.TIER_PRO or self.on_pro_trial or self.on_paid_pro:
            return False

        self.tier = self.TIER_FREE
        self.is_trial = False
        self.auto_renew = False
        self.save(update_fields=["tier", "is_trial", "auto_renew"])
        return True

    def listing_limit(self):
        """Free and Pro both list without limit."""
        return None

    def can_create_listing(self, current_count=0):
        """Only a Trust & Safety suspension blocks listing now - never
        the plan or a payment."""
        return self.is_active and self.status != "suspended"

    # ---------------------------------------------------------------
    # Pro payments (called from billing.services on a verified PayFast
    # payment notification - never from a browser redirect)
    # ---------------------------------------------------------------
    def extend_pro(self, *, band: str, cycle: str, months: int):
        now = timezone.now()
        # Paying during the free founding trial: the paid period starts
        # when the trial ends, so they don't lose free months.
        start = max(d for d in (now, self.paid_until, self.trial_end if self.on_pro_trial else None) if d)
        self.paid_until = _add_months(start, months)
        self.tier = self.TIER_PRO
        self.pro_band = band
        self.billing_cycle = cycle
        self.save()

    # ---------------------------------------------------------------
    # FOUNDING LANDLORD
    # ---------------------------------------------------------------
    def apply_founding(self):
        """Sets the founding perks on this instance without saving: Pro
        free until the programme date, and the founding price lock. A
        landlord already paying for Pro keeps their paid period as-is
        and gets the badge and price lock only."""
        from billing.pricing import FOUNDING_DISCOUNT_PERCENT

        now = timezone.now()
        self.is_founding = True
        self.founding_since = self.founding_since or now
        self.founding_discount_percent = FOUNDING_DISCOUNT_PERCENT

        if not self.on_paid_pro:
            self.tier = self.TIER_PRO
            self.is_trial = True
            self.trial_end = max(self.trial_end or now, founding.free_until())
            self.is_active = True
            self.status = "active"

    def enrol_as_founding(self):
        """Enrols an existing membership (admin action). Returns False and
        changes nothing for an account suspended by Trust & Safety (login
        deactivated)."""
        if not self.user.is_active:
            return False

        self.apply_founding()
        self.save()
        return True

    def suspend_for_unpaid_placement_fee(self, invoice):
        """
        Only reachable while PLACEMENT_SUCCESS_FEE_ENABLED and
        PLACEMENT_FEE_AUTO_SUSPEND are both on (both default off) - see
        placements/management/commands/flag_overdue_placement_fees.py.
        """
        self.status = "suspended"
        self.is_active = False
        self.save()

    @property
    def days_left(self):
        ends = self.pro_ends_at
        if ends:
            return max((ends - timezone.now()).days, 0)
        return 0


def _add_months(start, months):
    """Calendar months, clamping to the month's last day (31 Jan + 1
    month = 28/29 Feb)."""
    import calendar

    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


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


class TrustedDevice(models.Model):
    """
    One browser/device that has already completed a login-time OTP
    challenge for a given user (see listings/views/auth_views.py -
    user_login/verify_device). A future login that presents this same
    device's cookie skips the challenge; any other device gets asked
    "is this you?" via a fresh emailed OTP before the session is created.

    Only a salted hash of the device token is stored (never the raw
    token itself) - same reasoning as not storing raw passwords: a
    leaked row shouldn't let anyone impersonate the device it names.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trusted_devices",
    )
    token_hash = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["user", "token_hash"],
                name="uniq_trusteddevice_user_token",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"Trusted device for {self.user} ({self.label or 'unknown'})"