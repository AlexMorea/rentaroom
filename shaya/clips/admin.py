from django.contrib import admin

from .models import (
    AdCampaign,
    Comment,
    CreatorProfile,
    Earning,
    FundTopUp,
    Payout,
    PayoutPeriod,
    Report,
    Video,
)


@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "province", "id_verified", "payout_shap_id"]
    list_filter = ["id_verified", "province", "language"]
    search_fields = ["user__username", "display_name"]


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ["id", "creator", "caption", "language", "is_removed", "created_at"]
    list_filter = ["is_removed", "language", "province"]
    search_fields = ["caption", "creator__username"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["video", "reason", "resolved", "created_at"]
    list_filter = ["resolved", "reason"]
    actions = ["remove_video"]

    @admin.action(description="Remove reported video and resolve")
    def remove_video(self, request, queryset):
        for report in queryset.select_related("video"):
            report.video.is_removed = True
            report.video.save(update_fields=["is_removed"])
        queryset.update(resolved=True)


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = ["advertiser", "cpm_cents", "budget_cents", "spent_millicents", "active"]


@admin.register(PayoutPeriod)
class PayoutPeriodAdmin(admin.ModelAdmin):
    list_display = ["month", "ad_revenue_cents", "top_up_cents", "creator_pool_cents", "paid_views", "closed_at"]


admin.site.register([Comment, FundTopUp, Earning, Payout])
