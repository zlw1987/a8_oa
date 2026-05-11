from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from common.choices import BudgetEntryType, RequestStatus
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseRequest
from travel.models import TravelRequest, TravelRequestStatus

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


def _request_currency(request_obj):
    return getattr(request_obj, "currency", "") or getattr(getattr(request_obj, "project", None), "currency", "") or "USD"


def _review_item_currency(item):
    if item.purchase_request_id:
        return _request_currency(item.purchase_request)
    if item.travel_request_id:
        return _request_currency(item.travel_request)
    if item.card_transaction_id:
        return item.card_transaction.currency
    if item.card_allocation_id and item.card_allocation.card_transaction_id:
        return item.card_allocation.card_transaction.currency
    return "USD"


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
                "currency": project.currency,
            }
        )
    return rows


def build_department_spending_summary():
    rows = {}
    for entry in ProjectBudgetEntry.objects.select_related("project__owning_department").filter(
        entry_type=BudgetEntryType.CONSUME
    ):
        department = entry.project.owning_department
        currency = entry.project.currency
        key = (department.id, currency)
        rows.setdefault(key, {"department": department, "currency": currency, "consumed": Decimal("0.00")})
        rows[key]["consumed"] += entry.amount
    return sorted(rows.values(), key=lambda row: (row["department"].dept_code, row["currency"]))


def build_reserved_vs_consumed_summary():
    rows = {}
    for entry in ProjectBudgetEntry.objects.select_related("project"):
        currency = entry.project.currency
        rows.setdefault(
            currency,
            {
                "currency": currency,
                "reserved": Decimal("0.00"),
                "released": Decimal("0.00"),
                "consumed": Decimal("0.00"),
            },
        )
        if entry.entry_type == BudgetEntryType.RESERVE:
            rows[currency]["reserved"] += entry.amount
        elif entry.entry_type == BudgetEntryType.RELEASE:
            rows[currency]["released"] += entry.amount
        elif entry.entry_type == BudgetEntryType.CONSUME:
            rows[currency]["consumed"] += entry.amount
    return sorted(rows.values(), key=lambda row: row["currency"])


def build_open_requests_with_remaining_reserve():
    rows = []
    purchase_statuses = [RequestStatus.SUBMITTED, RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.RETURNED]
    for request_obj in PurchaseRequest.objects.select_related("project", "requester").filter(status__in=purchase_statuses):
        remaining = request_obj.get_reserved_remaining_amount()
        if remaining > 0:
            rows.append({"type": "Purchase", "request": request_obj, "remaining": remaining, "currency": _request_currency(request_obj)})
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
            rows.append({"type": "Travel", "request": request_obj, "remaining": remaining, "currency": _request_currency(request_obj)})
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
        item.report_currency = _review_item_currency(item)
    return {
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
