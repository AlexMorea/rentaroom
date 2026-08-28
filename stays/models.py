from decimal import Decimal
from typing import ClassVar

from cloudinary.models import CloudinaryField
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class GuestHouse(models.Model):
    """A guest house or BnB listing - nightly rate, not monthly rent like
    Room. Kept as a separate app from listings rather than a Room
    subtype, since the booking mechanics (real calendar dates, conflict
    checking) are different enough that bolting it onto Room would make
    both models worse."""

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["location"]),
            models.Index(fields=["price_per_night"]),
            models.Index(fields=["created_at"]),
        ]

    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guesthouses")

    name = models.CharField(max_length=200)
    description = models.TextField()

    location = models.CharField(max_length=200)
    suburb = models.CharField(max_length=120)
    town = models.CharField(max_length=120)
    city = models.CharField(max_length=120)
    province = models.CharField(max_length=120, default="Gauteng")

    full_address = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=10)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
    max_guests = models.PositiveIntegerField(default=2)
    min_nights = models.PositiveIntegerField(default=1)

    check_in_time = models.TimeField(default="14:00")  # pyright: ignore[reportArgumentType] - Django parses this fine; kept a plain string to match the migration's frozen default and avoid model/migration drift
    check_out_time = models.TimeField(default="10:00")  # pyright: ignore[reportArgumentType]
    house_rules = models.TextField(blank=True, default="")

    has_wifi = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    has_breakfast = models.BooleanField(default=False)
    has_pool = models.BooleanField(default=False)
    has_aircon = models.BooleanField(default=False)
    has_tv = models.BooleanField(default=False)

    contact_phone = models.CharField(max_length=20)
    contact_whatsapp = models.CharField(max_length=20, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.min_nights < 1:
            raise ValidationError({"min_nights": "Minimum stay must be at least 1 night."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.location})"


class GuestHouseImage(models.Model):
    """Mirrors RoomImage exactly, including the reorderable order field,
    so the existing image-manager UI/view patterns can be reused with
    minimal changes."""

    guesthouse = models.ForeignKey(
        GuestHouse,
        related_name="images",
        on_delete=models.CASCADE,
        db_index=True,
    )

    image = CloudinaryField("image")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "created_at")

    def clean(self):
        if self.guesthouse.images.exclude(pk=self.pk).count() >= 15:
            raise ValidationError("Maximum 15 images allowed per guest house.")

    def __str__(self):
        return f"Image for {self.guesthouse.name}"


class Booking(models.Model):
    """A guest's request for specific dates. A request does not block
    other guests from requesting the same dates - see the module-level
    note in stays/availability.py for why, and where the actual
    conflict check happens (at confirmation time, not request time)."""

    STATUS_REQUESTED = "requested"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = (
        (STATUS_REQUESTED, "Requested"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
    )

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["guesthouse", "status"]),
            models.Index(fields=["guest"]),
            models.Index(fields=["check_in", "check_out"]),
        ]

    guesthouse = models.ForeignKey(GuestHouse, on_delete=models.PROTECT, related_name="bookings")
    guest = models.ForeignKey(User, on_delete=models.PROTECT, related_name="bookings_made")

    check_in = models.DateField()
    check_out = models.DateField()
    num_guests = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_REQUESTED)

    message = models.TextField(blank=True, default="")
    decline_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": "Check-out date must be after check-in date."})

        if self.check_in and self.check_in < timezone.localdate():
            raise ValidationError({"check_in": "Check-in date can't be in the past."})

    @property
    def nights(self):
        return (self.check_out - self.check_in).days

    @property
    def total_estimate(self):
        """A rough estimate only - the app never processes payment, so
        this is purely informational for the guest/host to see while
        discussing price, not a binding total."""
        return self.nights * self.guesthouse.price_per_night

    def __str__(self):
        return f"{self.guesthouse.name}: {self.check_in} to {self.check_out} ({self.get_status_display()})"

    SUCCESS_FEE_RATE = Decimal("0.08")
    SUCCESS_FEE_MINIMUM = 50

    @property
    def expected_success_fee(self):
        """8% of the total booking value, with a R50 minimum so even a
        single cheap night still generates a worthwhile fee - mirrors
        Placement.calculate_success_fee's same philosophy for rooms,
        just percentage-based rather than tiered, since guest house
        bookings vary far more widely in total value (a single night
        vs a two-week stay) than monthly room rent does."""
        fee = (self.total_estimate * self.SUCCESS_FEE_RATE).quantize(1)
        return max(fee, self.SUCCESS_FEE_MINIMUM)


class BlockedDate(models.Model):
    """A date range the host has manually blocked - already booked via
    another platform, under maintenance, personal use, etc. Counts
    toward availability conflicts exactly like a confirmed Booking does."""

    class Meta:
        indexes = (
            models.Index(fields=["guesthouse", "start_date", "end_date"]),
        )

    guesthouse = models.ForeignKey(GuestHouse, on_delete=models.CASCADE, related_name="blocked_dates")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after start date."})

    def __str__(self):
        return f"{self.guesthouse.name} blocked {self.start_date} to {self.end_date}"

class BookingInvoice(models.Model):
    """
    The success fee invoice for one confirmed booking. Mirrors
    placements.models.PlacementInvoice's manual reconciliation pattern
    exactly (payment_reference / admin marks paid) rather than
    introducing a new payment gateway integration - same "we never
    touch payment" philosophy the whole app follows.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_WAIVED = "waived"

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_WAIVED, "Waived"),
    ]

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    payment_reference = models.CharField(max_length=50, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    marked_paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stay_invoices_marked_paid",
        help_text="Staff member who confirmed payment.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Invoice R{self.amount} for booking #{self.booking_id} ({self.status})"