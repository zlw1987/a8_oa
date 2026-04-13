from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from approvals.models import ApprovalTask
from common.choices import ApprovalTaskStatus, RequestStatus
from purchase.models import PurchaseRequest


def _get_request_detail_url(task):
    request_obj = task.get_request_object()
    if not request_obj:
        return ""

    if task.request_content_type_id and task.request_content_type.app_label == "travel":
        return reverse("travel:tr_detail", args=[request_obj.pk])

    return reverse("purchase:pr_detail", args=[request_obj.pk])


def _decorate_dashboard_task(task):
    request_obj = task.get_request_object()

    task.request_detail_url = _get_request_detail_url(task)
    task.request_no_display = task.request_no or "-"
    task.request_title_display = task.request_title or "-"
    task.request_status_display = request_obj.get_status_display() if request_obj else "-"
    task.request_currency = getattr(request_obj, "currency", "")
    task.request_amount = getattr(request_obj, "estimated_total", "")

    if task.request_content_type_id:
        app_label = task.request_content_type.app_label
        if app_label == "purchase":
            task.request_type_label = "Purchase"
        elif app_label == "travel":
            task.request_type_label = "Travel"
        else:
            task.request_type_label = app_label.title()
    elif task.purchase_request_id:
        task.request_type_label = "Purchase"
    else:
        task.request_type_label = "-"

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
        .select_related("purchase_request", "request_content_type", "rule", "step", "assigned_user")
        .order_by("created_at")
    )

    assigned_tasks = list(assigned_tasks)

    for task in assigned_tasks:
        _decorate_dashboard_task(task)

    pool_tasks = (
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.POOL,
            candidates__user=request.user,
            candidates__is_active=True,
        )
        .select_related("purchase_request", "request_content_type", "rule", "step")
        .distinct()
        .order_by("created_at")
    )

    pool_tasks = list(pool_tasks)

    for task in pool_tasks:
        _decorate_dashboard_task(task)

    context = {
        "editable_count": my_editable_requests.count(),
        "in_progress_count": my_in_progress_requests.count(),
        "assigned_task_count": len(assigned_tasks),
        "pool_task_count": len(pool_tasks),
        "my_recent_requests": my_recent_requests,
        "assigned_tasks": assigned_tasks[:5],
        "pool_tasks": pool_tasks[:5],
    }
    return render(request, "dashboard/home.html", context)