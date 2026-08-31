import logging
import re
from datetime import timedelta
from typing import ClassVar

from cloudinary import uploader
from cloudinary.models import CloudinaryField
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg
from django.db.models.functions import Lower
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


class Room(models.Model):
    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                Lower("title"),
                Lower("location"),
                "room_type",
                "price",
                "owner",
                name="uniq_room_owner_title_location_type_price",
            )
        ]

        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["is_available"]),
            models.Index(fields=["location"]),
            models.Index(fields=["price"]),
            models.Index(fields=["created_at"]),
            # Composite index to speed up queries that filter by availability
            # and order by materialized score + created_at (used for default ordering)
            models.Index(fields=["is_available", "score", "created_at"], name="room_avail_score_created_idx"),
        ]
        
    ROOM_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("Single Room", "Single Room"),
        ("Shared Room", "Shared Room"),
        ("Bachelor", "Bachelor"),
        ("Ensuite", "Ensuite"),
        ("Student Accommodation", "Student Accommodation"),
        ("Backroom", "Backroom"),
        ("Cottage", "Cottage"),
        ("Apartment", "Apartment")
    ]

    AVAILABILITY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("now", "Available now"),
        ("from", "Occupied (available from)"),
        ("mixed", "Some available now"),
    ]

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rooms")
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)

    # null/blank = no deposit required. A value = the deposit amount in
    # Rand. Deliberately a single nullable field rather than a separate
    # boolean + amount pair, so there's no way for the two to
    # contradict each other (e.g. "no deposit" flag set but an amount
    # still saved).
    deposit_amount = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank if no deposit is required."
    )


    location = models.CharField(max_length=200)
    suburb = models.CharField(max_length=120)
    town = models.CharField(max_length=120)
    city = models.CharField(max_length=120)
    province = models.CharField(
        max_length=120,
        default="Gauteng"
    )

    full_address = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=10)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    room_type = models.CharField(max_length=30, choices=ROOM_TYPES)

    contact_phone = models.CharField(max_length=20)
    contact_whatsapp = models.CharField(max_length=20, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    total_units = models.PositiveIntegerField(default=1)
    available_units = models.PositiveIntegerField(default=1)
    availability_status = models.CharField(
        max_length=10, choices=AVAILABILITY_CHOICES, default="now"
    )
    available_from = models.DateField(null=True, blank=True)

    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # denormalized hit counter (kept small and indexed for fast ordering)
    hits = models.PositiveIntegerField(default=0, db_index=True)
    # materialized composite score (optional performance optimization)
    score = models.PositiveIntegerField(default=0, db_index=True)

    # ----------------- Freshness -----------------
    # When the landlord last actively confirmed this listing is accurate
    # (via the dashboard "Confirm" button, the vacancy toggle, or an
    # emailed one-click link). Defaults to "now" so a newly created room
    # starts its freshness clock at creation, not at some arbitrary
    # earlier date - see flag_stale_listings for what happens once this
    # goes quiet for too long.
    last_confirmed_at = models.DateTimeField(default=timezone.now, db_index=True)
    # When we last sent a "please confirm" nudge, so flag_stale_listings
    # doesn't re-nudge every single day once a room crosses the stale
    # threshold - only after another full LISTING_STALE_DAYS has passed.
    last_nudge_sent_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.total_units < 1:
            raise ValidationError({"total_units": "Total units must be at least 1."})

        if self.available_units > self.total_units:
            raise ValidationError({
                "available_units": "Available units cannot exceed total units."
            })

        if self.availability_status == "from":
            if not self.available_from:
                raise ValidationError({
                    "available_from": "Please set the date it becomes available."
                })

            if self.available_units != 0:
                raise ValidationError({
                    "available_units": "Set available units to 0 for occupied listings."
                })

        if (self.availability_status == "mixed" and
                (self.available_units == 0 or self.available_units == self.total_units)):
            raise ValidationError({
                "available_units": "Must be between 1 and total_units-1."
            })
        
    def save(self, *args, **kwargs):
        if self.availability_status == "from":
            self.available_units = 0
        else:
            self.available_from = None

        self.full_clean()
        super().save(*args, **kwargs)

        
    @property
    def availability_badge_text(self):
        units = f"{self.available_units}/{self.total_units} units"

        if not self.is_available or self.available_units <= 0:
            # Was previously possible to show "0/1 units - Available now",
            # which flatly contradicts itself. Zero vacancy always wins,
            # regardless of what availability_status says.
            return f"{units} • Fully occupied"

        if self.availability_status == "now":
            return f"{units} • Available now"
        if self.availability_status == "from":
            if self.available_from:
                return f"{units} • Available from {self.available_from.strftime('%d %b %Y')}"
            return f"{units} • Available from (date not set)"
        return f"{units} • Some available now"

    @property
    def availability_state(self):
        """Used purely for CSS color-coding on room cards/landlord lists -
        keeps that styling logic out of templates."""
        if not self.is_available or self.available_units <= 0:
            return "occupied"
        if self.availability_status == "from":
            return "upcoming"
        return "available"

    def __str__(self):
        return f"{self.title} ({self.owner.username})"

    @property
    def avg_rating(self):
        """Return average rating for this room or None if no reviews."""
        agg = self.reviews.aggregate(avg=Avg("rating"))
        val = agg.get("avg")
        return float(val) if val is not None else None

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def contact_count(self):
        # lightweight contact count (RoomStat preferred for analytics)
        return RoomStat.objects.filter(room=self, stat_type__startswith="contact").count()

    # ----------------- Freshness -----------------
    @property
    def days_since_confirmed(self) -> int:
        return max((timezone.now() - self.last_confirmed_at).days, 0)

    @property
    def is_stale(self) -> bool:
        """A listing claiming to be available that nobody has confirmed
        in a while - the exact "looks available, isn't really" problem
        this whole feature exists to catch. A room already marked
        unavailable isn't "stale", it's just correctly occupied."""
        return self.is_available and self.days_since_confirmed >= settings.LISTING_STALE_DAYS

    @property
    def freshness_label(self) -> str:
        """Human-readable freshness signal, shown to tenants (builds
        trust that "available" is current) and landlords (tells them
        exactly what a tenant sees, and whether it's time to confirm)."""
        days = self.days_since_confirmed
        if days == 0:
            return "Confirmed available today"
        if days == 1:
            return "Confirmed available yesterday"
        if days < settings.LISTING_STALE_DAYS:
            return f"Confirmed available {days} days ago"
        return f"Not confirmed in {days} days"

    def confirm_availability(self):
        """Landlord actively vouching this listing is still accurate -
        resets both the staleness clock and the nudge cooldown, so a
        confirmed room won't get nudged again until it's genuinely gone
        quiet for another full LISTING_STALE_DAYS."""
        self.last_confirmed_at = timezone.now()
        self.last_nudge_sent_at = None
        self.save(update_fields=["last_confirmed_at", "last_nudge_sent_at"])

    # ----------------- Completeness -----------------
    # Deliberately computed rather than stored - it only ever needs to be
    # read by the landlord viewing their own dashboard, so there's no
    # ranking/query reason to materialize it like `score`.
    _COMPLETENESS_CHECKS: ClassVar[list[tuple[str, str]]] = [
        ("has_photos", "Add at least 3 photos"),
        ("has_description", "Write a fuller description (30+ words)"),
        ("has_map_pin", "Pin the exact location on the map"),
        ("has_whatsapp", "Add a WhatsApp number so tenants can reach you fast"),
        ("has_precise_address", "Add the full street address"),
    ]

    @property
    def has_photos(self) -> bool:
        return self.images.count() >= 3

    @property
    def has_description(self) -> bool:
        return len((self.description or "").split()) >= 30

    @property
    def has_map_pin(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_whatsapp(self) -> bool:
        return bool(self.contact_whatsapp.strip())

    @property
    def has_precise_address(self) -> bool:
        return len((self.full_address or "").strip()) >= 8

    @property
    def completeness_percent(self) -> int:
        checks = self._COMPLETENESS_CHECKS
        passed = sum(1 for attr, _label in checks if getattr(self, attr))
        return round((passed / len(checks)) * 100)

    @property
    def completeness_missing(self) -> list[str]:
        return [label for attr, label in self._COMPLETENESS_CHECKS if not getattr(self, attr)]


class Review(models.Model):

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["room", "user"],
                name="uniq_review_room_user"
            ),
        )

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rating}⭐ for {self.room.title}"


class Profile(models.Model):
    ROLE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("tenant", "Tenant"),
        ("landlord", "Landlord"),    
    ]

    PERSONA_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("student", "Student"),
        ("worker", "Worker"),
        ("family", "Family"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="tenant")

    pending_email = models.EmailField(blank=True, null=True)
    email_change_token = models.UUIDField(null=True, blank=True)
    # NOTE: despite the name, this is set from the same email-delivered
    # OTP as is_email_verified (see listings/views/auth_views.py -
    # verify_account/confirm_phone_change) - there is no SMS/WhatsApp
    # channel wired up yet (Twilio in this codebase is voice-call-masking
    # only, and isn't funded/configured). Functionally it's real: it
    # means "completed onboarding's OTP step" and correctly gates
    # get_user_state()/evaluate_user_state(). Just don't surface it to
    # users as a distinct "phone verified" trust signal anywhere - it
    # isn't one yet. trust:verification.html already lists real phone
    # verification as "Coming Soon" for exactly this reason.
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # keep old for compatibility
    is_verified = models.BooleanField(default=False)
    is_verified_landlord = models.BooleanField(
    default=False,
    help_text="Admin verified landlord badge"
)

    # tenant persona
    persona = models.CharField(
        max_length=20,
        choices=PERSONA_CHOICES,
        blank=True,
        default="worker",
    )

    country_code = models.CharField(max_length=5, default="+27")
    verification_otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)

    phone_number = models.CharField(max_length=20, blank=True, default="")
    cell_no = models.CharField(max_length=15, null=True, blank=True)
    alt_no = models.CharField(max_length=20, blank=True, default="")

    # address
    home_address = models.CharField(max_length=255, blank=True, default="")
    postal_code = models.CharField(max_length=10, blank=True, default="")

  
    terms_accepted = models.BooleanField(default=False)
    # POPIA COMPLIANCE TRACKING (IMPORTANT)

    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)

    gps_latitude = models.FloatField(null=True, blank=True)
    gps_longitude = models.FloatField(null=True, blank=True)
    gps_accuracy = models.FloatField(null=True, blank=True)  # meters
    gps_captured_at = models.DateTimeField(null=True, blank=True)
    gps_source = models.CharField(
        max_length=20,
        choices=[
            ("self", "Self reported"),
            ("browser", "Browser GPS"),
            ("admin", "Admin verified"),
        ],
        default="self"
    )

    # ----------------- Response time (landlords) -----------------
    # Materialized by compute_response_stats, same pattern as Room.score -
    # computed from real Message threads (median time from a tenant's
    # first message to the landlord's first reply), not self-reported.
    # Null/0 means "not enough measured threads yet", handled by
    # response_time_label below rather than showing a misleading claim
    # off one data point.
    avg_response_minutes = models.PositiveIntegerField(null=True, blank=True)
    response_rate_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    responses_measured = models.PositiveIntegerField(default=0)

    # Below this many measured threads, there isn't enough signal to
    # claim a response-time pattern - one lucky (or unlucky) reply
    # shouldn't earn or cost a landlord a public label.
    MIN_THREADS_FOR_RESPONSE_LABEL: ClassVar[int] = 3

    @property
    def response_time_label(self) -> str | None:
        if self.responses_measured < self.MIN_THREADS_FOR_RESPONSE_LABEL or self.avg_response_minutes is None:
            return None

        minutes = self.avg_response_minutes
        if minutes <= 60:
            return "Usually responds within an hour"
        if minutes <= 60 * 4:
            return "Usually responds within a few hours"
        if minutes <= 60 * 24:
            return "Usually responds within a day"
        if minutes <= 60 * 24 * 3:
            return "Usually responds within a few days"
        return "Response time varies"

    @property
    def is_fast_responder(self) -> bool:
        return (
            self.responses_measured >= self.MIN_THREADS_FOR_RESPONSE_LABEL
            and self.avg_response_minutes is not None
            and self.avg_response_minutes <= 240
            and (self.response_rate_percent or 0) >= 70
        )

    def full_phone(self):
        phone = (self.phone_number or "").strip()

        if not phone:
            return ""

        # remove all junk
        phone = re.sub(r"[^\d]", "", phone)

        # remove country if duplicated
        phone = phone.removeprefix("27")

        # remove leading zero
        phone = phone.removeprefix("0")

        return f"{self.country_code.strip()}{phone}"
        

    def __str__(self):
        display_name = (self.user.first_name or "").strip() or (self.user.email or "").strip()
        return f"{display_name} ({self.role})"
    
    
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

class Contact(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="contacts")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["room", "user"],
                name="uniq_contact_room_user"
            ),
        )

    def __str__(self):
        return f"{self.user} → {self.room.title}"
    
class Message(models.Model):

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=["recipient"]),
            models.Index(fields=["sender"]),
        )

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages"
    )

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_messages"
    )

    body = models.TextField(max_length=1000)

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.recipient}"    

class RoomStat(models.Model):

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            # NOTE: no separate index on "room" alone - Django already
            # creates one automatically for every ForeignKey field.
            models.Index(fields=["stat_type"]),  # used standalone for
                # sitewide totals (e.g. total contacts across all rooms)
            models.Index(fields=["room", "stat_type"], name="roomstat_room_type_idx"),
                # the dominant real pattern - virtually every per-room
                # analytics query filters on both together
        ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    stat_type = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    gps_latitude = models.FloatField(null=True, blank=True)
    gps_longitude = models.FloatField(null=True, blank=True)
    address_confidence_score = models.FloatField(default=0.0)
    is_suspicious = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.stat_type} — {self.room.title}"


class RoomImage(models.Model):
    room = models.ForeignKey(
        "Room",
        related_name="images",
        on_delete=models.CASCADE,
        db_index=True
    )

    image = CloudinaryField("image")

    created_at = models.DateTimeField(auto_now_add=True)

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "created_at")

    def clean(self):

        # HARD LIMIT
        if self.room.images.exclude(pk=self.pk).count() >= 10:
            raise ValidationError("Maximum 10 images allowed per room.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    

    def __str__(self):
        return f"Room {self.room_id} image"
    

@receiver(post_delete, sender=RoomImage)
def delete_room_image(sender, instance, **kwargs):
    # Safely remove the stored image. CloudinaryField may provide a FieldFile
    # with a .delete() method or a CloudinaryResource without it. Handle both.
    if not instance.image:
        return

    # Prefer built-in delete when available (FileField/FieldFile)
    if hasattr(instance.image, "delete"):
        try:
            instance.image.delete(save=False)
            return
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            # fallback to uploader below
            logger.warning("Unable to delete room image through its field: %s", exc)

    # Try to obtain a public_id or name for CloudinaryResource/string
    public_id = None
    if hasattr(instance.image, "public_id") and instance.image.public_id:
        public_id = instance.image.public_id
    elif hasattr(instance.image, "name") and instance.image.name:
        public_id = instance.image.name

    if public_id:
        try:
            uploader.destroy(public_id, invalidate=True, resource_type="image")
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            # best-effort; don't raise during post_delete signal
            logger.warning("Unable to delete room image from Cloudinary: %s", exc)

class Favorite(models.Model):
    # tenant saves (favoured) rooms
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["user", "room"],
                name="uniq_favorite_user_room"
            )
        ]

        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user"]),
            models.Index(fields=["room"]),
        ]

    def __str__(self):
        return f"{self.user.username} ♥ {self.room.title}"

class PhoneOTP(models.Model):
    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user"]),
            models.Index(fields=["phone_number"]),
        ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)

    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=15)
    
    def save(self, *args, **kwargs):
    # Ensure ONLY one active OTP per user
        PhoneOTP.objects.filter(
            user=self.user,
            is_verified=False
        ).exclude(pk=self.pk).delete()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.phone_number} (verified={self.is_verified})"