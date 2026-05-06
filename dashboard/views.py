from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from approvals.models import ApprovalTask
from common.choices import ApprovalTaskStatus, RequestStatus
from purchase.models import PurchaseRequest
from travel.models import TravelRequest, TravelRequestStatus
from accounts.models import Department
from approvals.dashboard import get_approval_summary_for_user

def _can_create_project(user):
    if user.is_superuser:
        return True
    return Department.objects.filter(manager=user).exists()

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


def _build_dashboard_request_item(request_obj, request_type_label, detail_url):
    if request_type_label == "Purchase":
        request_no = request_obj.pr_no or "-"
        title = request_obj.title or "-"
    else:
        request_no = request_obj.travel_no or "-"
        title = request_obj.purpose or "-"

    project_obj = getattr(request_obj, "project", None)

    return {
        "request_type_label": request_type_label,
        "request_no": request_no,
        "title": title,
        "status_display": request_obj.get_status_display(),
        "project": str(project_obj) if project_obj else "",
        "project_budget_url": (
            reverse("projects:project_budget_ledger", args=[project_obj.id])
            if project_obj else ""
        ),
        "currency": getattr(request_obj, "currency", ""),
        "amount": getattr(request_obj, "estimated_total", ""),
        "detail_url": detail_url,
        "sort_request_date": getattr(request_obj, "request_date", None) or date.min,
        "sort_id": request_obj.id,
    }


@login_required
def home(request):
    purchase_editable_qs = (
        PurchaseRequest.objects.filter(
            requester=request.user,
            status__in=[RequestStatus.DRAFT, RequestStatus.RETURNED],
        )
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")
    )

    travel_editable_qs = (
        TravelRequest.objects.filter(
            requester=request.user,
            status__in=[TravelRequestStatus.DRAFT, TravelRequestStatus.RETURNED],
        )
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")
    )

    purchase_in_progress_qs = (
        PurchaseRequest.objects.filter(
            requester=request.user,
            status__in=[RequestStatus.SUBMITTED, RequestStatus.PENDING, RequestStatus.APPROVED],
        )
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")
    )

    travel_in_progress_qs = (
        TravelRequest.objects.filter(
            requester=request.user,
            status__in=[
                TravelRequestStatus.PENDING_APPROVAL,
                TravelRequestStatus.APPROVED,
                TravelRequestStatus.EXPENSE_PENDING,
                TravelRequestStatus.EXPENSE_SUBMITTED,
            ],
        )
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")
    )

    purchase_recent_requests = list(
        PurchaseRequest.objects.filter(requester=request.user)
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")[:10]
    )

    travel_recent_requests = list(
        TravelRequest.objects.filter(requester=request.user)
        .select_related("project", "request_department")
        .order_by("-request_date", "-id")[:10]
    )

    my_recent_requests = []

    for pr in purchase_recent_requests:
        my_recent_requests.append(
            _build_dashboard_request_item(
                request_obj=pr,
                request_type_label="Purchase",
                detail_url=reverse("purchase:pr_detail", args=[pr.id]),
            )
        )

    for tr in travel_recent_requests:
        my_recent_requests.append(
            _build_dashboard_request_item(
                request_obj=tr,
                request_type_label="Travel",
                detail_url=reverse("travel:tr_detail", args=[tr.id]),
            )
        )

    my_recent_requests.sort(
        key=lambda item: (item["sort_request_date"], item["sort_id"]),
        reverse=True,
    )
    my_recent_requests = my_recent_requests[:8]

    assigned_tasks = list(
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.PENDING,
            assigned_user=request.user,
        )
        .select_related("purchase_request", "request_content_type", "rule", "step", "assigned_user")
        .prefetch_related("candidates")
        .order_by("created_at", "id")
    )

    for task in assigned_tasks:
        _decorate_dashboard_task(task)

    pool_tasks = list(
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.POOL,
            candidates__user=request.user,
            candidates__is_active=True,
        )
        .select_related("purchase_request", "request_content_type", "rule", "step")
        .prefetch_related("candidates")
        .distinct()
        .order_by("created_at", "id")
    )

    for task in pool_tasks:
        _decorate_dashboard_task(task)

    context = {
        "editable_count": purchase_editable_qs.count() + travel_editable_qs.count(),
        "in_progress_count": purchase_in_progress_qs.count() + travel_in_progress_qs.count(),
        "assigned_task_count": len(assigned_tasks),
        "pool_task_count": len(pool_tasks),
        "my_recent_requests": my_recent_requests,
        "assigned_tasks": assigned_tasks[:5],
        "pool_tasks": pool_tasks[:5],
        "can_create_project": _can_create_project(request.user),
        "approval_summary": get_approval_summary_for_user(request.user),
    }
    return render(request, "dashboard/home.html", context)