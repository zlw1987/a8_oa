from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse

from common.choices import ApprovalTaskStatus, RequestStatus
from .models import ApprovalTask


def _build_querystring(request_get, exclude_keys=None):
    params = request_get.copy()
    exclude_keys = exclude_keys or []

    for key in exclude_keys:
        if key in params:
            del params[key]

    return params.urlencode()

def _get_request_detail_url(task):
    request_obj = task.get_request_object()
    if not request_obj:
        return ""

    if task.request_content_type_id and task.request_content_type.app_label == "travel":
        return reverse("travel:tr_detail", args=[request_obj.pk])

    return reverse("purchase:pr_detail", args=[request_obj.pk])

def _get_task_status_badge_class(status):
    mapping = {
        ApprovalTaskStatus.WAITING: "badge-neutral",
        ApprovalTaskStatus.POOL: "badge-info",
        ApprovalTaskStatus.PENDING: "badge-warning",
        ApprovalTaskStatus.APPROVED: "badge-success",
        ApprovalTaskStatus.REJECTED: "badge-danger",
        ApprovalTaskStatus.RETURNED: "badge-info",
        ApprovalTaskStatus.SKIPPED: "badge-dark",
        ApprovalTaskStatus.CANCELLED: "badge-dark",
    }
    return mapping.get(status, "badge-neutral")


def _get_request_status_badge_class(status):
    mapping = {
        RequestStatus.DRAFT: "badge-neutral",
        RequestStatus.SUBMITTED: "badge-warning",
        RequestStatus.PENDING: "badge-warning",
        RequestStatus.APPROVED: "badge-success",
        RequestStatus.REJECTED: "badge-danger",
        RequestStatus.RETURNED: "badge-info",
        RequestStatus.CANCELLED: "badge-dark",
        RequestStatus.CLOSED: "badge-dark",

        # Travel statuses
        "PENDING_APPROVAL": "badge-warning",
        "IN_TRIP": "badge-info",
        "EXPENSE_PENDING": "badge-info",
        "EXPENSE_SUBMITTED": "badge-warning",
    }
    return mapping.get(status, "badge-neutral")

def _decorate_task(task):
    task.can_release = task.candidates.exists()
    task.task_status_badge_class = _get_task_status_badge_class(task.status)

    request_obj = task.get_request_object()

    task.request_detail_url = _get_request_detail_url(task)
    task.request_no_display = task.request_no or "-"
    task.request_title_display = task.request_title or "-"
    task.request_status_display = request_obj.get_status_display() if request_obj else "-"
    task.request_amount = getattr(request_obj, "estimated_total", "")
    task.request_currency = getattr(request_obj, "currency", "")

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

    task.pr_status_badge_class = (
        _get_request_status_badge_class(getattr(request_obj, "status", None))
        if request_obj else
        "badge-neutral"
    )

@login_required
def my_tasks(request):
    search_q = request.GET.get("q", "").strip()

    assigned_qs = (
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.PENDING,
            assigned_user=request.user,
        )
        .select_related(
            "purchase_request",
            "request_content_type",
            "rule",
            "step",
            "assigned_user",
        )
        .prefetch_related("candidates")
        .order_by("created_at", "id")
    )

    pool_qs = (
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.POOL,
            candidates__user=request.user,
            candidates__is_active=True,
        )
        .select_related(
            "purchase_request",
            "request_content_type",
            "rule",
            "step",
        )
        .prefetch_related("candidates")
        .distinct()
        .order_by("created_at", "id")
    )

    assigned_tasks = list(assigned_qs)
    pool_tasks = list(pool_qs)

    if search_q:
        search_q_lower = search_q.lower()

        assigned_tasks = [
            task for task in assigned_tasks
            if search_q_lower in f"{task.request_no} {task.request_title} {task.step_name}".lower()
        ]

        pool_tasks = [
            task for task in pool_tasks
            if search_q_lower in f"{task.request_no} {task.request_title} {task.step_name}".lower()
        ]

    for task in assigned_tasks:
        _decorate_task(task)

    for task in pool_tasks:
        _decorate_task(task)

    assigned_count = len(assigned_tasks)
    pool_count = len(pool_tasks)

    assigned_paginator = Paginator(assigned_tasks, 8)
    pool_paginator = Paginator(pool_tasks, 8)

    assigned_page_obj = assigned_paginator.get_page(request.GET.get("assigned_page"))
    pool_page_obj = pool_paginator.get_page(request.GET.get("pool_page"))

    context = {
        "assigned_tasks": assigned_page_obj.object_list,
        "pool_tasks": pool_page_obj.object_list,
        "assigned_count": assigned_count,
        "pool_count": pool_count,
        "assigned_page_obj": assigned_page_obj,
        "pool_page_obj": pool_page_obj,
        "assigned_pagination_querystring": _build_querystring(request.GET, ["assigned_page"]),
        "pool_pagination_querystring": _build_querystring(request.GET, ["pool_page"]),
        "search_q": search_q,
    }
    return render(request, "approvals/my_tasks.html", context)

@login_required
@require_POST
def task_claim(request, task_id):
    task = get_object_or_404(ApprovalTask, pk=task_id)

    try:
        task.claim(request.user)
        messages.success(request, f"Task '{task.step_name}' claimed successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("approvals:my_tasks")


@login_required
@require_POST
def task_release(request, task_id):
    task = get_object_or_404(ApprovalTask, pk=task_id)

    try:
        task.release_to_pool(request.user)
        messages.success(request, f"Task '{task.step_name}' released back to pool.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("approvals:my_tasks")


@login_required
@require_POST
def task_approve(request, task_id):
    task = get_object_or_404(ApprovalTask, pk=task_id)
    comment = request.POST.get("comment", "").strip()

    try:
        task.approve(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' approved successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("approvals:my_tasks")


@login_required
@require_POST
def task_return(request, task_id):
    task = get_object_or_404(ApprovalTask, pk=task_id)
    comment = request.POST.get("comment", "").strip()

    try:
        task.return_to_requester(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' returned to requester successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("approvals:my_tasks")


@login_required
@require_POST
def task_reject(request, task_id):
    task = get_object_or_404(ApprovalTask, pk=task_id)
    comment = request.POST.get("comment", "").strip()

    try:
        task.reject(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' rejected successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("approvals:my_tasks")