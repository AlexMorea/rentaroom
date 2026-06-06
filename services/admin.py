from django.contrib import admin
from django.utils import timezone
from .models import MoveBooking, EmergencyEvent, ServiceAnalyticsEvent

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



@admin.register(MoveBooking)
class MoveBookingAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "tenant",
        "driver",
        "status",
        "payment_status",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_status",
    )

@admin.register(EmergencyEvent)
class EmergencyEventAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "event_type",
        "session",
        "is_resolved",
        "created_at",
    )

    list_filter = (
        "event_type",
        "is_resolved",
    )


@admin.register(ServiceAnalyticsEvent)
class ServiceAnalyticsEventAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "event_type",
        "user",
        "created_at",
    )

    list_filter = (
        "event_type",
    )