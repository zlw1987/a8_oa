from datetime import date

from approvals.access import get_task_action_flags
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