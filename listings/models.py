from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError


class Room(models.Model):
    ROOM_TYPES = [
        ("single", "Single Room"),
        ("shared", "Shared Room"),
        ("flat", "Flat / Apartment"),
    ]

    AVAILABILITY_CHOICES = [
        ("now", "Available now"),
        ("from", "Occupied (available from)"),
        ("mixed", "Some available now"),
    ]

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="rooms", null=True, blank=True
    )
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)

    # Public-friendly location (keep it)
    location = models.CharField(max_length=200)

    # ✅ Safety/authenticity (required)
    full_address = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=10)

    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)

    # Contacts
    contact_phone = models.CharField(max_length=20)
    contact_whatsapp = models.CharField(max_length=20, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    # ✅ Units + availability
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
            raise ValidationError({"available_units": "Available units cannot exceed total units."})

        # If occupied-from, must have date and 0 available now
        if self.availability_status == "from":
            if not self.available_from:
                raise ValidationError({"available_from": "Please set the date it becomes available."})
            if self.available_units != 0:
                raise ValidationError({"available_units": "Set available units to 0 for occupied listings."})

        # If mixed, must be between 1 and total-1
        if self.availability_status == "mixed":
            if self.available_units == 0 or self.available_units == self.total_units:
                raise ValidationError({"available_units": "For 'Some available now', set a number between 1 and total_units-1."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def availability_badge_text(self):
        units = f"{self.available_units}/{self.total_units} units"
        if self.availability_status == "now":
            return f"{units} • Available now"
        if self.availability_status == "from":
            if self.available_from:
                return f"{units} • Available from {self.available_from.strftime('%d %b %Y')}"
            return f"{units} • Available from (date not set)"
        # mixed
        if self.available_from:
            return f"{units} • Some available • Next opening {self.available_from.strftime('%d %b %Y')}"
        return f"{units} • Some available"

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

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, role="tenant")


class Contact(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="contacts")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} → {self.room.title}"


class RoomStat(models.Model):
    STAT_CHOICES = [
        ("view", "View"),
        ("contact_phone", "Phone"),
        ("contact_whatsapp", "WhatsApp"),
        ("contact_email", "Email"),
        ("success", "Success"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    stat_type = models.CharField(max_length=20, choices=STAT_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stat_type} — {self.room.title}"


class RoomImage(models.Model):
    room = models.ForeignKey(Room, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="rooms/")

    def __str__(self):
        return f"Image for {self.room.title}"

