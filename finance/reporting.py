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


def build_project_budget_summary():
    rows = []
    for project in Project.objects.select_related("owning_department").order_by("project_code"):
        reserved = _entry_total(project, BudgetEntryType.RESERVE)
        consumed = _entry_total(project, BudgetEntryType.CONSUME)
        released = _entry_total(project, BudgetEntryType.RELEASE)
        active_reserved = reserved - released
        rows.append(
            {
                "project": project,
                "budget": project.budget_amount,
                "reserved": active_reserved,
                "consumed": consumed,
                "available": project.budget_amount - active_reserved - consumed,
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
        rows.setdefault(key, {"department": department, "consumed": Decimal("0.00")})
        rows[key]["consumed"] += entry.amount
    return sorted(rows.values(), key=lambda row: row["department"].dept_code)


def build_reserved_vs_consumed_summary():
    return {
        "reserved": _money(ProjectBudgetEntry.objects.filter(entry_type=BudgetEntryType.RESERVE).aggregate(total=Sum("amount"))["total"]),
        "released": _money(ProjectBudgetEntry.objects.filter(entry_type=BudgetEntryType.RELEASE).aggregate(total=Sum("amount"))["total"]),
        "consumed": _money(ProjectBudgetEntry.objects.filter(entry_type=BudgetEntryType.CONSUME).aggregate(total=Sum("amount"))["total"]),
    }


def build_open_requests_with_remaining_reserve():
    rows = []
    purchase_statuses = [RequestStatus.SUBMITTED, RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.RETURNED]
    for request_obj in PurchaseRequest.objects.select_related("project", "requester").filter(status__in=purchase_statuses):
        remaining = request_obj.get_reserved_remaining_amount()
        if remaining > 0:
            rows.append({"type": "Purchase", "request": request_obj, "remaining": remaining})
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
            rows.append({"type": "Travel", "request": request_obj, "remaining": remaining})
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
    return {
        "project_budget_rows": build_project_budget_summary(),
        "department_spending_rows": build_department_spending_summary(),
        "reserved_vs_consumed": build_reserved_vs_consumed_summary(),
        "open_reserve_rows": build_open_requests_with_remaining_reserve(),
        "over_budget_items": AccountingReviewItem.objects.filter(reason=AccountingReviewReason.OVER_BUDGET).order_by("-created_at"),
        "unmatched_card_transactions": CardTransaction.objects.filter(
            match_status__in=[CardTransactionMatchStatus.UNMATCHED, CardTransactionMatchStatus.PARTIALLY_MATCHED]
        ).order_by("-transaction_date", "-id"),
        "review_aging_rows": build_accounting_review_aging(),
    }
