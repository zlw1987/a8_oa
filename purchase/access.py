from django.core.exceptions import PermissionDenied
from django.db.models import Q

from approvals.models import ApprovalTaskStatus
from common.choices import RequestStatus
from .models import PurchaseRequest


def get_visible_purchase_queryset_for_user(user):
    qs = PurchaseRequest.objects.all()

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    return qs.filter(
        Q(requester=user)
        | Q(request_department__manager=user)
        | Q(approval_tasks__assigned_user=user)
        | Q(approval_tasks__candidates__user=user, approval_tasks__candidates__is_active=True)
        | Q(approval_tasks__acted_by=user)
    ).distinct()


def user_can_view_purchase(user, pr):
    return get_visible_purchase_queryset_for_user(user).filter(pk=pr.pk).exists()


def user_can_edit_purchase(user, pr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return pr.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]

    return (
        pr.requester_id == user.id
        and pr.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]
    )


def user_can_submit_purchase(user, pr):
    return user_can_edit_purchase(user, pr)


def user_can_cancel_purchase(user, pr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return pr.status in [
            RequestStatus.SUBMITTED,
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
        ]

    return (
        pr.requester_id == user.id
        and pr.status in [
            RequestStatus.SUBMITTED,
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
        ]
    )


def user_can_record_actual_spend(user, pr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return pr.status == RequestStatus.APPROVED

    return pr.requester_id == user.id and pr.status == RequestStatus.APPROVED


def user_can_close_purchase(user, pr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return pr.status == RequestStatus.APPROVED

    return pr.requester_id == user.id and pr.status == RequestStatus.APPROVED


def user_can_manage_attachment(user, pr):
    return user_can_edit_purchase(user, pr)


def enforce_purchase_permission(condition):
    if not condition:
        raise PermissionDenied("You do not have permission to perform this action.")