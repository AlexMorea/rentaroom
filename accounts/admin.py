from django.contrib import admin
from django.utils.html import format_html

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "status",
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
            "fields": ("tier", "status", "is_active", "is_trial")
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
        "approve_memberships",
        "reject_memberships",
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