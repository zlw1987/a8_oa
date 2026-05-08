from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from common.approval_constants import POOL_APPROVER_TYPES
from common.choices import ApprovalTaskStatus, RequestType
from .models import (
    ApprovalRule,
    ApprovalTask,
    ApprovalTaskActionType,
    ApprovalTaskCandidate,
)


def get_request_type_for_object(request_obj):
    app_label = request_obj._meta.app_label
    if app_label == "purchase":
        return RequestType.PURCHASE
    if app_label == "travel":
        return RequestType.TRAVEL
    if app_label == "projects":
        return RequestType.PROJECT
    raise ValidationError(f"Unsupported request type for approval: {app_label}.")


def get_request_amount_for_rule_matching(request_obj):
    if hasattr(request_obj, "get_lines_total"):
        return request_obj.get_lines_total()
    if hasattr(request_obj, "refresh_estimated_total"):
        return request_obj.refresh_estimated_total(commit=False)
    return getattr(request_obj, "estimated_total", 0)


def resolve_approval_rule_for_request(request_obj):
    request_type = get_request_type_for_object(request_obj)
    request_department = getattr(request_obj, "request_department", None)
    requester = getattr(request_obj, "requester", None)
    requester_level = getattr(requester, "approval_level", "") if requester else ""
    request_amount = get_request_amount_for_rule_matching(request_obj)

    base_queryset = ApprovalRule.objects.filter(
        is_active=True,
        request_type=request_type,
    )

    matched_rule = (
        base_queryset.filter(is_general_fallback=False)
        .filter(Q(department=request_department) | Q(department__isnull=True))
        .filter(Q(amount_from__isnull=True) | Q(amount_from__lte=request_amount))
        .filter(Q(amount_to__isnull=True) | Q(amount_to__gte=request_amount))
        .filter(Q(requester_level="") | Q(requester_level=requester_level))
        .filter(Q(specific_requester__isnull=True) | Q(specific_requester=requester))
        .order_by("priority", "rule_code", "id")
        .first()
    )

    if matched_rule:
        return matched_rule

    return (
        base_queryset.filter(is_general_fallback=True)
        .order_by("priority", "rule_code", "id")
        .first()
    )


def get_approval_tasks_queryset_for_request(request_obj):
    content_type = ContentType.objects.get_for_model(type(request_obj))
    return ApprovalTask.objects.filter(
        request_content_type=content_type,
        request_object_id=request_obj.id,
    ).order_by("step_no", "id")


def create_approval_tasks_for_request(request_obj, matched_rule=None):
    matched_rule = matched_rule or getattr(request_obj, "matched_rule", None)
    if not matched_rule:
        raise ValidationError("Cannot create approval tasks without a matched approval rule.")

    steps = matched_rule.steps.filter(is_active=True).order_by("step_no", "id")
    if not steps.exists():
        raise ValidationError("The matched approval rule has no active steps.")

    content_type = ContentType.objects.get_for_model(type(request_obj))
    get_approval_tasks_queryset_for_request(request_obj).delete()

    created_tasks = []
    for step in steps:
        is_first_step = len(created_tasks) == 0
        task_status = ApprovalTaskStatus.WAITING
        assigned_user = None
        candidates = []

        if step.approver_type in POOL_APPROVER_TYPES:
            resolver = getattr(request_obj, "resolve_step_candidates", None)
            if callable(resolver):
                candidates = resolver(step)

            if not candidates:
                raise ValidationError(
                    f"Unable to resolve any candidates for step {step.step_no} - {step.step_name}."
                )

            task_status = ApprovalTaskStatus.POOL if is_first_step else ApprovalTaskStatus.WAITING
        else:
            if is_first_step:
                resolver = getattr(request_obj, "resolve_fixed_step_assignee", None)
                assigned_user = resolver(step) if callable(resolver) else None
                if not assigned_user:
                    raise ValidationError(
                        f"Unable to resolve approver for step {step.step_no} - {step.step_name}."
                    )
                task_status = ApprovalTaskStatus.PENDING

        task_kwargs = {
            "request_content_type": content_type,
            "request_object_id": request_obj.id,
            "rule": matched_rule,
            "step": step,
            "step_no": step.step_no,
            "step_name": step.step_name,
            "assigned_user": assigned_user,
            "status": task_status,
            "due_at": timezone.now() + timedelta(days=step.sla_days or 0),
            "completed_at": None,
        }

        if request_obj._meta.app_label == "purchase":
            task_kwargs["purchase_request"] = request_obj

        task = ApprovalTask.objects.create(**task_kwargs)

        if candidates:
            ApprovalTaskCandidate.objects.bulk_create(
                [ApprovalTaskCandidate(task=task, user=user) for user in candidates]
            )
            task._add_history(
                action_type=ApprovalTaskActionType.CREATED,
                action_by=None,
                from_status=None,
                to_status=task.status,
                from_assignee=None,
                to_assignee=None,
                comment=f"Pool task created with {len(candidates)} candidate(s).",
            )
        else:
            task._add_history(
                action_type=ApprovalTaskActionType.CREATED,
                action_by=None,
                from_status=None,
                to_status=task.status,
                from_assignee=None,
                to_assignee=assigned_user,
                comment=(
                    f"Task created and assigned to {assigned_user}."
                    if assigned_user
                    else "Waiting task created. Assignee will be resolved on activation."
                ),
            )

        created_tasks.append(task)

    return created_tasks
