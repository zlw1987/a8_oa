from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import (
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestHistory,
    PurchaseRequestAttachment,
    PurchaseRequestContentAudit,
)


@admin.action(description="Submit selected purchase requests")
def submit_requests(modeladmin, request, queryset):
    success_count = 0

    for purchase_request in queryset:
        try:
            purchase_request.submit(acting_user=request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{purchase_request.pr_no}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} purchase request(s) submitted successfully.",
            level=messages.SUCCESS,
        )


@admin.action(description="Cancel selected purchase requests")
def cancel_requests(modeladmin, request, queryset):
    success_count = 0

    for purchase_request in queryset:
        try:
            purchase_request.cancel(acting_user=request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{purchase_request.pr_no}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} purchase request(s) cancelled successfully.",
            level=messages.SUCCESS,
        )


class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1


class PurchaseRequestHistoryInline(admin.TabularInline):
    model = PurchaseRequestHistory
    extra = 0
    can_delete = False
    readonly_fields = (
        "action_at",
        "action_type",
        "from_status",
        "to_status",
        "action_by",
        "comment",
    )
    fields = (
        "action_at",
        "action_type",
        "from_status",
        "to_status",
        "action_by",
        "comment",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "pr_no",
        "title",
        "requester",
        "request_department",
        "project",
        "matched_rule",
        "status",
        "current_step_display",
        "current_approver_display",
        "approval_progress_display",
        "request_date",
        "estimated_total",
    )
    search_fields = (
        "pr_no",
        "title",
        "requester__username",
        "requester__display_name",
        "request_department__dept_code",
        "request_department__dept_name",
        "project__project_code",
        "project__project_name",
        "matched_rule__rule_code",
        "matched_rule__rule_name",
    )
    list_filter = (
        "status",
        "request_department",
        "project",
        "matched_rule",
        "request_date",
    )
    readonly_fields = (
        "pr_no",
        "current_step_display",
        "current_approver_display",
        "approval_progress_display",
    )
    fieldsets = (
        (
            "Request Information",
            {
                "fields": (
                    "pr_no",
                    "title",
                    "requester",
                    "request_department",
                    "project",
                    "status",
                    "matched_rule",
                    "request_date",
                    "needed_by_date",
                    "currency",
                    "estimated_total",
                )
            },
        ),
        (
            "Approval Summary",
            {
                "fields": (
                    "current_step_display",
                    "current_approver_display",
                    "approval_progress_display",
                )
            },
        ),
        (
            "Business Details",
            {
                "fields": (
                    "justification",
                    "vendor_suggestion",
                    "delivery_location",
                    "notes",
                )
            },
        ),
    )
    inlines = [PurchaseRequestLineInline, PurchaseRequestHistoryInline]
    actions = [submit_requests, cancel_requests]

    @admin.display(description="Current Step")
    def current_step_display(self, obj):
        return obj.get_current_step_name()

    @admin.display(description="Current Approver")
    def current_approver_display(self, obj):
        return obj.get_current_approver()

    @admin.display(description="Approval Progress")
    def approval_progress_display(self, obj):
        return obj.get_approval_progress_text()


@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "line_no",
        "item_name",
        "quantity",
        "uom",
        "unit_price",
        "line_amount",
    )
    search_fields = (
        "request__pr_no",
        "item_name",
        "item_description",
    )


@admin.register(PurchaseRequestHistory)
class PurchaseRequestHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_request",
        "action_type",
        "from_status",
        "to_status",
        "action_by",
        "action_at",
    )
    search_fields = (
        "purchase_request__pr_no",
        "purchase_request__title",
        "action_by__username",
        "action_by__display_name",
        "comment",
    )
    list_filter = (
        "action_type",
        "from_status",
        "to_status",
        "action_at",
    )
    readonly_fields = (
        "purchase_request",
        "action_type",
        "from_status",
        "to_status",
        "action_by",
        "action_at",
        "comment",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(PurchaseRequestAttachment)
class PurchaseRequestAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_request",
        "document_type",
        "title",
        "uploaded_by",
        "uploaded_at",
    )
    search_fields = (
        "purchase_request__pr_no",
        "purchase_request__title",
        "title",
        "uploaded_by__username",
        "uploaded_by__display_name",
    )
    list_filter = (
        "document_type",
        "uploaded_at",
    )

@admin.register(PurchaseRequestContentAudit)
class PurchaseRequestContentAuditAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_request",
        "action_type",
        "field_name",
        "line_no",
        "changed_by",
        "changed_at",
    )
    search_fields = (
        "purchase_request__pr_no",
        "purchase_request__title",
        "field_name",
        "old_value",
        "new_value",
        "notes",
        "changed_by__username",
        "changed_by__display_name",
    )
    list_filter = (
        "action_type",
        "changed_at",
    )