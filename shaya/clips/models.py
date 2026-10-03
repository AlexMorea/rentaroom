"""Data model for Shaya: clips, social graph, view tracking and creator pay.

Money is always stored as integer cents (ZAR) so payout maths never drifts.
"""
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

# The 12 official languages (SASL became the 12th in 2023).
LANGUAGES = [
    ("en", "English"),
    ("zu", "isiZulu"),
    ("xh", "isiXhosa"),
    ("af", "Afrikaans"),
    ("nso", "Sepedi"),
    ("tn", "Setswana"),
    ("st", "Sesotho"),
    ("ts", "Xitsonga"),
    ("ss", "siSwati"),
    ("ve", "Tshivenda"),
    ("nr", "isiNdebele"),
    ("sasl", "South African Sign Language"),
    ("mix", "Mixed / Kasi taal"),
]

PROVINCES = [
    ("EC", "Eastern Cape"),
    ("FS", "Free State"),
    ("GP", "Gauteng"),
    ("KZN", "KwaZulu-Natal"),
    ("LP", "Limpopo"),
    ("MP", "Mpumalanga"),
    ("NC", "Northern Cape"),
    ("NW", "North West"),
    ("WC", "Western Cape"),
]


class CreatorProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField(max_length=50, blank=True)
    bio = models.CharField(max_length=160, blank=True)
    province = models.CharField(max_length=3, choices=PROVINCES, blank=True)
    language = models.CharField(max_length=4, choices=LANGUAGES, default="en")
    date_of_birth = models.DateField(null=True, blank=True)
    # Set by staff after an SA ID / Smart-ID check (KYC provider in prod).
    id_verified = models.BooleanField(default=False)
    # PayShap ShapID (usually the cellphone number linked to a bank account).
    payout_shap_id = models.CharField(max_length=40, blank=True)
    data_saver = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.display_name or self.user.username

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def can_earn(self):
        """Paid creators must be verified adults with somewhere to send money.

        POPIA treats under-18s as children, so minors can post (with parental
        consent) but cannot enter the payout programme in this MVP.
        """
        return bool(
            self.id_verified
            and self.age is not None
            and self.age >= 18
            and self.payout_shap_id
        )


class Video(models.Model):
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="videos"
    )
    file = models.FileField(upload_to="clips/%Y/%m/")
    data_saver_file = models.FileField(upload_to="clips/lite/%Y/%m/", blank=True)
    caption = models.CharField(max_length=300, blank=True)
    language = models.CharField(max_length=4, choices=LANGUAGES, default="en")
    province = models.CharField(max_length=3, choices=PROVINCES, blank=True)
    is_removed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.creator.username}: {self.caption[:40]}"

    def qualified_view_count(self):
        return self.views.filter(qualified=True).count()

    def is_monetised(self):
        threshold = settings.SHAYA["MONETISE_THRESHOLD_VIEWS"]
        return self.qualified_view_count() >= threshold

    def source_for(self, data_saver):
        if data_saver and self.data_saver_file:
            return self.data_saver_file.url
        return self.file.url


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "video"], name="one_like_per_user")
        ]


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="comments")
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following"
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followers"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"], name="one_follow_per_pair"
            )
        ]


class View(models.Model):
    """One playback. Only `qualified` views are paid.

    viewer_key is a salted hash of the session (or user id), so we can
    de-duplicate without storing raw IPs or device IDs (POPIA minimality).
    """

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="views")
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    viewer_key = models.CharField(max_length=64, db_index=True)
    watch_ms = models.PositiveIntegerField(default=0)
    qualified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class Report(models.Model):
    REASONS = [
        ("abuse", "Harassment or hate speech"),
        ("child", "Child safety"),
        ("sexual", "Sexual content"),
        ("violence", "Violence or self-harm"),
        ("scam", "Scam or fraud"),
        ("copyright", "Stolen content / copyright"),
        ("misinfo", "Harmful misinformation"),
        ("other", "Other"),
    ]
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=12, choices=REASONS)
    details = models.CharField(max_length=500, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AdCampaign(models.Model):
    """A local business pays a CPM to show a sponsored clip in the feed."""

    advertiser = models.CharField(max_length=100)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="campaigns")
    cpm_cents = models.PositiveIntegerField(help_text="Price per 1,000 impressions, in cents")
    budget_cents = models.PositiveIntegerField()
    spent_millicents = models.PositiveBigIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.advertiser} @ R{self.cpm_cents / 100:.2f} CPM"

    @property
    def remaining_cents(self):
        return max(self.budget_cents - self.spent_millicents // 1000, 0)

    @property
    def cost_per_impression_millicents(self):
        # cpm_cents / 1000 impressions, expressed in thousandths of a cent.
        return self.cpm_cents


class AdImpression(models.Model):
    campaign = models.ForeignKey(
        AdCampaign, on_delete=models.CASCADE, related_name="impressions"
    )
    viewer_key = models.CharField(max_length=64)
    # Stored in millicents: a R30 CPM is 3 cents per impression, but a R8.50
    # CPM is 0.85 cents, so whole cents would lose most of the revenue.
    cost_millicents = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class FundTopUp(models.Model):
    """Money added to a month's creator pool from outside ad sales.

    e.g. a sponsor, a telco partnership or a government / SETA grant.
    """

    month = models.DateField(help_text="First day of the month it applies to")
    source = models.CharField(max_length=100)
    amount_cents = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class PayoutPeriod(models.Model):
    month = models.DateField(unique=True, help_text="First day of the month")
    ad_revenue_cents = models.PositiveBigIntegerField(default=0)
    top_up_cents = models.PositiveBigIntegerField(default=0)
    creator_pool_cents = models.PositiveBigIntegerField(default=0)
    paid_views = models.PositiveBigIntegerField(default=0)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return self.month.strftime("%B %Y")

    @property
    def rate_per_1000_cents(self):
        if not self.paid_views:
            return 0
        return self.creator_pool_cents * 1000 // self.paid_views


class Earning(models.Model):
    period = models.ForeignKey(PayoutPeriod, on_delete=models.CASCADE, related_name="earnings")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="earnings"
    )
    paid_views = models.PositiveIntegerField()
    amount_cents = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "creator"], name="one_earning_per_period")
        ]


class Payout(models.Model):
    STATUS = [
        ("pending", "Pending"),
        ("sent", "Sent via PayShap"),
        ("failed", "Failed"),
    ]
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payouts"
    )
    amount_cents = models.PositiveIntegerField()
    shap_id = models.CharField(max_length=40)
    status = models.CharField(max_length=8, choices=STATUS, default="pending")
    reference = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
