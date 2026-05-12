from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from approvals.models import ApprovalTask
from common.choices import ApprovalTaskStatus, RequestStatus
from purchase.models import PurchaseRequest
from travel.models import TravelRequest, TravelRequestStatus
from approvals.dashboard import get_approval_summary_for_user
from finance.models import (
    AccountingReviewItem,
    AccountingReviewReason,
    AccountingReviewStatus,
    CardTransaction,
    CardTransactionMatchStatus,
    OverBudgetAction,
)
from finance.presentation import OPEN_STATUS_FILTER
from projects.models import Project
from projects.access import user_can_create_project

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


def _dashboard_card(label, value, url="", tone="neutral", description=""):
    return {
        "label": label,
        "value": value,
        "url": url,
        "tone": tone,
        "description": description,
    }


def _dashboard_section(title, cards, *, secondary=False, collapsible=False):
    visible_cards = [card for card in cards if card is not None]
    return {
        "title": title,
        "cards": visible_cards,
        "secondary": secondary,
        "collapsible": collapsible,
    }


def _priority_card(label, value, url="", tone="neutral", description=""):
    if not value:
        return None
    return _dashboard_card(label, value, url, tone=tone, description=description)


def _open_review_queryset():
    return AccountingReviewItem.objects.filter(status__in=OPEN_STATUS_FILTER)


def _projects_near_budget_limit_count():
    count = 0
    for project in Project.objects.filter(is_active=True):
        effective_budget = project.get_effective_budget_amount()
        if effective_budget <= 0:
            continue
        available_ratio = project.get_available_amount() / effective_budget
        if available_ratio <= 0.10:
            count += 1
    return count


def _build_role_dashboard_sections(user):
    now = timezone.now()
    open_reviews = _open_review_queryset()
    requester_purchase = PurchaseRequest.objects.filter(requester=user)
    requester_travel = TravelRequest.objects.filter(requester=user)
    assigned_pending = ApprovalTask.objects.filter(status=ApprovalTaskStatus.PENDING, assigned_user=user)
    pool_pending = ApprovalTask.objects.filter(
        status=ApprovalTaskStatus.POOL,
        candidates__user=user,
        candidates__is_active=True,
    ).distinct()
    overdue_assigned = assigned_pending.filter(due_at__lt=now)

    returned_count = requester_purchase.filter(status=RequestStatus.RETURNED).count() + requester_travel.filter(
        status=TravelRequestStatus.RETURNED
    ).count()
    missing_receipt_count = open_reviews.filter(
        reason=AccountingReviewReason.MISSING_RECEIPT,
        purchase_request__requester=user,
    ).count() + open_reviews.filter(
        reason=AccountingReviewReason.MISSING_RECEIPT,
        travel_request__requester=user,
    ).count()
    unmatched_cards = CardTransaction.objects.none()
    if user.is_staff:
        unmatched_cards = CardTransaction.objects.filter(
            match_status__in=[CardTransactionMatchStatus.UNMATCHED, CardTransactionMatchStatus.PARTIALLY_MATCHED]
        )

    sections = [
        _dashboard_section(
            "My Work Today",
            [
                _priority_card("Pending Approval Tasks", assigned_pending.count(), reverse("approvals:my_tasks"), tone="attention"),
                _priority_card(
                    "Overdue Approval Tasks",
                    overdue_assigned.count(),
                    reverse("approvals:my_tasks") + "?due_state=overdue",
                    tone="danger",
                ),
                _priority_card(
                    "Returned to Me",
                    returned_count,
                    reverse("purchase:pr_list") + "?status=RETURNED",
                    tone="attention",
                    description="Requests returned for correction.",
                ),
                _priority_card(
                    "Missing Receipt / Need Action",
                    missing_receipt_count,
                    reverse("purchase:pr_list"),
                    tone="warning",
                    description="Receipt issues connected to your requests.",
                ),
                _priority_card(
                    "Pending Accounting Reviews",
                    open_reviews.count() if user.is_staff else 0,
                    reverse("finance:accounting_review_queue") if user.is_staff else "",
                    tone="attention",
                ),
                _priority_card(
                    "Unmatched Card Transactions",
                    unmatched_cards.count() if user.is_staff else 0,
                    reverse("finance:card_transaction_list") + "?status=UNMATCHED" if user.is_staff else "",
                    tone="warning",
                ),
            ],
        ),
        _dashboard_section(
            "Approval Summary",
            [
                _dashboard_card("My Pending Approval Tasks", assigned_pending.count(), reverse("approvals:my_tasks")),
                _dashboard_card("Claimable Pool Tasks", pool_pending.count(), reverse("approvals:my_tasks")),
                _dashboard_card(
                    "Recently Approved",
                    ApprovalTask.objects.filter(status=ApprovalTaskStatus.APPROVED, acted_by=user).count(),
                    reverse("approvals:my_history"),
                ),
                _dashboard_card(
                    "Returned / Rejected Items",
                    ApprovalTask.objects.filter(
                        status__in=[ApprovalTaskStatus.RETURNED, ApprovalTaskStatus.REJECTED],
                        acted_by=user,
                    ).count(),
                    reverse("approvals:my_history"),
                ),
            ],
            secondary=True,
        ),
        _dashboard_section(
            "My Requests / My Recent Activity",
            [
                _dashboard_card(
                    "My Draft Requests",
                    requester_purchase.filter(status=RequestStatus.DRAFT).count()
                    + requester_travel.filter(status=TravelRequestStatus.DRAFT).count(),
                    reverse("purchase:pr_list") + "?status=DRAFT",
                    description="Draft PR/TR items you can continue.",
                ),
                _dashboard_card(
                    "Pending Approval",
                    requester_purchase.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.PENDING]).count()
                    + requester_travel.filter(status=TravelRequestStatus.PENDING_APPROVAL).count(),
                    reverse("purchase:pr_list") + "?status=PENDING",
                    description="Requests currently waiting for approval.",
                ),
                _dashboard_card(
                    "Approved Not Closed",
                    requester_purchase.filter(status=RequestStatus.APPROVED).count()
                    + requester_travel.filter(
                        status__in=[
                            TravelRequestStatus.APPROVED,
                            TravelRequestStatus.IN_TRIP,
                            TravelRequestStatus.EXPENSE_PENDING,
                            TravelRequestStatus.EXPENSE_SUBMITTED,
                        ]
                    ).count(),
                    reverse("purchase:pr_list") + "?status=APPROVED",
                    description="Approved requests still open.",
                ),
                _dashboard_card("Create Purchase Request", "+", reverse("purchase:pr_create"), tone="action"),
                _dashboard_card("Create Travel Request", "+", reverse("travel:tr_create"), tone="action"),
            ],
            secondary=True,
        ),
    ]

    if user.is_staff:
        sections.append(
            _dashboard_section(
                "Team / Department / Finance Oversight",
                [
                    _dashboard_card("Pending Accounting Reviews", open_reviews.count(), reverse("finance:accounting_review_queue"), tone="attention"),
                    _dashboard_card(
                        "Missing Receipt Items",
                        open_reviews.filter(reason=AccountingReviewReason.MISSING_RECEIPT).count(),
                        reverse("finance:accounting_review_queue") + "?tab=missing_receipt",
                        tone="warning",
                    ),
                    _dashboard_card(
                        "Over-Budget Reviews",
                        open_reviews.filter(reason=AccountingReviewReason.OVER_BUDGET).count(),
                        reverse("finance:accounting_review_queue") + "?tab=over_budget",
                        tone="attention",
                    ),
                    _dashboard_card(
                        "Amendment Required Items",
                        open_reviews.filter(policy_action=OverBudgetAction.AMENDMENT_REQUIRED).count(),
                        reverse("finance:accounting_review_queue") + "?tab=amendment",
                        tone="danger",
                    ),
                    _dashboard_card("Unmatched Card Transactions", unmatched_cards.count(), reverse("finance:card_transaction_list") + "?status=UNMATCHED"),
                    _dashboard_card(
                        "Duplicate Card Reviews",
                        open_reviews.filter(reason=AccountingReviewReason.DUPLICATE_CARD).count(),
                        reverse("finance:accounting_review_queue") + "?tab=duplicate_card",
                    ),
                    _dashboard_card(
                        "Requests Ready to Close",
                        PurchaseRequest.objects.filter(status=RequestStatus.APPROVED).count()
                        + TravelRequest.objects.filter(
                            status__in=[
                                TravelRequestStatus.APPROVED,
                                TravelRequestStatus.EXPENSE_PENDING,
                                TravelRequestStatus.EXPENSE_SUBMITTED,
                            ]
                        ).count(),
                        reverse("purchase:pr_list") + "?status=APPROVED",
                    ),
                ],
                secondary=True,
            )
        )
        sections.append(
            _dashboard_section(
                "Admin / Setup Shortcuts",
                [
                    _dashboard_card(
                        "Open Review Aging",
                        open_reviews.filter(created_at__lte=now - timedelta(days=8)).count(),
                        reverse("finance:accounting_review_queue") + "?tab=pending&min_age_days=8",
                        tone="danger",
                    ),
                    _dashboard_card("Projects Near Budget Limit", _projects_near_budget_limit_count(), reverse("finance:finance_reports")),
                    _dashboard_card("Over-Budget Exceptions", open_reviews.filter(reason=AccountingReviewReason.OVER_BUDGET).count(), reverse("finance:accounting_review_queue") + "?tab=over_budget"),
                    _dashboard_card("Unmatched Card Count", unmatched_cards.count(), reverse("finance:card_transaction_list") + "?status=UNMATCHED"),
                    _dashboard_card("Receipt Policy Issues", open_reviews.filter(reason=AccountingReviewReason.MISSING_RECEIPT).count(), reverse("finance:accounting_review_queue") + "?tab=missing_receipt"),
                    _dashboard_card("Finance Reports", "Open", reverse("finance:finance_reports"), tone="action"),
                    _dashboard_card("Policy Setup", "Open", reverse("finance:over_budget_policy_list"), tone="action"),
                ],
                secondary=True,
                collapsible=True,
            )
        )

    if user.is_superuser:
        sections.append(
            _dashboard_section(
                "System Admin",
                [
                    _dashboard_card("User / Department Setup", "Open", reverse("accounts:department_list"), tone="action"),
                    _dashboard_card("Approval Rule Setup", "Open", reverse("approvals:rule_list"), tone="action"),
                    _dashboard_card("Finance Policy Setup", "Open", reverse("finance:over_budget_policy_list"), tone="action"),
                    _dashboard_card("System Notes", "No feed", reverse("admin:index")),
                ],
                secondary=True,
                collapsible=True,
            )
        )

    return [section for section in sections if section["cards"]]


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
        "can_create_project": user_can_create_project(request.user),
        "approval_summary": get_approval_summary_for_user(request.user),
        "dashboard_sections": _build_role_dashboard_sections(request.user),
    }
    return render(request, "dashboard/home.html", context)
