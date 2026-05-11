from django.urls import reverse
from django.utils import timezone

from common.presentation import get_status_badge_tone
from .models import (
    AccountingReviewReason,
    AccountingReviewStatus,
    CardTransactionMatchStatus,
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


ACCOUNTING_REVIEW_TAB_DEFS = [
    ("pending", "All Pending"),
    ("over_budget", "Over-Budget"),
    ("missing_receipt", "Missing Receipt"),
    ("amendment", "Amendment Required"),
    ("duplicate_card", "Duplicate Card"),
    ("returned", "Returned"),
    ("resolved", "Resolved"),
]


def build_accounting_review_tabs(active_tab, base_url, counts=None):
    counts = counts or {}
    tabs = []
    for key, label in ACCOUNTING_REVIEW_TAB_DEFS:
        count = counts.get(key)
        display_label = f"{label} ({count})" if count is not None else label
        tabs.append(
            {
                "key": key,
                "label": display_label,
                "url": f"{base_url}?tab={key}",
                "active": active_tab == key,
            }
        )
    return tabs


def build_accounting_review_tab_counts(queryset):
    return {
        key: apply_accounting_review_tab(queryset, key).count()
        for key, _label in ACCOUNTING_REVIEW_TAB_DEFS
    }


def has_active_accounting_review_filters(cleaned_data):
    filter_keys = [
        "q",
        "status",
        "reason",
        "source_type",
        "policy_action",
        "requester",
        "department",
        "project",
        "min_age_days",
    ]
    return any(cleaned_data.get(key) not in [None, ""] for key in filter_keys)


def has_active_advanced_accounting_review_filters(cleaned_data):
    return any(cleaned_data.get(key) not in [None, ""] for key in ["requester", "department", "project", "min_age_days"])


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


def build_card_transaction_summary(transaction):
    allocated_amount = transaction.get_allocated_amount()
    unallocated_amount = transaction.get_unallocated_amount()
    open_review_count = transaction.review_items.filter(status__in=OPEN_STATUS_FILTER).count()
    possible_duplicate = transaction.has_possible_duplicate()
    return {
        "allocated_amount": allocated_amount,
        "unallocated_amount": unallocated_amount,
        "open_review_count": open_review_count,
        "possible_duplicate": possible_duplicate,
        "match_status_tone": get_status_badge_tone(transaction.match_status),
        "cards": [
            {"label": "Transaction Amount", "value": f"{transaction.currency} {transaction.amount}", "tone": "neutral"},
            {"label": "Allocated Amount", "value": f"{transaction.currency} {allocated_amount}", "tone": "success" if allocated_amount else "neutral"},
            {"label": "Unallocated Amount", "value": f"{transaction.currency} {unallocated_amount}", "tone": "danger" if unallocated_amount > 0 else "success"},
            {"label": "Match Status", "value": transaction.get_match_status_display(), "tone": get_status_badge_tone(transaction.match_status)},
            {"label": "Open Reviews", "value": open_review_count, "tone": "danger" if open_review_count else "success"},
            {"label": "Duplicate Warning", "value": "Yes" if possible_duplicate else "No", "tone": "danger" if possible_duplicate else "success"},
        ],
    }


def build_card_review_action(transaction):
    open_review_count = transaction.review_items.filter(status__in=OPEN_STATUS_FILTER).count()
    if transaction.match_status != CardTransactionMatchStatus.MATCHED:
        return {
            "enabled": False,
            "reason": "Cannot mark reviewed until the transaction is fully matched.",
        }
    if open_review_count:
        review_label = "item exists" if open_review_count == 1 else "items exist"
        return {
            "enabled": False,
            "reason": f"Cannot mark reviewed because {open_review_count} unresolved Accounting Review {review_label}.",
        }
    return {"enabled": True, "reason": ""}


def enrich_card_review_items(items):
    for item in items:
        enrich_review_item(item)
    return items
