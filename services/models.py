from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils import timezone


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

    APPLICATION_STATUS = (
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    AVAILABILITY_CHOICES = (
        ("available", "Available"),
        ("busy", "Busy"),
        ("offline", "Offline"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bakkie_profiles",
        null=True,
        blank=True
    )

    # ================= BASIC INFO =================

    full_name = models.CharField(max_length=120)

    email = models.EmailField(
        unique=True,
        blank=True,
        null=True
    )

    phone_number = models.CharField(max_length=30)

    # ================= VEHICLE =================

    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_CHOICES
    )

    vehicle_registration = models.CharField(max_length=30)

    vehicle_image = CloudinaryField(
        "vehicle_image",
        null=True,
        blank=True
    )

    licence_image = CloudinaryField(
        "driver_license",
        null=True,
        blank=True
    )

    # ================= LOCATION =================

    address = models.CharField(max_length=255)

    city = models.CharField(max_length=120)

    province = models.CharField(max_length=120)

    latitude = models.FloatField(null=True, blank=True)

    longitude = models.FloatField(null=True, blank=True)

    # ================= STATUS =================

    is_verified = models.BooleanField(default=False)

    application_status = models.CharField(
        max_length=20,
        choices=APPLICATION_STATUS,
        default="pending"
    )

    verification_notes = models.TextField(
        blank=True,
        default=""
    )

    verified_at = models.DateTimeField(null=True, blank=True)

    is_online = models.BooleanField(default=False)

    availability_status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default="offline"
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True
    )

    # ================= ANALYTICS =================

    completed_jobs = models.PositiveIntegerField(default=0)

    total_bookings = models.PositiveIntegerField(default=0)

    response_rate = models.PositiveIntegerField(default=100)

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=5.0
    )

    # ================= CONSENT =================

    terms_accepted = models.BooleanField(default=False)

    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    privacy_accepted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # ================= SECURITY =================

    must_change_password = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name
    

class MoveBooking(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    PAYMENT_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="move_bookings"
    )

    driver = models.ForeignKey(
        BakkieDriver,
        on_delete=models.CASCADE,
        related_name="move_bookings"
    )

    pickup_location = models.CharField(max_length=255)

    dropoff_location = models.CharField(max_length=255)

    scheduled_time = models.DateTimeField()

    quoted_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking #{self.id}" 

class EmergencyContact(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="emergency_contacts"
    )

    full_name = models.CharField(max_length=120)

    phone_number = models.CharField(max_length=30)

    relationship = models.CharField(max_length=120)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class EmergencyEvent(models.Model):

    EVENT_CHOICES = (
        ("panic", "Panic"),
        ("manual_checkin", "Manual Check-In"),
        ("session_timeout", "Session Timeout"),
    )

    session = models.ForeignKey(
        GuardianSession,
        on_delete=models.CASCADE,
        related_name="emergency_events"
    )

    event_type = models.CharField(
        max_length=30,
        choices=EVENT_CHOICES
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    is_resolved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} #{self.id}"  


class ServiceAnalyticsEvent(models.Model):

    EVENT_TYPES = (
        ("driver_view", "Driver View"),
        ("booking_created", "Booking Created"),
        ("panic_triggered", "Panic Triggered"),
        ("guardian_started", "Guardian Started"),
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPES
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.event_type         

