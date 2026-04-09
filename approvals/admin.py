from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import (
    ApprovalRule,
    ApprovalRuleStep,
    ApprovalTask,
    ApprovalTaskCandidate,
    ApprovalTaskHistory,
)


@admin.action(description="Claim selected tasks to me")
def claim_selected_tasks(modeladmin, request, queryset):
    success_count = 0

    for task in queryset:
        try:
            task.claim(request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{task}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} task(s) claimed successfully.",
            level=messages.SUCCESS,
        )


@admin.action(description="Release selected tasks back to pool")
def release_selected_tasks(modeladmin, request, queryset):
    success_count = 0

    for task in queryset:
        try:
            task.release_to_pool(request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{task}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} task(s) released back to pool successfully.",
            level=messages.SUCCESS,
        )


@admin.action(description="Approve selected tasks")
def approve_selected_tasks(modeladmin, request, queryset):
    success_count = 0

    for task in queryset:
        try:
            task.approve(request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{task}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} task(s) approved successfully.",
            level=messages.SUCCESS,
        )

@admin.action(description="Return selected tasks to requester")
def return_selected_tasks(modeladmin, request, queryset):
    success_count = 0

    for task in queryset:
        try:
            task.return_to_requester(request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{task}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} task(s) returned to requester successfully.",
            level=messages.SUCCESS,
        )

@admin.action(description="Reject selected tasks")
def reject_selected_tasks(modeladmin, request, queryset):
    success_count = 0

    for task in queryset:
        try:
            task.reject(request.user)
            success_count += 1
        except ValidationError as exc:
            modeladmin.message_user(
                request,
                f"{task}: {'; '.join(exc.messages)}",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} task(s) rejected successfully.",
            level=messages.SUCCESS,
        )


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = (
        "rule_code",
        "rule_name",
        "request_type",
        "department",
        "requester_level",
        "priority",
        "is_active",
    )
    search_fields = (
        "rule_code",
        "rule_name",
        "department__dept_code",
        "department__dept_name",
        "specific_requester__username",
        "specific_requester__display_name",
    )
    list_filter = (
        "request_type",
        "requester_level",
        "is_active",
        "department",
    )
    ordering = ("priority", "rule_code")


@admin.register(ApprovalRuleStep)
class ApprovalRuleStepAdmin(admin.ModelAdmin):
    list_display = (
        "rule",
        "step_no",
        "step_name",
        "approver_type",
        "approver_user",
        "approver_department",
        "approver_level",
        "is_required",
        "is_active",
    )
    search_fields = (
        "rule__rule_code",
        "rule__rule_name",
        "step_name",
        "approver_user__username",
        "approver_user__display_name",
        "approver_department__dept_code",
        "approver_department__dept_name",
    )
    list_filter = (
        "approver_type",
        "approver_level",
        "is_required",
        "is_active",
    )
    ordering = ("rule", "step_no")


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_request",
        "rule",
        "step_no",
        "step_name",
        "assigned_user",
        "status",
        "created_at",
    )
    search_fields = (
        "purchase_request__pr_no",
        "purchase_request__title",
        "rule__rule_code",
        "rule__rule_name",
        "assigned_user__username",
        "assigned_user__display_name",
    )
    list_filter = (
        "status",
        "rule",
        "assigned_user",
    )
    readonly_fields = (
        "purchase_request",
        "rule",
        "step",
        "step_no",
        "step_name",
        "assigned_user",
        "status",
        "acted_by",
        "acted_at",
        "comment",
        "created_at",
    )
    actions = [
        claim_selected_tasks,
        release_selected_tasks,
        approve_selected_tasks,
        return_selected_tasks,
        reject_selected_tasks,
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApprovalTaskCandidate)
class ApprovalTaskCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "user",
        "is_active",
    )
    search_fields = (
        "task__purchase_request__pr_no",
        "task__step_name",
        "user__username",
        "user__display_name",
    )
    list_filter = (
        "is_active",
        "task__status",
    )
    readonly_fields = ("task", "user", "is_active")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApprovalTaskHistory)
class ApprovalTaskHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "action_type",
        "action_by",
        "from_status",
        "to_status",
        "from_assignee",
        "to_assignee",
        "action_at",
    )
    search_fields = (
        "task__purchase_request__pr_no",
        "task__step_name",
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
        "task",
        "action_type",
        "action_by",
        "from_status",
        "to_status",
        "from_assignee",
        "to_assignee",
        "action_at",
        "comment",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False