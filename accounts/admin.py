from django.contrib import admin
from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "status",
        "requested_tier",
        "payment_requested",
        "approved_at",
    )

    list_filter = ("tier", "status", "payment_requested")
    search_fields = ("user__username", "user__email", "payment_reference")

    actions = ["approve_payments", "reject_payments"]

    def approve_payments(self, request, queryset):
        for membership in queryset:
            if membership.requested_tier:
                membership.activate_membership(admin_user=request.user)

        self.message_user(request, "✅ Payments approved and memberships upgraded.")

    approve_payments.short_description = "Approve payment & activate membership"

    def reject_payments(self, request, queryset):
        for membership in queryset:
            membership.reject_payment()

        self.message_user(request, "❌ Payments rejected.")

    reject_payments.short_description = "Reject payments"