from django.contrib import admin
from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "is_active",
        "is_trial",
        "payment_requested",
        "payment_reference",
        "trial_end",
    )

    list_filter = ("tier", "is_active", "payment_requested")
    search_fields = ("user__username", "user__email", "payment_reference")

    actions = ["activate_bronze", "activate_silver", "activate_gold", "downgrade_to_starter"]

    def activate_bronze(self, request, queryset):
        for membership in queryset:
            membership.tier = "bronze"
            membership.is_active = True
            membership.is_trial = False
            membership.payment_requested = False
            membership.save()

        self.message_user(request, "Selected users upgraded to Bronze.")

    activate_bronze.short_description = "Activate Bronze4You"

    def activate_silver(self, request, queryset):
        for membership in queryset:
            membership.tier = "silver"
            membership.is_active = True
            membership.is_trial = False
            membership.payment_requested = False
            membership.save()

        self.message_user(request, "Selected users upgraded to Silver.")

    activate_silver.short_description = "Activate Silver4You"

    def activate_gold(self, request, queryset):
        for membership in queryset:
            membership.tier = "gold"
            membership.is_active = True
            membership.is_trial = False
            membership.payment_requested = False
            membership.save()

        self.message_user(request, "Selected users upgraded to Gold.")

    activate_gold.short_description = "Activate Gold4You"

    def downgrade_to_starter(self, request, queryset):
        for membership in queryset:
            membership.tier = "starter"
            membership.is_active = True
            membership.save()

        self.message_user(request, "Selected users downgraded to Starter.")

    downgrade_to_starter.short_description = "Downgrade to Starter4You"