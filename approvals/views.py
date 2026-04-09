from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from common.choices import ApprovalTaskStatus, RequestStatus
from .models import ApprovalTask


def _build_querystring(request_get, exclude_keys=None):
    params = request_get.copy()
    exclude_keys = exclude_keys or []

    for key in exclude_keys:
        if key in params:
            del params[key]

    return params.urlencode()


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
    }
    return mapping.get(status, "badge-neutral")


@login_required
def my_tasks(request):
    search_q = request.GET.get("q", "").strip()

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

    if search_q:
        assigned_tasks = assigned_tasks.filter(
            Q(purchase_request__pr_no__icontains=search_q)
            | Q(purchase_request__title__icontains=search_q)
            | Q(step_name__icontains=search_q)
        )

        pool_tasks = pool_tasks.filter(
            Q(purchase_request__pr_no__icontains=search_q)
            | Q(purchase_request__title__icontains=search_q)
            | Q(step_name__icontains=search_q)
        )

    assigned_count = assigned_tasks.count()
    pool_count = pool_tasks.count()

    assigned_paginator = Paginator(assigned_tasks, 8)
    pool_paginator = Paginator(pool_tasks, 8)

    assigned_page_obj = assigned_paginator.get_page(request.GET.get("assigned_page"))
    pool_page_obj = pool_paginator.get_page(request.GET.get("pool_page"))

    for task in assigned_page_obj.object_list:
        task.can_release = task.candidates.exists()
        task.task_status_badge_class = _get_task_status_badge_class(task.status)
        task.pr_status_badge_class = _get_request_status_badge_class(task.purchase_request.status)

    for task in pool_page_obj.object_list:
        task.task_status_badge_class = _get_task_status_badge_class(task.status)
        task.pr_status_badge_class = _get_request_status_badge_class(task.purchase_request.status)

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