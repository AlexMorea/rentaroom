from django.contrib import admin
from .models import Room, Review, RoomImage, Profile


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 1


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = [RoomImageInline]

    list_display = (
        "title",
        "owner",
        "location",
        "price",
        "room_type",
        "is_available",
    )

    list_filter = (
        "room_type",
        "is_available",
        "city",
        "province",
    )

    search_fields = (
        "title",
        "location",
        "owner__username",
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "is_verified_landlord",
        "is_phone_verified",
        "is_email_verified",
    )

    list_filter = (
        "role",
        "is_verified_landlord",
        "is_phone_verified",
        "is_email_verified",
    )

    list_editable = (
        "is_verified_landlord",
    )

    search_fields = (
        "user__username",
        "phone_number",
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "user",
        "rating",
        "created_at",
    )