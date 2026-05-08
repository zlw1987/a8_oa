from datetime import datetime
from django.utils import timezone

from decimal import Decimal

from purchase.models import PurchaseRequest, PurchaseActualReviewStatus
from purchase.access import user_can_close_purchase
from travel.access import user_can_close_travel

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.db import transaction

from .forms import ApprovalRuleForm, ApprovalRuleStepFormSet
from .models import ApprovalRule


from common.choices import ApprovalTaskStatus, RequestStatus
from .models import ApprovalTask
from .filters import ApprovalTaskListFilterForm, ApprovalTaskHistoryFilterForm,AccountingReviewQueueFilterForm,VarianceExceptionReportFilterForm
from travel.models import TravelRequest, TravelActualReviewStatus
from django.contrib.contenttypes.models import ContentType

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
    if task.request_content_type_id and task.request_content_type.app_label == "projects":
        return reverse("projects:project_detail", args=[request_obj.pk])

    return reverse("purchase:pr_detail", args=[request_obj.pk])

def _enforce_rule_admin_permission(user):
    if not user.is_authenticated:
        raise PermissionDenied
    if not user.is_staff:
        raise PermissionDenied

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
    task.current_comment_display = task.comment or "-"
    requester = getattr(request_obj, "requester", None)
    task.request_requester_display = str(requester) if requester else "-"
    task.request_requester_id = str(getattr(request_obj, "requester_id", "") or "")

    if str(task.status) == str(ApprovalTaskStatus.POOL):
        task.ownership_label = "Pool task"
    elif getattr(task, "assigned_user", None):
        task.ownership_label = f"Assigned to {task.assigned_user}"
    else:
        task.ownership_label = "-"

    if task.request_content_type_id:
        app_label = task.request_content_type.app_label
        if app_label == "purchase":
            task.request_type_label = "Purchase"
            task.request_type_value = "PURCHASE"
        elif app_label == "travel":
            task.request_type_label = "Travel"
            task.request_type_value = "TRAVEL"
        elif app_label == "projects":
            task.request_type_label = "Project"
            task.request_type_value = "PROJECT"
        else:
            task.request_type_label = app_label.title()
            task.request_type_value = app_label.upper()
    elif task.purchase_request_id:
        task.request_type_label = "Purchase"
        task.request_type_value = "PURCHASE"
    else:
        task.request_type_label = "-"
        task.request_type_value = "-"

    task.pr_status_badge_class = (
        _get_request_status_badge_class(getattr(request_obj, "status", None))
        if request_obj else
        "badge-neutral"
    )

    task.due_at_display = task.due_at
    task.completed_at_display = task.completed_at
    task.due_status_display = task.due_status_label
    task.is_overdue_flag = task.is_overdue
    task.due_status_badge_class = "badge-danger" if task.is_overdue else "badge-neutral"

def _build_requester_choices(tasks):
    requester_map = {}

    for task in tasks:
        requester_id = getattr(task, "request_requester_id", "")
        requester_display = getattr(task, "request_requester_display", "-")
        if requester_id and requester_id not in requester_map:
            requester_map[requester_id] = requester_display

    return sorted(requester_map.items(), key=lambda item: item[1].lower())

def _task_sort_key(task):
    due_at = getattr(task, "due_at", None)
    created_at = getattr(task, "created_at", None) or timezone.now()

    overdue_rank = 0 if getattr(task, "is_overdue", False) else 1
    missing_due_rank = 1 if due_at is None else 0
    due_value = due_at or datetime.max.replace(tzinfo=timezone.get_current_timezone())

    return (overdue_rank, missing_due_rank, due_value, created_at)

def _task_matches_filters(task, cleaned_data):
    keyword = (cleaned_data.get("q") or "").strip().lower()
    request_type = cleaned_data.get("request_type") or ""
    requester = cleaned_data.get("requester") or ""
    due_state = cleaned_data.get("due_state") or ""

    if keyword:
        haystack = " ".join(
            [
                str(getattr(task, "request_no", "") or ""),
                str(getattr(task, "request_title", "") or ""),
                str(getattr(task, "step_name", "") or ""),
                str(getattr(task, "request_requester_display", "") or ""),
            ]
        ).lower()
        if keyword not in haystack:
            return False

    if request_type and getattr(task, "request_type_value", "") != request_type:
        return False

    if requester and getattr(task, "request_requester_id", "") != requester:
        return False

    if due_state == "overdue" and not getattr(task, "is_overdue", False):
        return False

    if due_state == "on_time":
        if getattr(task, "due_at", None) is None or getattr(task, "is_overdue", False):
            return False

    if due_state == "no_due_date" and getattr(task, "due_at", None) is not None:
        return False
    return True

@login_required
def rule_create(request):
    _enforce_rule_admin_permission(request.user)

    if request.method == "POST":
        form = ApprovalRuleForm(request.POST)
        formset = ApprovalRuleStepFormSet(request.POST, prefix="steps")

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                rule = form.save()
                formset.instance = rule
                formset.save()

            messages.success(request, f"Approval rule '{rule.rule_code}' created successfully.")
            return redirect("approvals:rule_edit", pk=rule.pk)
    else:
        form = ApprovalRuleForm()
        formset = ApprovalRuleStepFormSet(prefix="steps")

    context = {
        "page_mode": "create",
        "form": form,
        "formset": formset,
        "rule": None,
    }
    return render(request, "approvals/rule_edit.html", context)

@login_required
def rule_edit(request, pk):
    _enforce_rule_admin_permission(request.user)

    rule = get_object_or_404(
        ApprovalRule.objects.select_related("department", "specific_requester"),
        pk=pk,
    )

    if request.method == "POST":
        form = ApprovalRuleForm(request.POST, instance=rule)
        formset = ApprovalRuleStepFormSet(request.POST, instance=rule, prefix="steps")

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                rule = form.save()
                formset.save()

            messages.success(request, f"Approval rule '{rule.rule_code}' updated successfully.")
            return redirect("approvals:rule_edit", pk=rule.pk)
    else:
        form = ApprovalRuleForm(instance=rule)
        formset = ApprovalRuleStepFormSet(instance=rule, prefix="steps")

    step_preview_rows = list(
        rule.steps.order_by("step_no").values(
            "step_no",
            "step_name",
            "approver_type",
            "approver_user__username",
            "approver_department__dept_name",
            "sla_days",
            "is_active",
        )
    )

    context = {
        "page_mode": "edit",
        "form": form,
        "formset": formset,
        "rule": rule,
        "step_preview_rows": step_preview_rows,
    }
    return render(request, "approvals/rule_edit.html", context)

@login_required
def rule_list(request):
    _enforce_rule_admin_permission(request.user)

    queryset = (
        ApprovalRule.objects.select_related("department", "specific_requester")
        .annotate(step_count=Count("steps"))
        .order_by("request_type", "priority", "rule_code")
    )

    keyword = (request.GET.get("q") or "").strip()
    request_type = (request.GET.get("request_type") or "").strip()
    is_active = (request.GET.get("is_active") or "").strip()
    fallback = (request.GET.get("fallback") or "").strip()

    if keyword:
        queryset = queryset.filter(
            Q(rule_code__icontains=keyword)
            | Q(rule_name__icontains=keyword)
        )

    if request_type:
        queryset = queryset.filter(request_type=request_type)

    if is_active == "true":
        queryset = queryset.filter(is_active=True)
    elif is_active == "false":
        queryset = queryset.filter(is_active=False)

    if fallback == "true":
        queryset = queryset.filter(is_general_fallback=True)
    elif fallback == "false":
        queryset = queryset.filter(is_general_fallback=False)

    paginator = Paginator(queryset, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    querydict = request.GET.copy()
    querydict.pop("page", None)
    pagination_querystring = querydict.urlencode()

    context = {
        "page_obj": page_obj,
        "keyword": keyword,
        "request_type": request_type,
        "is_active": is_active,
        "fallback": fallback,
        "pagination_querystring": pagination_querystring,
    }
    return render(request, "approvals/rule_list.html", context)

@login_required
def my_history(request):
    history_qs = (
        ApprovalTask.objects.filter(
            acted_by=request.user,
            acted_at__isnull=False,
        )
        .select_related(
            "purchase_request",
            "request_content_type",
            "rule",
            "step",
            "assigned_user",
            "acted_by",
        )
        .prefetch_related("candidates")
        .order_by("-acted_at", "-id")
    )

    history_tasks = list(history_qs)
    for task in history_tasks:
        _decorate_task(task)

    filter_form = ApprovalTaskHistoryFilterForm(request.GET or None)

    if filter_form.is_valid():
        q = (filter_form.cleaned_data.get("q") or "").strip().lower()
        request_type = filter_form.cleaned_data.get("request_type") or ""
        outcome_status = filter_form.cleaned_data.get("outcome_status") or ""

        filtered = []
        for task in history_tasks:
            if q:
                haystack = " ".join(
                    [
                        str(getattr(task, "request_no", "") or ""),
                        str(getattr(task, "request_title", "") or ""),
                        str(getattr(task, "step_name", "") or ""),
                        str(getattr(task, "request_requester_display", "") or ""),
                        str(getattr(task, "comment", "") or ""),
                    ]
                ).lower()
                if q not in haystack:
                    continue

            if request_type and getattr(task, "request_type_value", "") != request_type:
                continue

            if outcome_status and task.status != outcome_status:
                continue

            filtered.append(task)

        history_tasks = filtered

    paginator = Paginator(history_tasks, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    querydict = request.GET.copy()
    querydict.pop("page", None)
    pagination_querystring = querydict.urlencode()

    context = {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "pagination_querystring": pagination_querystring,
        "history_count": len(history_tasks),
    }
    return render(request, "approvals/my_history.html", context)

def _build_purchase_accounting_review_row(pr):
    actual_total = pr.get_actual_spent_total()
    variance_amount = actual_total - pr.estimated_total

    return {
        "request_type": "PURCHASE",
        "request_type_label": "Purchase",
        "request_no": pr.pr_no,
        "title": pr.title,
        "requester": str(pr.requester),
        "project": str(pr.project) if pr.project else "-",
        "estimated_total": pr.estimated_total,
        "actual_total": actual_total,
        "variance_amount": variance_amount,
        "review_status": pr.actual_review_status,
        "review_status_label": pr.get_actual_review_status_display(),
        "reviewed_by": pr.actual_reviewed_by,
        "reviewed_at": pr.actual_reviewed_at,
        "detail_url": reverse("purchase:pr_detail", args=[pr.id]),
    }


def _build_travel_accounting_review_row(tr):
    variance_amount = tr.actual_total - tr.estimated_total

    return {
        "request_type": "TRAVEL",
        "request_type_label": "Travel",
        "request_no": tr.travel_no,
        "title": tr.purpose,
        "requester": str(tr.requester),
        "project": str(tr.project) if tr.project else "-",
        "estimated_total": tr.estimated_total,
        "actual_total": tr.actual_total,
        "variance_amount": variance_amount,
        "review_status": tr.actual_review_status,
        "review_status_label": tr.get_actual_review_status_display(),
        "reviewed_by": tr.actual_reviewed_by,
        "reviewed_at": tr.actual_reviewed_at,
        "detail_url": reverse("travel:tr_detail", args=[tr.id]),
    }


def _matches_accounting_review_filters(row, cleaned_data):
    q = (cleaned_data.get("q") or "").strip().lower()
    request_type = cleaned_data.get("request_type") or ""
    review_status = cleaned_data.get("review_status") or ""

    if q:
        haystack = " ".join(
            [
                str(row.get("request_no") or ""),
                str(row.get("title") or ""),
                str(row.get("requester") or ""),
                str(row.get("project") or ""),
            ]
        ).lower()
        if q not in haystack:
            return False

    if request_type and row.get("request_type") != request_type:
        return False

    if review_status and row.get("review_status") != review_status:
        return False

    return True

@login_required
def accounting_review_queue(request):
    purchase_requests = (
        PurchaseRequest.get_visible_queryset(request.user)
        .select_related("requester", "project", "actual_reviewed_by")
        .filter(is_over_estimate=True)
        .order_by("-id")
    )

    purchase_requests = [
        pr for pr in purchase_requests
        if user_can_close_purchase(request.user, pr)
    ]

    travel_requests = (
        TravelRequest.get_visible_queryset(request.user)
        .select_related("requester", "project", "actual_reviewed_by")
        .filter(is_over_estimate=True)
        .order_by("-id")
    )

    travel_requests = [
        tr for tr in travel_requests
        if user_can_close_travel(request.user, tr)
    ]

    rows = [
        *[_build_purchase_accounting_review_row(pr) for pr in purchase_requests],
        *[_build_travel_accounting_review_row(tr) for tr in travel_requests],
    ]

    filter_form = AccountingReviewQueueFilterForm(request.GET or None)

    if filter_form.is_valid():
        rows = [
            row for row in rows
            if _matches_accounting_review_filters(row, filter_form.cleaned_data)
        ]

    rows.sort(
        key=lambda row: (
            0 if row["review_status"] == "PENDING_REVIEW" else 1,
            -(row["variance_amount"] or Decimal("0.00")),
            row["request_no"],
        )
    )

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    querydict = request.GET.copy()
    querydict.pop("page", None)
    pagination_querystring = querydict.urlencode()

    context = {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "total_count": len(rows),
        "pending_count": sum(1 for row in rows if row["review_status"] == "PENDING_REVIEW"),
        "approved_count": sum(1 for row in rows if row["review_status"] == "APPROVED_TO_PROCEED"),
        "rejected_count": sum(1 for row in rows if row["review_status"] == "REJECTED"),
        "pagination_querystring": pagination_querystring,
    }
    return render(request, "approvals/accounting_review_queue.html", context)

@login_required
def my_tasks(request):
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

    for task in assigned_tasks:
        _decorate_task(task)

    for task in pool_tasks:
        _decorate_task(task)

    all_tasks = assigned_tasks + pool_tasks
    requester_choices = _build_requester_choices(all_tasks)

    filter_form = ApprovalTaskListFilterForm(
        request.GET or None,
        requester_choices=requester_choices,
    )

    if filter_form.is_valid():
        assigned_tasks = [
            task for task in assigned_tasks
            if _task_matches_filters(task, filter_form.cleaned_data)
        ]
        pool_tasks = [
            task for task in pool_tasks
            if _task_matches_filters(task, filter_form.cleaned_data)
        ]

    assigned_count = len(assigned_tasks)
    pool_count = len(pool_tasks)
    assigned_tasks = sorted(assigned_tasks, key=_task_sort_key)
    pool_tasks = sorted(pool_tasks, key=_task_sort_key)
    assigned_overdue_count = sum(1 for task in assigned_tasks if getattr(task, "is_overdue", False))
    pool_overdue_count = sum(1 for task in pool_tasks if getattr(task, "is_overdue", False))

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
        "filter_form": filter_form,
        "assigned_overdue_count": assigned_overdue_count,
        "pool_overdue_count": pool_overdue_count,
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

def _matches_variance_report_filters(row, cleaned_data):
    q = (cleaned_data.get("q") or "").strip().lower()
    request_type = cleaned_data.get("request_type") or ""
    review_status = cleaned_data.get("review_status") or ""
    requester = (cleaned_data.get("requester") or "").strip().lower()

    if q:
        haystack = " ".join(
            [
                str(row.get("request_no") or ""),
                str(row.get("title") or ""),
                str(row.get("requester") or ""),
                str(row.get("project") or ""),
            ]
        ).lower()
        if q not in haystack:
            return False

    if request_type and row.get("request_type") != request_type:
        return False

    if review_status and row.get("review_status") != review_status:
        return False

    if requester and requester not in str(row.get("requester") or "").lower():
        return False

    return True

@login_required
def variance_exception_report(request):
    purchase_requests = (
        PurchaseRequest.get_visible_queryset(request.user)
        .select_related("requester", "project", "actual_reviewed_by")
        .filter(is_over_estimate=True)
        .order_by("-id")
    )

    purchase_requests = [
        pr for pr in purchase_requests
        if user_can_close_purchase(request.user, pr)
    ]

    travel_requests = (
        TravelRequest.get_visible_queryset(request.user)
        .select_related("requester", "project", "actual_reviewed_by")
        .filter(is_over_estimate=True)
        .order_by("-id")
    )

    travel_requests = [
        tr for tr in travel_requests
        if user_can_close_travel(request.user, tr)
    ]

    rows = [
        *[_build_purchase_accounting_review_row(pr) for pr in purchase_requests],
        *[_build_travel_accounting_review_row(tr) for tr in travel_requests],
    ]

    filter_form = VarianceExceptionReportFilterForm(request.GET or None)

    if filter_form.is_valid():
        rows = [
            row for row in rows
            if _matches_variance_report_filters(row, filter_form.cleaned_data)
        ]

    rows.sort(
        key=lambda row: (
            0 if row["review_status"] == "PENDING_REVIEW" else 1,
            -(row["variance_amount"] or Decimal("0.00")),
            row["request_no"],
        )
    )

    total_variance = sum((row["variance_amount"] for row in rows), Decimal("0.00"))

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    querydict = request.GET.copy()
    querydict.pop("page", None)
    pagination_querystring = querydict.urlencode()

    context = {
        "filter_form": filter_form,
        "page_obj": page_obj,
        "total_count": len(rows),
        "pending_count": sum(1 for row in rows if row["review_status"] == "PENDING_REVIEW"),
        "approved_count": sum(1 for row in rows if row["review_status"] == "APPROVED_TO_PROCEED"),
        "rejected_count": sum(1 for row in rows if row["review_status"] == "REJECTED"),
        "total_variance": total_variance,
        "pagination_querystring": pagination_querystring,
    }
    return render(request, "approvals/variance_exception_report.html", context)
