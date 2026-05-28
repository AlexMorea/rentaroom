from django.conf import settings
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField


class GuardianSession(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("ended", "Ended"),
        ("panic", "Panic"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guardian_sessions"
    )

    destination = models.CharField(max_length=255)

    emergency_contact_name = models.CharField(max_length=120)

    emergency_contact_phone = models.CharField(max_length=30)

    started_at = models.DateTimeField(default=timezone.now)

    ended_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    latest_latitude = models.FloatField(null=True, blank=True)

    latest_longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} → {self.destination}"


class GuardianLocationPing(models.Model):
    session = models.ForeignKey(
        GuardianSession,
        on_delete=models.CASCADE,
        related_name="pings"
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ping {self.session.id}"


class PanicAlert(models.Model):
    session = models.ForeignKey(
        GuardianSession,
        on_delete=models.CASCADE,
        related_name="alerts"
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"PANIC #{self.id}"


class BakkieDriver(models.Model):
    VEHICLE_CHOICES = (
        ("small", "Small Bakkie"),
        ("medium", "Medium Truck"),
        ("large", "Large Truck"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bakkie_profiles",
        null=True,
        blank=True
    )

    full_name = models.CharField(max_length=120)
    email = models.EmailField(
        unique=True,
        blank=True,
        null=True
    )
    phone_number = models.CharField(max_length=30)

    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_CHOICES
    )

    vehicle_registration = models.CharField(max_length=30)

    licence_image = CloudinaryField(
        "driver_license",
        null=True,
        blank=True
    )

    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    province = models.CharField(max_length=120)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name