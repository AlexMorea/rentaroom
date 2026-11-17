from django.contrib import admin, messages

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "status",
        "is_founding",
        "trial_end",
        "paid_until",
        "auto_renew",
    )


    list_filter = (
        "is_founding",
        "status",
        "tier",
        "auto_renew",
    )

    search_fields = (
        "user__username",
        "user__email",
        "payment_reference",
    )

    readonly_fields = (
        "membership_id",
        "payment_reference",
        "payfast_token",
    )

    fieldsets = (
        ("👤 User", {
            "fields": ("user",)
        }),

        ("📦 Plan", {
            "fields": ("tier", "status", "is_active", "is_trial", "trial_end")
        }),

        ("💳 Pro billing (PayFast)", {
            "fields": ("paid_until", "pro_band", "billing_cycle", "auto_renew", "payfast_token", "payment_reference")
        }),

        ("🏅 Founding Landlord", {
            "fields": ("is_founding", "founding_since", "founding_discount_percent")
        }),
    )

    actions = (
        "enrol_founding_landlords",
        "grant_one_month_pro",
    )

    # 🏅 FOUNDING LANDLORD
    @admin.action(description="Enrol as Founding Landlord (Pro free until programme date + 50%% off for life)")
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
                "Skipped (suspended account): " + ", ".join(skipped),
                messages.WARNING,
            )

    # 🎁 Goodwill / manual comp - e.g. a PayFast payment that needs
    # fixing by hand. Leaves an audit row in billing Payments.
    @admin.action(description="Grant 1 month of Pro (complimentary)")
    def grant_one_month_pro(self, request, queryset):
        from billing.models import Payment
        from billing.pricing import CYCLE_MONTHLY, band_for_rooms, room_count_for

        for membership in queryset.select_related("user"):
            band = band_for_rooms(room_count_for(membership.user))
            membership.extend_pro(band=band.code, cycle=CYCLE_MONTHLY, months=1)
            Payment.objects.create(
                user=membership.user,
                kind=Payment.KIND_PRO,
                status=Payment.STATUS_COMPLETE,
                amount=0,
                item_name="Complimentary Pro (1 month)",
                pro_band=band.code,
                billing_cycle=CYCLE_MONTHLY,
                note=f"Granted by {request.user.username} in admin",
            )
        self.message_user(request, f"🎁 Granted 1 month of Pro to {queryset.count()} landlord(s).")
