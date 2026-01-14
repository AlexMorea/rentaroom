from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings


class Room(models.Model):
    ROOM_TYPES = [
        ("single", "Single Room"),
        ("shared", "Shared Room"),
        ("flat", "Flat / Apartment"),
    ]

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="rooms", null=True, blank=True
    )
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    location = models.CharField(max_length=200)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)

    # Contacts
    contact_phone = models.CharField(max_length=20)
    contact_whatsapp = models.CharField(max_length=20, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")

    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
