from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from cloudinary.models import CloudinaryField
from django.db.models.functions import Lower
import uuid
import re
from django.utils import timezone
from datetime import timedelta


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

        if self.availability_status != "from":
            self.available_from = None

    def save(self, *args, **kwargs):
        # FIX: no mutation in clean, only in save
        if self.availability_status == "from":
            self.available_units = 0

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
        return f"{self.title} - {self.location}"


class Review(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
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

        return f"{self.country_code}{phone}"
        

    def __str__(self):
        display_name = (self.user.first_name or "").strip() or (self.user.email or "").strip()
        return f"{display_name} ({self.role})"
    
    
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

class Contact(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="contacts")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("room", "user")

    def __str__(self):
        return f"{self.user} → {self.room.title}"

class RoomStat(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    stat_type = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stat_type} — {self.room.title}"


class RoomImage(models.Model):
    room = models.ForeignKey(
        "Room",
        related_name="images",
        on_delete=models.CASCADE
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


class Favorite(models.Model):
    # tenant saves (favoured) rooms
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "room")

    def __str__(self):
        return f"{self.user.username} ♥ {self.room.title}"

class PhoneOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)

    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)
    
    def save(self, *args, **kwargs):
    # Ensure ONLY one active OTP per user
        PhoneOTP.objects.filter(user=self.user).exclude(pk=self.pk).delete()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.phone_number} ({self.otp})"

class EmailVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(hours=24)

    def __str__(self):
        return f"{self.user} - {self.token}"
    
class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    room = models.ForeignKey(Room, on_delete=models.CASCADE)

    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)    