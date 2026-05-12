from django.core.exceptions import PermissionDenied
from django.db.models import Q

from common.choices import ApprovalTaskStatus
from .models import ApprovalDelegation


def get_active_delegation_for_task(user, task, date_value=None):
    if not user or not user.is_authenticated or not task:
        return None
    from django.utils import timezone

    today = date_value or timezone.localdate()
    request_obj = task.get_request_object() if hasattr(task, "get_request_object") else None
    requester_id = getattr(request_obj, "requester_id", None)
    if requester_id and requester_id == user.id:
        return None
    department = getattr(request_obj, "request_department", None)
    request_type = getattr(task, "request_type_value", "") or ""
    if not request_type and task.request_content_type_id:
        app_label = task.request_content_type.app_label
        if app_label == "purchase":
            request_type = "PURCHASE"
        elif app_label == "travel":
            request_type = "TRAVEL"
    queryset = ApprovalDelegation.objects.filter(
        original_approver=task.assigned_user,
        delegate_user=user,
        start_date__lte=today,
        end_date__gte=today,
        is_active=True,
    )
    queryset = queryset.filter(Q(department__isnull=True) | Q(department=department))
    queryset = queryset.filter(Q(request_type="") | Q(request_type=request_type))
    return queryset.order_by("-start_date", "-id").first()


def user_can_claim_task(user, task):
    if not user or not user.is_authenticated:
        return False

    return (
        task.status == ApprovalTaskStatus.POOL
        and task.can_user_claim(user)
    )


def user_can_release_task(user, task):
    if not user or not user.is_authenticated:
        return False

    return (
        task.status == ApprovalTaskStatus.PENDING
        and task.assigned_user_id == user.id
        and task.candidates.filter(is_active=True).exists()
    )


def user_can_approve_task(user, task):
    if not user or not user.is_authenticated:
        return False

    request_obj = task.get_request_object() if hasattr(task, "get_request_object") else None
    requester_id = getattr(request_obj, "requester_id", None)
    if requester_id and requester_id == user.id:
        return False

    if task.status != ApprovalTaskStatus.PENDING:
        return False
    if task.assigned_user_id == user.id:
        return True
    return bool(get_active_delegation_for_task(user, task))


def user_can_return_task(user, task):
    return user_can_approve_task(user, task)


def user_can_reject_task(user, task):
    return user_can_approve_task(user, task)


def get_task_action_flags(user, task):
    if not task:
        return {
            "can_claim_current_task": False,
            "can_release_current_task": False,
            "can_approve_current_task": False,
            "can_return_current_task": False,
            "can_reject_current_task": False,
        }

    return {
        "can_claim_current_task": user_can_claim_task(user, task),
        "can_release_current_task": user_can_release_task(user, task),
        "can_approve_current_task": user_can_approve_task(user, task),
        "can_return_current_task": user_can_return_task(user, task),
        "can_reject_current_task": user_can_reject_task(user, task),
    }


def enforce_approval_permission(condition):
    if not condition:
        raise PermissionDenied("You do not have permission to perform this approval action.")
