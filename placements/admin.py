from django.contrib import admin, messages
from django.db.models import Count, Sum, Q
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html

from .models import Placement, PlacementStatusHistory, PlacementInvoice


class PlacementStatusHistoryInline(admin.TabularInline):
    model = PlacementStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # History is written only by the signal - staff shouldn't hand-edit it.
        return False


class PlacementInvoiceInline(admin.StackedInline):
    model = PlacementInvoice
    extra = 0
    readonly_fields = ("created_at", "updated_at", "marked_paid_by", "paid_at")


@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "landlord",
        "room",
        "status_badge",
        "viewing_date",
        "move_in_date",
        "verification_flag",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "tenant__username", "tenant__email",
        "landlord__username", "landlord__email",
        "room__title",
    )
    autocomplete_fields = ("tenant", "landlord", "room")
    readonly_fields = (
        "created_at", "updated_at",
        "tenant_confirmed_at", "landlord_confirmed_at",
        "move_in_check_sent_at",
    )
    inlines = [PlacementStatusHistoryInline, PlacementInvoiceInline]

    actions = [
        "override_to_viewing_scheduled",
        "override_to_approved",
        "override_to_cancelled",
        "resolve_dispute_as_successful",
        "resolve_dispute_as_cancelled",
    ]

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            Placement.STATUS_INTERESTED: "#64748b",
            Placement.STATUS_VIEWING_SCHEDULED: "#2563eb",
            Placement.STATUS_VIEWING_COMPLETED: "#0891b2",
            Placement.STATUS_APPROVED: "#16a34a",
            Placement.STATUS_MOVED_IN: "#15803d",
            Placement.STATUS_SUCCESS_FEE_DUE: "#f59e0b",
            Placement.STATUS_PAID: "#059669",
            Placement.STATUS_VERIFICATION_REQUIRED: "#dc2626",
            Placement.STATUS_CANCELLED: "#6b7280",
        }
        color = colors.get(obj.status, "#334155")
        return format_html(
            '<span style="background:{}22;color:{};padding:3px 10px;'
            'border-radius:999px;font-weight:700;font-size:12px;">{}</span>',
            color, color, obj.get_status_display(),
        )

    @admin.display(description="Dispute?", boolean=True)
    def verification_flag(self, obj):
        return obj.status == Placement.STATUS_VERIFICATION_REQUIRED

    # ------------------------------------------------------------------
    # Bulk override actions
    # ------------------------------------------------------------------
    def _bulk_set_status(self, request, queryset, new_status, label):
        updated = 0
        for placement in queryset:
            placement.status = new_status
            placement.save()
            updated += 1
        self.message_user(request, f"{updated} placement(s) set to {label}.", messages.SUCCESS)

    @admin.action(description="Override status → Viewing Scheduled")
    def override_to_viewing_scheduled(self, request, queryset):
        self._bulk_set_status(request, queryset, Placement.STATUS_VIEWING_SCHEDULED, "Viewing Scheduled")

    @admin.action(description="Override status → Approved")
    def override_to_approved(self, request, queryset):
        self._bulk_set_status(request, queryset, Placement.STATUS_APPROVED, "Approved")

    @admin.action(description="Override status → Cancelled")
    def override_to_cancelled(self, request, queryset):
        self._bulk_set_status(request, queryset, Placement.STATUS_CANCELLED, "Cancelled")

    @admin.action(description="Resolve dispute → mark Successful (Moved In)")
    def resolve_dispute_as_successful(self, request, queryset):
        """For placements stuck in Verification Required where staff have
        manually confirmed the tenant did move in."""
        count = 0
        for placement in queryset.filter(status=Placement.STATUS_VERIFICATION_REQUIRED):
            placement.status = Placement.STATUS_MOVED_IN
            placement.save()
            placement.mark_success_fee_due()
            count += 1
        self.message_user(request, f"{count} disputed placement(s) resolved as successful.", messages.SUCCESS)

    @admin.action(description="Resolve dispute → mark Cancelled")
    def resolve_dispute_as_cancelled(self, request, queryset):
        self._bulk_set_status(
            request,
            queryset.filter(status=Placement.STATUS_VERIFICATION_REQUIRED),
            Placement.STATUS_CANCELLED,
            "Cancelled",
        )

    # ------------------------------------------------------------------
    # Analytics view
    # ------------------------------------------------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("analytics/", self.admin_site.admin_view(self.analytics_view), name="placements_analytics"),
        ]
        return custom + urls

    def analytics_view(self, request):
        status_counts = (
            Placement.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )
        status_labels = dict(Placement.STATUS_CHOICES)
        status_counts = [
            {"label": status_labels.get(row["status"], row["status"]), "count": row["count"]}
            for row in status_counts
        ]

        invoice_totals = PlacementInvoice.objects.aggregate(
            total_pending=Sum("amount", filter=Q(status=PlacementInvoice.STATUS_PENDING)),
            total_paid=Sum("amount", filter=Q(status=PlacementInvoice.STATUS_PAID)),
            count_pending=Count("id", filter=Q(status=PlacementInvoice.STATUS_PENDING)),
            count_paid=Count("id", filter=Q(status=PlacementInvoice.STATUS_PAID)),
        )

        disputed_count = Placement.objects.filter(
            status=Placement.STATUS_VERIFICATION_REQUIRED
        ).count()

        context = {
            **self.admin_site.each_context(request),
            "title": "Placement Analytics",
            "status_counts": status_counts,
            "invoice_totals": invoice_totals,
            "disputed_count": disputed_count,
            "total_placements": Placement.objects.count(),
        }
        return TemplateResponse(request, "admin/placements/analytics.html", context)


@admin.register(PlacementInvoice)
class PlacementInvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "placement", "amount", "status", "paid_at", "marked_paid_by")
    list_filter = ("status",)
    search_fields = ("placement__tenant__username", "placement__room__title", "payment_reference")
    readonly_fields = ("created_at", "updated_at")
    actions = ["mark_selected_paid"]

    @admin.action(description="Mark selected invoices as Paid")
    def mark_selected_paid(self, request, queryset):
        count = 0
        for invoice in queryset.exclude(status=PlacementInvoice.STATUS_PAID):
            invoice.mark_paid(request.user)
            count += 1
        self.message_user(request, f"{count} invoice(s) marked as paid.", messages.SUCCESS)


@admin.register(PlacementStatusHistory)
class PlacementStatusHistoryAdmin(admin.ModelAdmin):
    """Read-only audit log browser - staff can inspect but not tamper with history."""
    list_display = ("placement", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    readonly_fields = [f.name for f in PlacementStatusHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
