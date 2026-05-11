from django.contrib import admin

from .models import (
    GuardianSession,
    GuardianLocationPing,
    PanicAlert,
    BakkieDriver,
)


@admin.register(GuardianSession)
class GuardianSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "destination",
        "status",
        "started_at",
    )

    list_filter = ("status",)

    search_fields = (
        "user__username",
        "destination",
    )


@admin.register(GuardianLocationPing)
class GuardianLocationPingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "latitude",
        "longitude",
        "created_at",
    )


@admin.register(PanicAlert)
class PanicAlertAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "resolved",
        "created_at",
    )

    list_filter = ("resolved",)


@admin.register(BakkieDriver)
class BakkieDriverAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "vehicle_type",
        "city",
        "is_verified",
    )

    list_filter = (
        "vehicle_type",
        "is_verified",
    )