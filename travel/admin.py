from django.contrib import admin

from .models import (
    TravelRequest,
    TravelItinerary,
    TravelEstimatedExpenseLine,
    TravelRequestNumberSequence,
    TravelRequestAttachment,
    TravelRequestContentAudit,
    TravelActualExpenseLine,
    TravelPerDiemPolicy,
)


@admin.register(TravelPerDiemPolicy)
class TravelPerDiemPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_code",
        "policy_name",
        "department",
        "currency",
        "daily_amount",
        "effective_from",
        "effective_to",
        "is_active",
    )
    list_filter = ("currency", "department", "is_active")
    search_fields = ("policy_code", "policy_name", "department__dept_code", "department__dept_name")


class TravelItineraryInline(admin.TabularInline):
    model = TravelItinerary
    extra = 1


class TravelEstimatedExpenseLineInline(admin.TabularInline):
    model = TravelEstimatedExpenseLine
    extra = 1
    exclude = ("location_mode", "nights")
    readonly_fields = ("nights",)


@admin.register(TravelRequest)
class TravelRequestAdmin(admin.ModelAdmin):
    list_display = (
        "travel_no",
        "purpose",
        "requester",
        "request_department",
        "project",
        "status",
        "start_date",
        "end_date",
        "estimated_total",
        "actual_total",
    )
    search_fields = (
        "travel_no",
        "purpose",
        "origin_city",
        "destination_city",
        "requester__username",
        "requester__display_name",
        "request_department__dept_code",
        "request_department__dept_name",
        "project__project_code",
        "project__project_name",
    )
    list_filter = (
        "status",
        "request_department",
        "project",
        "start_date",
        "end_date",
    )
    readonly_fields = (
        "travel_no",
        "estimated_total",
    )
    inlines = [TravelItineraryInline, TravelEstimatedExpenseLineInline]


@admin.register(TravelItinerary)
class TravelItineraryAdmin(admin.ModelAdmin):
    list_display = (
        "travel_request",
        "line_no",
        "trip_date",
        "from_city",
        "to_city",
        "transport_type",
        "departure_time",
        "arrival_time",
    )
    search_fields = (
        "travel_request__travel_no",
        "travel_request__purpose",
        "from_city",
        "to_city",
    )
    list_filter = (
        "transport_type",
        "trip_date",
    )


@admin.register(TravelEstimatedExpenseLine)
class TravelEstimatedExpenseLineAdmin(admin.ModelAdmin):
    list_display = (
        "travel_request",
        "line_no",
        "expense_type",
        "location_mode",
        "expense_date",
        "estimated_amount",
        "currency",
        "over_limit_flag",
    )
    search_fields = (
        "travel_request__travel_no",
        "travel_request__purpose",
        "expense_location",
        "from_location",
        "to_location",
        "notes",
    )
    list_filter = (
        "expense_type",
        "location_mode",
        "currency",
        "over_limit_flag",
        "receipt_required_flag",
    )
    exclude = ("location_mode",)
    readonly_fields = ("nights",)


@admin.register(TravelRequestNumberSequence)
class TravelRequestNumberSequenceAdmin(admin.ModelAdmin):
    list_display = (
        "sequence_date",
        "last_number",
    )
    ordering = ("-sequence_date",)

@admin.register(TravelRequestAttachment)
class TravelRequestAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "travel_request",
        "document_type",
        "title",
        "uploaded_by",
        "uploaded_at",
    )
    search_fields = (
        "travel_request__travel_no",
        "travel_request__purpose",
        "title",
        "uploaded_by__username",
        "uploaded_by__display_name",
    )
    list_filter = (
        "document_type",
        "uploaded_at",
    )

@admin.register(TravelRequestContentAudit)
class TravelRequestContentAuditAdmin(admin.ModelAdmin):
    list_display = (
        "travel_request",
        "action_type",
        "section",
        "field_name",
        "line_no",
        "changed_by",
        "changed_at",
    )
    search_fields = (
        "travel_request__travel_no",
        "travel_request__purpose",
        "section",
        "field_name",
        "old_value",
        "new_value",
        "notes",
        "changed_by__username",
        "changed_by__display_name",
    )
    list_filter = (
        "action_type",
        "section",
        "changed_at",
    )

@admin.register(TravelActualExpenseLine)
class TravelActualExpenseLineAdmin(admin.ModelAdmin):
    list_display = (
        "travel_request",
        "line_no",
        "expense_type",
        "expense_date",
        "actual_amount",
        "currency",
        "estimated_expense_line",
        "purchase_request_line",
        "vendor_name",
        "reference_no",
        "created_by",
        "created_at",
    )
    search_fields = (
        "travel_request__travel_no",
        "travel_request__purpose",
        "vendor_name",
        "reference_no",
        "expense_location",
        "notes",
    )
    list_filter = (
        "expense_type",
        "currency",
        "expense_date",
        "created_at",
    )
    readonly_fields = (
        "travel_request",
        "line_no",
        "expense_type",
        "expense_date",
        "actual_amount",
        "currency",
        "estimated_expense_line",
        "purchase_request_line",
        "vendor_name",
        "reference_no",
        "expense_location",
        "notes",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
