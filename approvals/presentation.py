from approvals.access import get_task_action_flags


def get_task_assignment_label(task):
    if not task:
        return "-"

    if str(task.status) == "POOL":
        return "Pool task - waiting for a candidate to claim"

    assigned_user = getattr(task, "assigned_user", None)
    if assigned_user:
        return f"Assigned to {assigned_user}"

    return "-"


def build_request_workflow_context(request_obj, user):
    current_task = request_obj.get_current_task()

    return {
        "current_task": current_task,
        "current_step": request_obj.get_current_step_name(),
        "current_approver": request_obj.get_current_approver(),
        "approval_progress": request_obj.get_approval_progress_text(),
        "current_task_assignment_label": get_task_assignment_label(current_task),
        **get_task_action_flags(user, current_task),
    }