from django.contrib import admin
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from accounts.moderation import suspend_account
from trust.models import FraudReport

from .models import Profile, Review, Room, RoomImage, ScheduledJobRun

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


def _accounts_on_same_phone():
    """How many profiles share this profile's phone number (0 when it has
    none). One person signing up under several names with one number is a
    known fake-landlord pattern, so staff should see it at a glance."""
    shared = (
        Profile.objects.filter(phone_number=OuterRef("phone_number"))
        .exclude(phone_number="")
        .values("phone_number")
        .annotate(n=Count("pk"))
        .values("n")[:1]
    )
    return Coalesce(Subquery(shared, output_field=IntegerField()), 0)


class SharedPhoneFilter(admin.SimpleListFilter):
    title = "phone shared with other accounts"
    parameter_name = "shared_phone"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(_phone_accounts__gt=1)
        if self.value() == "no":
            return queryset.filter(_phone_accounts__lte=1)
        return queryset


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "is_verified_landlord",
        "is_phone_verified",
        "is_email_verified",
        "open_reports_count",
        "phone_accounts",
    )

    list_filter = (
        SharedPhoneFilter,
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

    readonly_fields = ("other_accounts_on_phone",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _open_reports=Count(
                "user__fraud_reports_against",
                filter=Q(user__fraud_reports_against__status__in=_OPEN_REPORT_STATUSES),
                distinct=True,
            ),
            _phone_accounts=_accounts_on_same_phone(),
        )

    @admin.display(description="Same phone", ordering="_phone_accounts")
    def phone_accounts(self, obj):
        if obj._phone_accounts <= 1:
            return "-"
        url = reverse("admin:listings_profile_changelist") + f"?q={obj.phone_number}"
        return format_html('<a href="{}">⚠️ {} accounts</a>', url, obj._phone_accounts)

    @admin.display(description="Other accounts on this phone number")
    def other_accounts_on_phone(self, obj):
        if not obj.pk or not obj.phone_number:
            return "-"
        others = (
            Profile.objects.filter(phone_number=obj.phone_number)
            .exclude(pk=obj.pk)
            .select_related("user")
        )
        if not others:
            return "None"
        return format_html_join(
            ", ",
            '<a href="{}">{} ({})</a>',
            (
                (reverse("admin:listings_profile_change", args=[p.pk]), p.user.get_full_name() or p.user.username, p.user.email)
                for p in others
            ),
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
    

@admin.register(ScheduledJobRun)
class ScheduledJobRunAdmin(admin.ModelAdmin):
    """Read-only view of when each scheduled job last ran."""

    list_display = ("name", "last_started_at", "last_finished_at", "last_ok")
    readonly_fields = ("name", "last_started_at", "last_finished_at", "last_ok", "last_error")

    def has_add_permission(self, request):
        return False
