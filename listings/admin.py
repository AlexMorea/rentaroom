from django.contrib import admin
from django.db.models import Count, Q

from accounts.moderation import suspend_account
from trust.models import FraudReport

from .models import Profile, Review, Room, RoomImage

_OPEN_REPORT_STATUSES = (FraudReport.STATUS_NEW, FraudReport.STATUS_INVESTIGATING)


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 1


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = (RoomImageInline,)

    list_display = (
        "title",
        "owner",
        "location",
        "price",
        "room_type",
        "is_available",
        "open_reports_count",
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

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _open_reports=Count(
                "fraud_reports",
                filter=Q(fraud_reports__status__in=_OPEN_REPORT_STATUSES),
                distinct=True,
            )
        )

    @admin.display(description="Open reports", ordering="_open_reports")
    def open_reports_count(self, obj):
        return obj._open_reports


@admin.action(description="Suspend account (deactivate + hide all listings + pause billing)")
def suspend_selected_accounts(modeladmin, request, queryset):
    deactivated = 0
    hidden_total = 0
    for profile in queryset.select_related("user"):
        result = suspend_account(profile.user)
        deactivated += int(result["deactivated"])
        hidden_total += result["hidden_rooms"]

    modeladmin.message_user(
        request,
        f"Suspended {deactivated} account(s); hid {hidden_total} listing(s)."
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "is_verified_landlord",
        "is_phone_verified",
        "is_email_verified",
        "open_reports_count",
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

    actions = (suspend_selected_accounts,)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _open_reports=Count(
                "user__fraud_reports_against",
                filter=Q(user__fraud_reports_against__status__in=_OPEN_REPORT_STATUSES),
                distinct=True,
            )
        )

    @admin.display(description="Open reports", ordering="_open_reports")
    def open_reports_count(self, obj):
        return obj._open_reports


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "room",
        "user",
        "rating",
        "created_at",
    )
    