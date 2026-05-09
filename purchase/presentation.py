from datetime import date

from django.urls import reverse

from approvals.access import get_task_action_flags
from common.presentation import (
    build_action_state,
    build_checklist_item,
    build_open_issue,
    build_summary_card,
    format_money,
    get_status_badge_tone,
)
from finance.models import AccountingReviewReason
from finance.services import unresolved_review_items_for_request
from purchase.access import (
    user_can_edit_purchase,
    user_can_submit_purchase,
    user_can_cancel_purchase,
    user_can_close_purchase,
    user_can_record_actual_spend,
)
from common.choices import RequestStatus


def get_purchase_status_badge_class(status, request_status_cls):
    mapping = {
        request_status_cls.DRAFT: "badge-neutral",
        request_status_cls.SUBMITTED: "badge-warning",
        request_status_cls.PENDING: "badge-warning",
        request_status_cls.APPROVED: "badge-success",
        request_status_cls.REJECTED: "badge-danger",
        request_status_cls.RETURNED: "badge-info",
        request_status_cls.CANCELLED: "badge-dark",
        request_status_cls.CLOSED: "badge-dark",
    }
    return mapping.get(status, "badge-neutral")


def decorate_purchase_list_item(pr, user, request_status_cls):
    pr.current_step = pr.get_current_step_name()
    pr.current_approver = pr.get_current_approver()
    pr.approval_progress = pr.get_approval_progress_text()
    pr.can_edit = user_can_edit_purchase(user, pr)
    pr.status_badge_class = get_purchase_status_badge_class(pr.status, request_status_cls)
    return pr


def build_purchase_detail_ui_flags(pr, user, current_task):
    can_edit = user_can_edit_purchase(user, pr)
    can_submit = user_can_submit_purchase(user, pr)
    can_cancel = user_can_cancel_purchase(user, pr)
    can_close = user_can_close_purchase(user, pr)
    can_record_actual_spend = user_can_record_actual_spend(user, pr)

    task_flags = get_task_action_flags(user, current_task)

    return {
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_cancel": can_cancel,
        "can_close_purchase": can_close,
        "can_record_actual_spend": can_record_actual_spend,
        "can_manage_attachments": can_edit,
        "show_attachment_form": can_edit,
        "show_actual_spend_form": can_record_actual_spend,
        "actual_spend_initial": {"spend_date": date.today()},
        **task_flags,
    }


def _open_supplemental_requests(pr):
    open_statuses = [
        RequestStatus.DRAFT,
        RequestStatus.SUBMITTED,
        RequestStatus.PENDING,
        RequestStatus.RETURNED,
    ]
    return pr.supplemental_requests.filter(status__in=open_statuses).order_by("-request_date", "-id")


def build_purchase_detail_header(pr, workflow_ui):
    return {
        "request_label": "Purchase Request",
        "request_no": pr.pr_no,
        "request_title": pr.title,
        "request_status": pr.get_status_display(),
        "status_tone": get_status_badge_tone(pr.status),
        "requester": pr.requester,
        "request_department": pr.request_department,
        "project": pr.project,
        "request_date": pr.request_date,
        "current_owner": workflow_ui["current_task_assignment_label"] or workflow_ui["current_approver"] or "-",
        "current_step": workflow_ui["current_step"],
        "matched_rule": pr.matched_rule,
        "approval_progress": workflow_ui["approval_progress"],
        "request_currency": pr.currency,
        "request_amount": pr.estimated_total,
        "extra_rows": [
            {"label": "Needed By Date", "value": pr.needed_by_date or "-"},
            {"label": "Vendor Suggestion", "value": pr.vendor_suggestion or "-"},
        ],
    }


def build_purchase_financial_summary(pr):
    requested_amount = pr.estimated_total
    approved_amount = pr.estimated_total if pr.status in [RequestStatus.APPROVED, RequestStatus.CLOSED] else "-"
    actual_total = pr.get_actual_spent_total()
    remaining_reserve = pr.get_reserved_remaining_amount()
    variance = actual_total - requested_amount
    review_count = unresolved_review_items_for_request(pr).count()

    return [
        build_summary_card("Estimated / Requested", format_money(pr.currency, requested_amount)),
        build_summary_card("Approved Amount", format_money(pr.currency, approved_amount) if approved_amount != "-" else "-"),
        build_summary_card("Actual Spend", format_money(pr.currency, actual_total), "success" if actual_total <= requested_amount else "attention"),
        build_summary_card("Remaining Reserve", format_money(pr.currency, remaining_reserve)),
        build_summary_card(
            "Variance",
            format_money(pr.currency, variance),
            "attention" if variance > 0 else "success",
            "Over approved amount" if variance > 0 else "Within approved amount",
        ),
        build_summary_card("Open Issues", review_count, "danger" if review_count else "success"),
    ]


def build_purchase_closeout_checklist(pr, current_task=None):
    unresolved_reviews = list(unresolved_review_items_for_request(pr))
    open_supplementals = list(_open_supplemental_requests(pr))
    actual_total = pr.get_actual_spent_total()

    return [
        build_checklist_item(
            "Request approved",
            pr.status == RequestStatus.APPROVED,
            f"Current status is {pr.get_status_display()}." if pr.status != RequestStatus.APPROVED else "",
        ),
        build_checklist_item(
            "Actual expense recorded",
            actual_total > 0,
            "No actual spend has been recorded." if actual_total <= 0 else "",
        ),
        build_checklist_item(
            "No unresolved Accounting Review Item",
            not unresolved_reviews,
            f"{len(unresolved_reviews)} unresolved review item exists." if len(unresolved_reviews) == 1 else f"{len(unresolved_reviews)} unresolved review items exist." if unresolved_reviews else "",
            reverse("finance:accounting_review_queue") if unresolved_reviews else "",
        ),
        build_checklist_item(
            "No open amendment",
            not open_supplementals,
            f"{len(open_supplementals)} supplemental request is still open." if len(open_supplementals) == 1 else f"{len(open_supplementals)} supplemental requests are still open." if open_supplementals else "",
            reverse("purchase:pr_detail", args=[open_supplementals[0].id]) if open_supplementals else "",
        ),
        build_checklist_item(
            "No open approval task",
            current_task is None,
            "An approval task is still active." if current_task else "",
        ),
    ]


def get_first_failed_checklist_reason(checklist):
    for item in checklist:
        if not item["passed"]:
            return item["detail"] or item["label"]
    return ""


def build_purchase_open_issues(pr, current_task=None):
    issues = []
    for item in unresolved_review_items_for_request(pr):
        severity = "REVIEW"
        if item.reason == AccountingReviewReason.MISSING_RECEIPT:
            issue_type = "Missing Receipt"
            owner = "Accounting / Requester"
        elif item.reason == AccountingReviewReason.OVER_BUDGET:
            issue_type = "Over-Budget Review"
            owner = "Accounting"
        else:
            issue_type = item.get_reason_display()
            owner = "Accounting"
        issues.append(
            build_open_issue(
                issue_type,
                severity,
                item.title or item.description or item.get_reason_display(),
                owner,
                reverse("finance:accounting_review_queue"),
            )
        )

    for amendment in _open_supplemental_requests(pr):
        issues.append(
            build_open_issue(
                "Open Supplemental Request",
                "AMENDMENT_REQUIRED",
                f"{amendment.pr_no} is still {amendment.get_status_display()}.",
                amendment.requester,
                reverse("purchase:pr_detail", args=[amendment.id]),
            )
        )

    if current_task and getattr(current_task, "is_overdue", False):
        issues.append(
            build_open_issue(
                "Overdue Approval Task",
                "WARNING",
                f"{current_task.step_name} is overdue.",
                current_task.assigned_user or "Approval pool",
            )
        )

    return issues


def build_purchase_available_actions(pr, user, ui_flags, checklist):
    close_reason = get_first_failed_checklist_reason(checklist)
    can_close = ui_flags["can_close_purchase"] and not close_reason
    return [
        build_action_state("Back to List", True, url=reverse("purchase:pr_list")),
        build_action_state(
            "Open Project Budget Ledger",
            bool(pr.project_id),
            "No project is linked.",
            reverse("projects:project_budget_ledger", args=[pr.project_id]) if pr.project_id else "",
        ),
        build_action_state(
            "Edit Request",
            ui_flags["can_edit"],
            "Only draft or returned requests can be edited by the requester.",
            reverse("purchase:pr_edit", args=[pr.id]),
        ),
        build_action_state(
            "Submit",
            ui_flags["can_submit"],
            "Only draft or returned requests can be submitted.",
            reverse("purchase:pr_submit", args=[pr.id]),
            method="post",
            style="primary",
        ),
        build_action_state(
            "Record Actual Spend",
            ui_flags["can_record_actual_spend"],
            "Actual spend can be recorded after approval.",
            "#actual-spending",
        ),
        build_action_state(
            "Create Supplemental Request",
            pr.pending_overage_amount > 0,
            "No pending overage amount requires an amendment.",
            reverse("purchase:pr_create_supplemental", args=[pr.id]),
            method="post",
        ),
        build_action_state(
            "Close Request",
            can_close,
            close_reason or "Close is available when all checklist items pass.",
            "#close-request" if can_close else "",
            style="primary",
        ),
        build_action_state(
            "Cancel",
            ui_flags["can_cancel"],
            "Only submitted, pending, or approved requests can be cancelled by an allowed user.",
            reverse("purchase:pr_cancel", args=[pr.id]),
            method="post",
        ),
    ]
