from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from cloudinary.models import CloudinaryField
from cloudinary import uploader
from django.db.models.functions import Lower
import re
from django.utils import timezone
from datetime import timedelta
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg


class Room(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("title"),
                Lower("location"),
                "room_type",
                "price",
                "owner",
                name="uniq_room_owner_title_location_type_price",
            )
        ]

        indexes = [
            models.Index(fields=["is_available"]),
            models.Index(fields=["location"]),
            models.Index(fields=["price"]),
            models.Index(fields=["created_at"]),
            # Composite index to speed up queries that filter by availability
            # and order by materialized score + created_at (used for default ordering)
            models.Index(fields=["is_available", "score", "created_at"], name="room_avail_score_created_idx"),
        ]
        
    ROOM_TYPES = [
        ("Single Room", "Single Room"),
        ("Shared Room", "Shared Room"),
        ("Bachelor", "Bachelor"),
        ("Ensuite", "Ensuite"),
        ("Student Accommodation", "Student Accommodation"),
        ("Backroom", "Backroom"),
        ("Cottage", "Cottage"),
        ("Apartment", "Apartment")
    ]

    AVAILABILITY_CHOICES = [
        ("now", "Available now"),
        ("from", "Occupied (available from)"),
        ("mixed", "Some available now"),
    ]

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rooms")
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)

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

        if self.availability_status == "mixed":
            if self.available_units == 0 or self.available_units == self.total_units:
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
        if self.availability_status == "now":
            return f"{units} • Available now"
        if self.availability_status == "from":
            if self.available_from:
                return f"{units} • Available from {self.available_from.strftime('%d %b %Y')}"
            return f"{units} • Available from (date not set)"
        return f"{units} • Some available now"

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


class Review(models.Model):

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="uniq_review_room_user"
            )
        ]

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
    ROLE_CHOICES = [
        ("tenant", "Tenant"),
        ("landlord", "Landlord"),    
    ]

    PERSONA_CHOICES = [
        ("student", "Student"),
        ("worker", "Worker"),
        ("family", "Family"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="tenant")

    pending_email = models.EmailField(blank=True, null=True) 
    email_change_token = models.UUIDField(null=True, blank=True) 
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

    def full_phone(self):
        phone = (self.phone_number or "").strip()

        if not phone:
            return ""

        # remove all junk
        phone = re.sub(r"[^\d]", "", phone)

        # remove country if duplicated
        if phone.startswith("27"):
            phone = phone[2:]

        # remove leading zero
        if phone.startswith("0"):
            phone = phone[1:]

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
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="uniq_contact_room_user"
            )
        ]

    def __str__(self):
        return f"{self.user} → {self.room.title}"
    
class Message(models.Model):

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient"]),
            models.Index(fields=["sender"]),
        ]

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
        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["stat_type"]),
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

    class Meta:
        ordering = ["created_at"]

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
    try:
        if not instance.image:
            return

        # Prefer built-in delete when available (FileField/FieldFile)
        if hasattr(instance.image, "delete"):
            try:
                instance.image.delete(save=False)
                return
            except Exception:
                # fallback to uploader below
                pass

        # Try to obtain a public_id or name for CloudinaryResource/string
        public_id = None
        if hasattr(instance.image, "public_id") and instance.image.public_id:
            public_id = instance.image.public_id
        elif hasattr(instance.image, "name") and instance.image.name:
            public_id = instance.image.name

        if public_id:
            try:
                uploader.destroy(public_id, invalidate=True, resource_type="image")
            except Exception:
                # best-effort; don't raise during post_delete signal
                pass
    except Exception:
        # Swallow any unexpected errors in the signal handler
        pass

class Favorite(models.Model):
    # tenant saves (favoured) rooms
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "room"],
                name="uniq_favorite_user_room"
            )
        ]

        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["room"]),
        ]

    def __str__(self):
        return f"{self.user.username} ♥ {self.room.title}"

class PhoneOTP(models.Model):
    class Meta:
        indexes = [
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