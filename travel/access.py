from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from approvals.models import ApprovalTask
from .models import TravelRequest, TravelRequestStatus


def get_visible_travel_queryset_for_user(user):
    qs = TravelRequest.objects.all()

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    content_type = ContentType.objects.get_for_model(TravelRequest)

    visible_task_request_ids = ApprovalTask.objects.filter(
        request_content_type=content_type,
    ).filter(
        Q(assigned_user=user)
        | Q(candidates__user=user, candidates__is_active=True)
        | Q(acted_by=user)
    ).values_list("request_object_id", flat=True)

    return qs.filter(
        Q(requester=user)
        | Q(request_department__manager=user)
        | Q(id__in=visible_task_request_ids)
    ).distinct()


def user_can_view_travel(user, tr):
    return get_visible_travel_queryset_for_user(user).filter(pk=tr.pk).exists()


def user_can_edit_travel(user, tr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return tr.status in [TravelRequestStatus.DRAFT, TravelRequestStatus.RETURNED]

    return (
        tr.requester_id == user.id
        and tr.status in [TravelRequestStatus.DRAFT, TravelRequestStatus.RETURNED]
    )


def user_can_submit_travel(user, tr):
    return user_can_edit_travel(user, tr)


def user_can_cancel_travel(user, tr):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return tr.status in [
            TravelRequestStatus.PENDING_APPROVAL,
            TravelRequestStatus.APPROVED,
        ]

    return (
        tr.requester_id == user.id
        and tr.status in [
            TravelRequestStatus.PENDING_APPROVAL,
            TravelRequestStatus.APPROVED,
        ]
    )


def user_can_close_travel(user, tr):
    if not user or not user.is_authenticated:
        return False

    allowed_statuses = [
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.EXPENSE_PENDING,
        TravelRequestStatus.EXPENSE_SUBMITTED,
    ]

    if user.is_superuser:
        return tr.status in allowed_statuses

    return tr.requester_id == user.id and tr.status in allowed_statuses


def user_can_record_actual_expense_travel(user, tr):
    if not user or not user.is_authenticated:
        return False

    allowed_statuses = [
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.IN_TRIP,
        TravelRequestStatus.EXPENSE_PENDING,
        TravelRequestStatus.EXPENSE_SUBMITTED,
    ]

    if user.is_superuser:
        return tr.status in allowed_statuses

    return tr.requester_id == user.id and tr.status in allowed_statuses


def user_can_manage_travel_attachment(user, tr):
    return user_can_edit_travel(user, tr)


def enforce_travel_permission(condition):
    if not condition:
        raise PermissionDenied("You do not have permission to perform this action.")