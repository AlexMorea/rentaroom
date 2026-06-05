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


@admin.register(BakkieDriver)
class BakkieDriverAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "full_name",
        "email",
        "phone_number",
        "vehicle_type",
        "city",
        "application_status",
        "is_verified",
        "terms_accepted",
        "created_at",
    )

    list_filter = (
        "application_status",
        "is_verified",
        "vehicle_type",
        "terms_accepted",
        "created_at",
    )

    search_fields = (
        "full_name",
        "email",
        "phone_number",
        "vehicle_registration",
        "city",
    )

    readonly_fields = (
        "created_at",
        "verified_at",
        "terms_accepted_at",
        "privacy_accepted_at",
    )

    list_editable = (
        "application_status",
        "is_verified",
    )

    def save_model(self, request, obj, form, change):

        if obj.is_verified and not obj.verified_at:
            obj.verified_at = timezone.now()

        if obj.application_status == "approved":
            obj.is_verified = True

        super().save_model(request, obj, form, change)

        if obj.user:
            profile = obj.user.profile
            profile.role = "driver"
            profile.is_verified = obj.is_verified
            profile.is_phone_verified = True
            profile.is_email_verified = True
            profile.save()
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