from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "status",
        "is_founding",
        "trial_end",
        "requested_tier",
        "payment_requested",
        "proof_of_payment",
        "proof_link",
        "approved_at",
    )

    def proof_link(self, obj):
        if obj.proof_of_payment:
            return format_html(
                '<a href="{}" target="_blank">View Proof</a>',
                obj.proof_of_payment.url
            )
        return "-"


    list_filter = (
        "is_founding",
        "status",
        "tier",
        "payment_requested",
    )

    search_fields = (
        "user__username",
        "user__email",
        "payment_reference",
    )

    readonly_fields = (
        "membership_id",
        "payment_reference",
        "approved_at",
        "payment_requested_at",
    )

    fieldsets = (
        ("👤 User", {
            "fields": ("user",)
        }),

        ("📦 Membership", {
            "fields": ("tier", "status", "is_active", "is_trial", "trial_end")
        }),

        ("🏅 Founding Landlord", {
            "fields": ("is_founding", "founding_since")
        }),

        ("💳 Payment Info", {
            "fields": (
                "requested_tier",
                "payment_requested",
                "payment_requested_at",
                "proof_of_payment",
                "payment_reference",
            )
        }),

        ("✅ Approval", {
            "fields": ("approved_by", "approved_at")
        }),
    )

    actions = (
        "enrol_founding_landlords",
        "approve_memberships",
        "reject_memberships",
    )

    # 🏅 FOUNDING LANDLORD
    @admin.action(description="Enrol as Founding Landlord (Gold free + first tenant free)")
    def enrol_founding_landlords(self, request, queryset):
        enrolled, skipped = 0, []

        for membership in queryset.select_related("user"):
            if membership.enrol_as_founding():
                enrolled += 1
            else:
                skipped.append(membership.user.username)

        self.message_user(request, f"🏅 {enrolled} membership(s) enrolled as Founding Landlords.")
        if skipped:
            self.message_user(
                request,
                "Skipped (suspended account or payment under review): " + ", ".join(skipped),
                messages.WARNING,
            )

    # ✅ APPROVE (ONE CLICK)
    def approve_memberships(self, request, queryset):
        count = 0

        for membership in queryset:
            if membership.requested_tier:
                membership.activate_membership(admin_user=request.user)
                count += 1

        self.message_user(
            request,
            f"✅ {count} membership(s) approved successfully."
        )

    approve_memberships.short_description = "Approve selected memberships"

    # ❌ REJECT
    def reject_memberships(self, request, queryset):
        count = queryset.count()

        for membership in queryset:
            membership.reject_payment()

        self.message_user(
            request,
            f"❌ {count} payment(s) rejected."
        )

    reject_memberships.short_description = "Reject selected payments"