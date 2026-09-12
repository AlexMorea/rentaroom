from django.contrib import admin

from accounts.moderation import suspend_account

from .models import FraudReport


@admin.action(description="Mark selected reports as Investigating")
def mark_investigating(modeladmin, request, queryset):
    queryset.update(status=FraudReport.STATUS_INVESTIGATING)


@admin.action(description="Suspend reported user's account and resolve report")
def suspend_reported_user_and_resolve(modeladmin, request, queryset):
    suspended = 0
    for report in queryset:
        if report.reported_user_id:
            suspend_account(report.reported_user)
            suspended += 1
        report.mark_status(
            FraudReport.STATUS_RESOLVED,
            staff_user=request.user,
            note="Account suspended via Trust & Safety admin action.",
        )

    modeladmin.message_user(
        request,
        f"Suspended {suspended} account(s) and resolved {queryset.count()} report(s)."
    )


@admin.action(description="Mark selected reports as Resolved")
def mark_resolved(modeladmin, request, queryset):
    # Looped rather than a bulk .update() so each report goes through
    # mark_status() - that's what pushes the "your report was reviewed"
    # notification to the reporter. Report volume is triage-scale (staff
    # reviewing individual cases), not bulk data migration, so the extra
    # queries here are a non-issue.
    for report in queryset:
        report.mark_status(FraudReport.STATUS_RESOLVED, staff_user=request.user)


@admin.action(description="Dismiss selected reports")
def mark_dismissed(modeladmin, request, queryset):
    for report in queryset:
        report.mark_status(FraudReport.STATUS_DISMISSED, staff_user=request.user)


@admin.register(FraudReport)
class FraudReportAdmin(admin.ModelAdmin):
    list_display = (
        "id", "category", "status", "room", "reported_user",
        "reporter", "created_at",
    )
    list_filter = ("status", "category", "created_at")
    search_fields = (
        "detail", "reporter_contact",
        "room__title", "reported_user__username", "reporter__username",
    )
    autocomplete_fields = ("room", "reported_user", "reporter")
    readonly_fields = ("created_at", "updated_at", "reference_code")
    actions = (mark_investigating, mark_resolved, mark_dismissed, suspend_reported_user_and_resolve)
    date_hierarchy = "created_at"
