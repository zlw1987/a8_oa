from django.core.exceptions import PermissionDenied

from common.choices import ApprovalTaskStatus


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

    return (
        task.status == ApprovalTaskStatus.PENDING
        and task.assigned_user_id == user.id
    )


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
