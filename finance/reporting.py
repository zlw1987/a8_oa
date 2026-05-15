from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from common.choices import BudgetEntryType, RequestStatus
from common.currency import COMPANY_BASE_CURRENCY
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseActualSpend, PurchaseRequest
from travel.models import TravelActualExpenseLine, TravelRequest, TravelRequestStatus

from .models import (
    AccountingReviewItem,
    AccountingReviewReason,
    AccountingReviewStatus,
    CardTransaction,
    CardTransactionMatchStatus,
)


def _money(value):
    return value or Decimal("0.00")


def _entry_total(project, entry_type):
    return _money(
        ProjectBudgetEntry.objects.filter(project=project, entry_type=entry_type).aggregate(total=Sum("amount"))["total"]
    )


def _review_item_base_currency(item):
    return getattr(item, "base_currency", "") or COMPANY_BASE_CURRENCY


def build_project_budget_summary():
    rows = []
    for project in Project.objects.select_related("owning_department").order_by("project_code"):
        reserved = _entry_total(project, BudgetEntryType.RESERVE)
        consumed = _entry_total(project, BudgetEntryType.CONSUME)
        released = _entry_total(project, BudgetEntryType.RELEASE)
        active_reserved = reserved - released
        effective_budget = project.get_effective_budget_amount()
        rows.append(
            {
                "project": project,
                "budget": effective_budget,
                "reserved": active_reserved,
                "consumed": consumed,
                "available": effective_budget - active_reserved - consumed,
                "currency": COMPANY_BASE_CURRENCY,
            }
        )
    return rows


def build_department_spending_summary():
    rows = {}
    for entry in ProjectBudgetEntry.objects.select_related("project__owning_department").filter(
        entry_type=BudgetEntryType.CONSUME
    ):
        department = entry.project.owning_department
        key = department.id
        rows.setdefault(key, {"department": department, "currency": COMPANY_BASE_CURRENCY, "consumed": Decimal("0.00")})
        rows[key]["consumed"] += entry.amount
    for row in rows.values():
        row["detail_url"] = reverse("finance:department_spending_drilldown", args=[row["department"].id])
    return sorted(rows.values(), key=lambda row: row["department"].dept_code)


def build_department_spending_drilldown(department):
    projects = list(Project.objects.filter(owning_department=department).order_by("project_code"))
    purchase_requests = list(
        PurchaseRequest.objects.select_related("project", "requester")
        .filter(request_department=department)
        .order_by("-request_date", "-id")
    )
    travel_requests = list(
        TravelRequest.objects.select_related("project", "requester")
        .filter(request_department=department)
        .order_by("-request_date", "-id")
    )
    purchase_actuals = list(
        PurchaseActualSpend.objects.select_related("purchase_request", "purchase_request__project", "created_by")
        .filter(purchase_request__request_department=department)
        .order_by("-spend_date", "-id")
    )
    travel_actuals = list(
        TravelActualExpenseLine.objects.select_related("travel_request", "travel_request__project", "created_by")
        .filter(travel_request__request_department=department)
        .order_by("-expense_date", "-id")
    )
    return {
        "department": department,
        "projects": projects,
        "purchase_requests": purchase_requests,
        "travel_requests": travel_requests,
        "purchase_actuals": purchase_actuals,
        "travel_actuals": travel_actuals,
        "consumed_total": sum(
            (project.get_consumed_amount() for project in projects),
            Decimal("0.00"),
        ),
        "currency": COMPANY_BASE_CURRENCY,
    }


def build_reserved_vs_consumed_summary():
    row = {
        "currency": COMPANY_BASE_CURRENCY,
        "reserved": Decimal("0.00"),
        "released": Decimal("0.00"),
        "consumed": Decimal("0.00"),
    }
    for entry in ProjectBudgetEntry.objects.all():
        if entry.entry_type == BudgetEntryType.RESERVE:
            row["reserved"] += entry.amount
        elif entry.entry_type == BudgetEntryType.RELEASE:
            row["released"] += entry.amount
        elif entry.entry_type == BudgetEntryType.CONSUME:
            row["consumed"] += entry.amount
    return row


def build_open_requests_with_remaining_reserve():
    rows = []
    purchase_statuses = [RequestStatus.SUBMITTED, RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.RETURNED]
    for request_obj in PurchaseRequest.objects.select_related("project", "requester").filter(status__in=purchase_statuses):
        remaining = request_obj.get_reserved_remaining_amount()
        if remaining > 0:
            rows.append({"type": "Purchase", "request": request_obj, "remaining": remaining, "currency": COMPANY_BASE_CURRENCY})
    travel_statuses = [
        TravelRequestStatus.PENDING_APPROVAL,
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.IN_TRIP,
        TravelRequestStatus.EXPENSE_PENDING,
        TravelRequestStatus.EXPENSE_SUBMITTED,
        TravelRequestStatus.RETURNED,
    ]
    for request_obj in TravelRequest.objects.select_related("project", "requester").filter(status__in=travel_statuses):
        remaining = request_obj.get_reserved_remaining_amount()
        if remaining > 0:
            rows.append({"type": "Travel", "request": request_obj, "remaining": remaining, "currency": COMPANY_BASE_CURRENCY})
    return rows


def build_accounting_review_aging():
    now = timezone.now()
    rows = []
    for item in AccountingReviewItem.objects.filter(status__in=[AccountingReviewStatus.PENDING_REVIEW, AccountingReviewStatus.RETURNED]).order_by(
        "created_at"
    ):
        rows.append({"item": item, "aging_days": (now - item.created_at).days if item.created_at else 0})
    return rows


def build_finance_report_context():
    over_budget_items = list(
        AccountingReviewItem.objects.select_related(
            "purchase_request",
            "travel_request",
            "card_transaction",
            "card_allocation",
            "card_allocation__card_transaction",
        )
        .filter(reason=AccountingReviewReason.OVER_BUDGET)
        .order_by("-created_at")
    )
    for item in over_budget_items:
        item.report_currency = _review_item_base_currency(item)
        item.report_amount = item.base_amount if item.base_amount is not None else item.amount
    return {
        "base_currency": COMPANY_BASE_CURRENCY,
        "project_budget_rows": build_project_budget_summary(),
        "department_spending_rows": build_department_spending_summary(),
        "reserved_vs_consumed": build_reserved_vs_consumed_summary(),
        "open_reserve_rows": build_open_requests_with_remaining_reserve(),
        "over_budget_items": over_budget_items,
        "unmatched_card_transactions": CardTransaction.objects.filter(
            match_status__in=[CardTransactionMatchStatus.UNMATCHED, CardTransactionMatchStatus.PARTIALLY_MATCHED]
        ).order_by("-transaction_date", "-id"),
        "review_aging_rows": build_accounting_review_aging(),
    }
