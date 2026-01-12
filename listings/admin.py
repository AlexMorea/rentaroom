from django.contrib import admin
from .models import Room, Review, RoomImage

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
    list_filter = ("location", "room_type", "is_available")
    search_fields = ("title", "location")
