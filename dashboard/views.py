from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from approvals.models import ApprovalTask
from common.choices import ApprovalTaskStatus, RequestStatus
from purchase.models import PurchaseRequest
from travel.models import TravelRequest, TravelRequestStatus
from accounts.models import Department
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
from projects.models import DepartmentGeneralProject, Project
from projects.access import user_can_create_project
from common.currency import COMPANY_BASE_CURRENCY
from common.permissions import ROLE_PERMISSION_MATRIX, can_view_system_setup
from finance.models import Currency, ExchangeRate, FXVariancePolicy, OverBudgetPolicy, ReceiptPolicy
from finance.models import DirectProjectCostPolicy
from approvals.models import ApprovalRule

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
            _("My Work Today"),
            [
                _priority_card(_("Pending Approval Tasks"), assigned_pending.count(), reverse("approvals:my_tasks"), tone="attention"),
                _priority_card(
                    _("Overdue Approval Tasks"),
                    overdue_assigned.count(),
                    reverse("approvals:my_tasks") + "?due_state=overdue",
                    tone="danger",
                ),
                _priority_card(
                    _("Returned to Me"),
                    returned_count,
                    reverse("purchase:pr_list") + "?status=RETURNED",
                    tone="attention",
                    description=_("Requests returned for correction."),
                ),
                _priority_card(
                    _("Missing Receipt / Need Action"),
                    missing_receipt_count,
                    reverse("purchase:pr_list"),
                    tone="warning",
                    description=_("Receipt issues connected to your requests."),
                ),
                _priority_card(
                    _("Pending Accounting Reviews"),
                    open_reviews.count() if user.is_staff else 0,
                    reverse("finance:accounting_review_queue") if user.is_staff else "",
                    tone="attention",
                ),
                _priority_card(
                    _("Unmatched Card Transactions"),
                    unmatched_cards.count() if user.is_staff else 0,
                    reverse("finance:card_transaction_list") + "?status=UNMATCHED" if user.is_staff else "",
                    tone="warning",
                ),
            ],
        ),
        _dashboard_section(
            _("Approval Summary"),
            [
                _dashboard_card(_("My Pending Approval Tasks"), assigned_pending.count(), reverse("approvals:my_tasks")),
                _dashboard_card(_("Claimable Pool Tasks"), pool_pending.count(), reverse("approvals:my_tasks")),
                _dashboard_card(
                    _("Recently Approved"),
                    ApprovalTask.objects.filter(status=ApprovalTaskStatus.APPROVED, acted_by=user).count(),
                    reverse("approvals:my_history"),
                ),
                _dashboard_card(
                    _("Returned / Rejected Items"),
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
            _("My Requests / My Recent Activity"),
            [
                _dashboard_card(
                    _("My Draft Requests"),
                    requester_purchase.filter(status=RequestStatus.DRAFT).count()
                    + requester_travel.filter(status=TravelRequestStatus.DRAFT).count(),
                    reverse("purchase:pr_list") + "?status=DRAFT",
                    description=_("Draft PR/TR items you can continue."),
                ),
                _dashboard_card(
                    _("Pending Approval"),
                    requester_purchase.filter(status__in=[RequestStatus.SUBMITTED, RequestStatus.PENDING]).count()
                    + requester_travel.filter(status=TravelRequestStatus.PENDING_APPROVAL).count(),
                    reverse("purchase:pr_list") + "?status=PENDING",
                    description=_("Requests currently waiting for approval."),
                ),
                _dashboard_card(
                    _("Approved Not Closed"),
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
                    description=_("Approved requests still open."),
                ),
                _dashboard_card(_("Create Purchase Request"), "+", reverse("purchase:pr_create"), tone="action"),
                _dashboard_card(_("Create Travel Request"), "+", reverse("travel:tr_create"), tone="action"),
            ],
            secondary=True,
        ),
    ]

    if user.is_staff:
        sections.append(
            _dashboard_section(
                _("Team / Department / Finance Oversight"),
                [
                    _dashboard_card(_("Pending Accounting Reviews"), open_reviews.count(), reverse("finance:accounting_review_queue"), tone="attention"),
                    _dashboard_card(
                        _("Missing Receipt Items"),
                        open_reviews.filter(reason=AccountingReviewReason.MISSING_RECEIPT).count(),
                        reverse("finance:accounting_review_queue") + "?tab=missing_receipt",
                        tone="warning",
                    ),
                    _dashboard_card(
                        _("Over-Budget Reviews"),
                        open_reviews.filter(reason=AccountingReviewReason.OVER_BUDGET).count(),
                        reverse("finance:accounting_review_queue") + "?tab=over_budget",
                        tone="attention",
                    ),
                    _dashboard_card(
                        _("Amendment Required Items"),
                        open_reviews.filter(policy_action=OverBudgetAction.AMENDMENT_REQUIRED).count(),
                        reverse("finance:accounting_review_queue") + "?tab=amendment",
                        tone="danger",
                    ),
                    _dashboard_card(_("Unmatched Card Transactions"), unmatched_cards.count(), reverse("finance:card_transaction_list") + "?status=UNMATCHED"),
                    _dashboard_card(
                        _("Duplicate Card Reviews"),
                        open_reviews.filter(reason=AccountingReviewReason.DUPLICATE_CARD).count(),
                        reverse("finance:accounting_review_queue") + "?tab=duplicate_card",
                    ),
                    _dashboard_card(
                        _("Requests Ready to Close"),
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
                _("Admin / Setup Shortcuts"),
                [
                    _dashboard_card(
                        _("Open Review Aging"),
                        open_reviews.filter(created_at__lte=now - timedelta(days=8)).count(),
                        reverse("finance:accounting_review_queue") + "?tab=pending&min_age_days=8",
                        tone="danger",
                    ),
                    _dashboard_card(_("Projects Near Budget Limit"), _projects_near_budget_limit_count(), reverse("finance:finance_reports")),
                    _dashboard_card(_("Over-Budget Exceptions"), open_reviews.filter(reason=AccountingReviewReason.OVER_BUDGET).count(), reverse("finance:accounting_review_queue") + "?tab=over_budget"),
                    _dashboard_card(_("Unmatched Card Count"), unmatched_cards.count(), reverse("finance:card_transaction_list") + "?status=UNMATCHED"),
                    _dashboard_card(_("Receipt Policy Issues"), open_reviews.filter(reason=AccountingReviewReason.MISSING_RECEIPT).count(), reverse("finance:accounting_review_queue") + "?tab=missing_receipt"),
                    _dashboard_card(_("Finance Reports"), _("Open"), reverse("finance:finance_reports"), tone="action"),
                    _dashboard_card(_("Policy Setup"), _("Open"), reverse("finance:over_budget_policy_list"), tone="action"),
                ],
                secondary=True,
                collapsible=True,
            )
        )

    if user.is_superuser:
        sections.append(
            _dashboard_section(
                _("System Admin"),
                [
                    _dashboard_card(_("User / Department Setup"), _("Open"), reverse("accounts:department_list"), tone="action"),
                    _dashboard_card(_("Approval Rule Setup"), _("Open"), reverse("approvals:rule_list"), tone="action"),
                    _dashboard_card(_("Finance Policy Setup"), _("Open"), reverse("finance:over_budget_policy_list"), tone="action"),
                    _dashboard_card(_("System Notes"), _("No feed"), reverse("admin:index")),
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


def _setup_card(label, value, url="", tone="neutral", description=""):
    return {
        "label": label,
        "value": value,
        "url": url,
        "tone": tone,
        "description": description,
    }


def _admin_changelist_url(model):
    meta = model._meta
    return reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")


@login_required
def system_setup(request):
    if not can_view_system_setup(request.user):
        raise PermissionDenied("You do not have permission to view System Setup.")

    active_currencies = list(Currency.objects.filter(is_active=True).order_by("code").values_list("code", flat=True))
    current_year = timezone.localdate().year
    active_departments = Department.objects.filter(is_active=True)
    configured_department_ids = DepartmentGeneralProject.objects.filter(
        fiscal_year=current_year,
        is_active=True,
    ).values_list("department_id", flat=True)
    missing_general_budget_count = active_departments.exclude(id__in=configured_department_ids).count()
    setup_cards = [
        _setup_card(_("Base Currency"), COMPANY_BASE_CURRENCY, description=_("Used for budget control and finance reports.")),
        _setup_card(_("Active Currencies"), ", ".join(active_currencies) if active_currencies else _("Not configured"), tone="warning" if not active_currencies else "neutral"),
        _setup_card(
            _("Dept General Budgets"),
            _("Complete") if missing_general_budget_count == 0 else _("%(count)s missing") % {"count": missing_general_budget_count},
            reverse("projects:department_general_project_list"),
            tone="warning" if missing_general_budget_count else "neutral",
            description=_("Fiscal year %(year)s setup coverage.") % {"year": current_year},
        ),
        _setup_card(_("Departments"), Department.objects.count(), reverse("accounts:department_list")),
        _setup_card(_("Projects"), Project.objects.count(), reverse("projects:project_list")),
        _setup_card(_("Approval Rules"), ApprovalRule.objects.filter(is_active=True).count(), reverse("approvals:rule_list")),
        _setup_card(_("Over-Budget Policies"), OverBudgetPolicy.objects.filter(is_active=True).count(), reverse("finance:over_budget_policy_list")),
        _setup_card(_("Receipt Policies"), ReceiptPolicy.objects.filter(is_active=True).count(), reverse("finance:receipt_policy_list")),
        _setup_card(_("Direct Project Cost Policies"), DirectProjectCostPolicy.objects.filter(is_active=True).count(), reverse("finance:direct_project_cost_policy_list")),
        _setup_card(_("Accounting Periods"), _("Month-End Close"), reverse("finance:accounting_period_list")),
        _setup_card(_("FX Variance Policies"), FXVariancePolicy.objects.filter(is_active=True).count(), reverse("finance:fx_variance_policy_list")),
        _setup_card(_("Exchange Rates"), ExchangeRate.objects.count(), reverse("finance:exchange_rate_list")),
        _setup_card(_("Current Version"), "V1.1 Phase 3", reverse("dashboard:system_setup")),
        _setup_card(_("Seed Finance Defaults"), _("Manual command"), "", description=_("Run seed_finance_defaults from the server when setup data needs to be refreshed.")),
        _setup_card(_("Static / Media Check"), _("Review deployment"), "", description=_("Confirm static and media paths during deployment checklist.")),
    ]
    user_model = get_user_model()
    setup_sections = [
        {
            "title": _("User & Permission Setup"),
            "links": [
                  {"label": _("Departments"), "url": reverse("accounts:department_list")},
                  {"label": _("Projects"), "url": reverse("projects:project_list")},
                  {"label": _("Department General Budgets"), "url": reverse("projects:department_general_project_list")},
                  {"label": _("Django Admin Users"), "url": _admin_changelist_url(user_model)},
                {"label": _("Django Admin Groups"), "url": reverse("admin:auth_group_changelist")},
            ],
        },
        {
            "title": _("Approval And Finance Policy"),
            "links": [
                {"label": _("Approval Rules"), "url": reverse("approvals:rule_list")},
                {"label": _("Over-Budget Policies"), "url": reverse("finance:over_budget_policy_list")},
                {"label": _("Receipt Policies"), "url": reverse("finance:receipt_policy_list")},
                {"label": _("Direct Project Cost Policies"), "url": reverse("finance:direct_project_cost_policy_list")},
                  {"label": _("FX Variance Policies"), "url": reverse("finance:fx_variance_policy_list")},
                  {"label": _("Accounting Periods"), "url": reverse("finance:accounting_period_list")},
              ],
          },
          {
              "title": _("Currency And Exchange Rates"),
              "links": [
                  {"label": _("Currencies"), "url": reverse("finance:currency_list")},
                  {"label": _("Exchange Rates"), "url": reverse("finance:exchange_rate_list")},
              ],
          },
        {
            "title": _("System Health"),
            "links": [
                {"label": _("Finance Reports"), "url": reverse("finance:finance_reports")},
                {"label": _("Django Admin"), "url": reverse("admin:index")},
            ],
        },
    ]
    return render(
        request,
        "dashboard/system_setup.html",
        {
            "setup_cards": setup_cards,
            "setup_sections": setup_sections,
            "role_permission_matrix": ROLE_PERMISSION_MATRIX,
        },
    )
