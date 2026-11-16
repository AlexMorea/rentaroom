from django.contrib import admin
from django.db.models import Sum

from .models import Boost, Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "status", "amount", "item_name", "pf_payment_id", "completed_at", "created_at")
    list_filter = ("kind", "status", "billing_cycle")
    search_fields = ("user__username", "user__email", "pf_payment_id", "item_name")
    readonly_fields = (
        "user", "kind", "amount", "item_name", "pro_band", "billing_cycle", "discount_percent",
        "room", "boost_option", "parent", "pf_payment_id", "payfast_token", "amount_fee",
        "amount_net", "raw_notification", "completed_at", "created_at",
    )
    date_hierarchy = "created_at"

    def changelist_view(self, request, extra_context=None):
        complete = Payment.objects.filter(status=Payment.STATUS_COMPLETE)
        extra_context = {
            **(extra_context or {}),
            "title": f"Payments - R{complete.aggregate(t=Sum('amount'))['t'] or 0} collected in total",
        }
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Boost)
class BoostAdmin(admin.ModelAdmin):
    list_display = ("room", "landlord", "source", "starts_at", "ends_at", "is_active")
    list_filter = ("source",)
    search_fields = ("room__title", "landlord__username", "landlord__email")
    raw_id_fields = ("room", "landlord", "payment")

    @admin.display(boolean=True)
    def is_active(self, obj):
        return obj.is_active
