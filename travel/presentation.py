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
from .access import (
    user_can_edit_travel,
    user_can_submit_travel,
    user_can_cancel_travel,
    user_can_close_travel,
    user_can_record_actual_expense_travel,
    user_can_manage_travel_attachment,
)
from .models import TravelRequestStatus


def get_travel_status_badge_class(status):
    mapping = {
        TravelRequestStatus.DRAFT: "badge-neutral",
        TravelRequestStatus.PENDING_APPROVAL: "badge-warning",
        TravelRequestStatus.APPROVED: "badge-success",
        TravelRequestStatus.RETURNED: "badge-info",
        TravelRequestStatus.REJECTED: "badge-danger",
        TravelRequestStatus.IN_TRIP: "badge-info",
        TravelRequestStatus.EXPENSE_PENDING: "badge-warning",
        TravelRequestStatus.EXPENSE_SUBMITTED: "badge-warning",
        TravelRequestStatus.CLOSED: "badge-dark",
        TravelRequestStatus.CANCELLED: "badge-dark",
    }
    return mapping.get(status, "badge-neutral")


def decorate_travel_list_item(tr, user):
    tr.current_step = tr.get_current_step_name()
    tr.current_approver = tr.get_current_approver()
    tr.approval_progress = tr.get_approval_progress_text()
    tr.can_edit = user_can_edit_travel(user, tr)
    tr.status_badge_class = get_travel_status_badge_class(tr.status)
    return tr


def build_travel_detail_ui_flags(tr, user, current_task):
    can_edit = user_can_edit_travel(user, tr)
    can_submit = user_can_submit_travel(user, tr)
    can_cancel = user_can_cancel_travel(user, tr)
    can_close = user_can_close_travel(user, tr)
    can_record_actual_expense = user_can_record_actual_expense_travel(user, tr)
    can_manage_attachments = user_can_manage_travel_attachment(user, tr)

    task_flags = get_task_action_flags(user, current_task)

    return {
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_cancel": can_cancel,
        "can_close": can_close,
        "can_record_actual_expense": can_record_actual_expense,
        "can_manage_attachments": can_manage_attachments,
        "show_attachment_form": can_manage_attachments,
        "show_actual_expense_form": can_record_actual_expense,
        "actual_expense_initial": {
            "expense_date": tr.end_date,
            "currency": tr.currency,
        },
        **task_flags,
    }


def _open_supplemental_requests(tr):
    open_statuses = [
        TravelRequestStatus.DRAFT,
        TravelRequestStatus.PENDING_APPROVAL,
        TravelRequestStatus.RETURNED,
    ]
    return tr.supplemental_requests.filter(status__in=open_statuses).order_by("-request_date", "-id")


def build_travel_detail_header(tr, workflow_ui):
    return {
        "request_label": "Travel Request",
        "request_no": tr.travel_no,
        "request_title": tr.purpose,
        "request_status": tr.get_status_display(),
        "status_tone": get_status_badge_tone(tr.status),
        "requester": tr.requester,
        "request_department": tr.request_department,
        "project": tr.project,
        "request_date": tr.request_date,
        "current_owner": workflow_ui["current_task_assignment_label"] or workflow_ui["current_approver"] or "-",
        "current_step": workflow_ui["current_step"],
        "matched_rule": tr.matched_rule,
        "approval_progress": workflow_ui["approval_progress"],
        "request_currency": tr.currency,
        "request_amount": tr.estimated_total,
        "extra_rows": [
            {"label": "Destination", "value": tr.destination_city},
            {"label": "Start Date", "value": tr.start_date},
            {"label": "End Date", "value": tr.end_date},
        ],
    }


def build_travel_financial_summary(tr):
    requested_amount = tr.estimated_total
    approved_amount = tr.estimated_total if tr.status in [
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.IN_TRIP,
        TravelRequestStatus.EXPENSE_PENDING,
        TravelRequestStatus.EXPENSE_SUBMITTED,
        TravelRequestStatus.CLOSED,
    ] else "-"
    actual_total = tr.actual_total
    remaining_reserve = tr.get_reserved_remaining_amount()
    variance = actual_total - requested_amount
    review_count = unresolved_review_items_for_request(tr).count()

    return [
        build_summary_card("Estimated / Requested", format_money(tr.currency, requested_amount)),
        build_summary_card("Approved Amount", format_money(tr.currency, approved_amount) if approved_amount != "-" else "-"),
        build_summary_card("Actual Spend", format_money(tr.currency, actual_total), "success" if actual_total <= requested_amount else "attention"),
        build_summary_card("Remaining Reserve", format_money(tr.currency, remaining_reserve)),
        build_summary_card(
            "Variance",
            format_money(tr.currency, variance),
            "attention" if variance > 0 else "success",
            "Over approved amount" if variance > 0 else "Within approved amount",
        ),
        build_summary_card("Open Issues", review_count, "danger" if review_count else "success"),
    ]


def build_travel_closeout_checklist(tr, current_task=None):
    closable_statuses = [
        TravelRequestStatus.APPROVED,
        TravelRequestStatus.EXPENSE_PENDING,
        TravelRequestStatus.EXPENSE_SUBMITTED,
    ]
    unresolved_reviews = list(unresolved_review_items_for_request(tr))
    open_supplementals = list(_open_supplemental_requests(tr))
    actual_total = tr.actual_total

    return [
        build_checklist_item(
            "Request approved",
            tr.status in closable_statuses,
            f"Current status is {tr.get_status_display()}." if tr.status not in closable_statuses else "",
        ),
        build_checklist_item(
            "Actual expense recorded",
            actual_total > 0,
            "No actual travel expense has been recorded." if actual_total <= 0 else "",
        ),
        build_checklist_item(
            "Per diem calculated",
            tr.per_diem_allowed_total >= 0,
            "",
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
            reverse("travel:tr_detail", args=[open_supplementals[0].id]) if open_supplementals else "",
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


def build_travel_open_issues(tr, current_task=None):
    issues = []
    for item in unresolved_review_items_for_request(tr):
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

    for amendment in _open_supplemental_requests(tr):
        issues.append(
            build_open_issue(
                "Open Supplemental Request",
                "AMENDMENT_REQUIRED",
                f"{amendment.travel_no} is still {amendment.get_status_display()}.",
                amendment.requester,
                reverse("travel:tr_detail", args=[amendment.id]),
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


def build_travel_available_actions(tr, user, ui_flags, checklist):
    close_reason = get_first_failed_checklist_reason(checklist)
    can_close = ui_flags["can_close"] and not close_reason
    return [
        build_action_state("Back to List", True, url=reverse("travel:tr_list")),
        build_action_state(
            "Open Project Budget Ledger",
            bool(tr.project_id),
            "No project is linked.",
            reverse("projects:project_budget_ledger", args=[tr.project_id]) if tr.project_id else "",
        ),
        build_action_state(
            "Edit Request",
            ui_flags["can_edit"],
            "Only draft or returned travel requests can be edited by the requester.",
            reverse("travel:tr_edit", args=[tr.id]),
        ),
        build_action_state(
            "Submit",
            ui_flags["can_submit"],
            "Only draft or returned travel requests can be submitted.",
            reverse("travel:tr_submit", args=[tr.id]),
            method="post",
            style="primary",
        ),
        build_action_state(
            "Record Actual Expense",
            ui_flags["can_record_actual_expense"],
            "Actual expenses can be recorded after approval or during the expense phase.",
            "#actual-expenses",
        ),
        build_action_state(
            "Create Supplemental Request",
            tr.pending_overage_amount > 0,
            "No pending overage amount requires an amendment.",
            reverse("travel:tr_create_supplemental", args=[tr.id]),
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
            "Only pending or approved travel requests can be cancelled by an allowed user.",
            reverse("travel:tr_cancel", args=[tr.id]),
            method="post",
        ),
    ]
