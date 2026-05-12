from django.contrib import admin
from .models import Room, Review, RoomImage, Profile


admin.site.register(Review)


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 1


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = [RoomImageInline]

    list_display = (
        "title",
        "location",
        "price",
        "room_type",
        "is_available",
        "contact_phone",
    )

    list_filter = (
        "location",
        "room_type",
        "is_available",
    )

    search_fields = (
        "title",
        "location",
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "is_verified_landlord",
    )

    list_filter = (
        "role",
        "is_verified_landlord",
    )

    list_editable = (
        "is_verified_landlord",
    )