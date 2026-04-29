from datetime import date

from approvals.access import get_task_action_flags
from purchase.access import (
    user_can_edit_purchase,
    user_can_submit_purchase,
    user_can_cancel_purchase,
    user_can_close_purchase,
    user_can_record_actual_spend,
)


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