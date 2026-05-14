from django.contrib import admin
from django.contrib.auth.models import User

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
        "user",
        "vehicle_type",
        "city",
        "is_verified",
    )

    list_filter = (
        "vehicle_type",
        "is_verified",
    )

    list_editable = (
        "is_verified",
    )

    def save_model(self, request, obj, form, change):

        super().save_model(
            request,
            obj,
            form,
            change
        )

        # only create account once approved
        if obj.is_verified and not obj.user:

            username = obj.phone_number.replace("+", "")

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@driver.rooms4you.co.za"
                }
            )

            if created:
                user.set_password("ChangeMe123!")
                user.save()

            obj.user = user
            obj.save()

        if obj.user:
            profile = obj.user.profile
            profile.role = "driver"
            profile.is_verified = True
            profile.is_phone_verified = True
            profile.is_email_verified = True
            profile.save()