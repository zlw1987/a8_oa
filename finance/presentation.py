from django.urls import reverse
from django.utils import timezone

from common.presentation import get_status_badge_tone
from .models import (
    AccountingReviewReason,
    AccountingReviewStatus,
    OverBudgetAction,
)


OPEN_STATUS_FILTER = [
    AccountingReviewStatus.PENDING_REVIEW,
    AccountingReviewStatus.RETURNED,
]


def get_review_aging_bucket(aging_days):
    if aging_days >= 8:
        return {"label": "Aging 8+ days", "tone": "danger"}
    if aging_days >= 3:
        return {"label": "Aging 3-7 days", "tone": "warning"}
    return {"label": "Aging 0-2 days", "tone": "success"}


def get_review_severity(item):
    if item.policy_action in [OverBudgetAction.BLOCK, OverBudgetAction.AMENDMENT_REQUIRED]:
        return {"label": "Critical", "tone": "danger"}
    if item.reason in [AccountingReviewReason.OVER_BUDGET, AccountingReviewReason.DUPLICATE_CARD]:
        return {"label": "High", "tone": "attention"}
    return {"label": "Normal", "tone": "info"}


def get_review_required_action(item):
    if item.reason == AccountingReviewReason.MISSING_RECEIPT:
        return "Upload required receipt/invoice or approve an exception."
    if item.reason == AccountingReviewReason.DUPLICATE_CARD:
        return "Confirm duplicate status and resolve review."
    if item.policy_action == OverBudgetAction.AMENDMENT_REQUIRED:
        return "Create/approve amendment or approve accounting exception."
    if item.reason == AccountingReviewReason.OVER_BUDGET:
        return "Review over-budget exception."
    return "Review and resolve."


def build_review_source_links(item):
    links = []
    if item.purchase_request_id:
        links.append({
            "label": item.purchase_request.pr_no,
            "url": reverse("purchase:pr_detail", args=[item.purchase_request_id]),
        })
    if item.travel_request_id:
        links.append({
            "label": item.travel_request.travel_no,
            "url": reverse("travel:tr_detail", args=[item.travel_request_id]),
        })
    if item.card_transaction_id:
        links.append({
            "label": item.card_transaction.reference_no,
            "url": reverse("finance:card_transaction_detail", args=[item.card_transaction_id]),
        })
    if item.card_allocation_id and item.card_allocation.card_transaction_id:
        links.append({
            "label": f"Allocation {item.card_allocation_id}",
            "url": reverse("finance:card_transaction_detail", args=[item.card_allocation.card_transaction_id]),
        })
    return links


def enrich_review_item(item):
    request_obj = item.purchase_request or item.travel_request
    item.source_request_obj = request_obj
    item.aging_days = (timezone.now() - item.created_at).days if item.created_at else 0
    item.aging_bucket = get_review_aging_bucket(item.aging_days)
    item.severity = get_review_severity(item)
    item.status_tone = get_status_badge_tone(item.status)
    item.reason_tone = get_status_badge_tone(item.reason)
    item.policy_action_tone = get_status_badge_tone(item.policy_action)
    item.required_action_display = get_review_required_action(item)
    item.source_links = build_review_source_links(item)
    item.detail_url = reverse("finance:accounting_review_detail", args=[item.id])
    item.requester_display = getattr(getattr(request_obj, "requester", None), "username", "-") if request_obj else "-"
    item.department_display = getattr(getattr(request_obj, "request_department", None), "dept_name", "-") if request_obj else "-"
    item.project_display = getattr(getattr(request_obj, "project", None), "project_code", "-") if request_obj else "-"
    return item


def enrich_review_items(items):
    for item in items:
        enrich_review_item(item)
    return items


def build_accounting_review_tabs(active_tab, base_url):
    tab_defs = [
        ("pending", "All Pending"),
        ("over_budget", "Over-Budget"),
        ("missing_receipt", "Missing Receipt"),
        ("amendment", "Amendment Required"),
        ("duplicate_card", "Duplicate Card"),
        ("returned", "Returned"),
        ("resolved", "Resolved"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "url": f"{base_url}?tab={key}",
            "active": active_tab == key,
        }
        for key, label in tab_defs
    ]


def apply_accounting_review_tab(queryset, tab):
    if tab == "over_budget":
        return queryset.filter(status__in=OPEN_STATUS_FILTER, reason=AccountingReviewReason.OVER_BUDGET)
    if tab == "missing_receipt":
        return queryset.filter(status__in=OPEN_STATUS_FILTER, reason=AccountingReviewReason.MISSING_RECEIPT)
    if tab == "amendment":
        return queryset.filter(status__in=OPEN_STATUS_FILTER, policy_action=OverBudgetAction.AMENDMENT_REQUIRED)
    if tab == "duplicate_card":
        return queryset.filter(status__in=OPEN_STATUS_FILTER, reason=AccountingReviewReason.DUPLICATE_CARD)
    if tab == "returned":
        return queryset.filter(status=AccountingReviewStatus.RETURNED)
    if tab == "resolved":
        return queryset.exclude(status__in=OPEN_STATUS_FILTER)
    return queryset.filter(status__in=OPEN_STATUS_FILTER)
