from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from approvals.models import ApprovalTask
from common.choices import ApprovalTaskStatus, RequestStatus
from purchase.models import PurchaseRequest


@login_required
def home(request):
    my_editable_requests = (
        PurchaseRequest.objects.filter(
            requester=request.user,
            status__in=[RequestStatus.DRAFT, RequestStatus.RETURNED],
        )
        .select_related("project", "request_department")
        .order_by("-id")
    )

    my_in_progress_requests = (
        PurchaseRequest.objects.filter(
            requester=request.user,
            status__in=[RequestStatus.SUBMITTED, RequestStatus.PENDING],
        )
        .select_related("project", "request_department")
        .order_by("-id")
    )

    my_recent_requests = (
        PurchaseRequest.objects.filter(requester=request.user)
        .select_related("project", "request_department")
        .order_by("-id")[:5]
    )

    assigned_tasks = (
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.PENDING,
            assigned_user=request.user,
        )
        .select_related("purchase_request", "rule", "step", "assigned_user")
        .order_by("created_at")
    )

    pool_tasks = (
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.POOL,
            candidates__user=request.user,
            candidates__is_active=True,
        )
        .select_related("purchase_request", "rule", "step")
        .distinct()
        .order_by("created_at")
    )

    context = {
        "editable_count": my_editable_requests.count(),
        "in_progress_count": my_in_progress_requests.count(),
        "assigned_task_count": assigned_tasks.count(),
        "pool_task_count": pool_tasks.count(),
        "my_recent_requests": my_recent_requests,
        "assigned_tasks": assigned_tasks[:5],
        "pool_tasks": pool_tasks[:5],
    }
    return render(request, "dashboard/home.html", context)