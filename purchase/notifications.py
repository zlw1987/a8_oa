from django.conf import settings
from django.core.mail import send_mail

from common.choices import ApprovalTaskStatus


def _unique_email_list(emails):
    result = []
    seen = set()

    for email in emails:
        value = (email or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)

    return result


def _send_notification(subject, body, recipients):
    recipient_list = _unique_email_list(recipients)
    if not recipient_list:
        return 0

    return send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )


def _base_url():
    return (
        getattr(settings, "APP_BASE_URL", "")
        or getattr(settings, "SITE_BASE_URL", "")
        or ""
    ).rstrip("/")


def _build_absolute_url(path):
    base = _base_url()
    if not base or not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _purchase_detail_url(purchase_request):
    return _build_absolute_url(f"/purchase/{purchase_request.id}/")


def _travel_detail_url(travel_request):
    return _build_absolute_url(f"/travel/{travel_request.id}/")


def _task_assignment_label(task):
    if not task:
        return "-"

    if str(task.status) == str(ApprovalTaskStatus.POOL):
        return "Pool task - waiting for a candidate to claim"

    assigned_user = getattr(task, "assigned_user", None)
    if assigned_user:
        return f"Assigned to {assigned_user}"

    return "-"


def _request_common_lines(request_obj):
    matched_rule = getattr(request_obj, "matched_rule", None)
    matched_rule_text = (
        f"{matched_rule.rule_code} - {matched_rule.rule_name}"
        if matched_rule and getattr(matched_rule, "rule_code", None)
        else "-"
    )

    return [
        f"Request No: {getattr(request_obj, 'pr_no', getattr(request_obj, 'travel_no', '-'))}",
        f"Title/Purpose: {getattr(request_obj, 'title', getattr(request_obj, 'purpose', '-'))}",
        f"Status: {request_obj.get_status_display()}",
        f"Project: {getattr(request_obj, 'project', '-')}",
        f"Amount: {getattr(request_obj, 'currency', '')} {getattr(request_obj, 'estimated_total', '')}",
        f"Matched Approval Rule: {matched_rule_text}",
    ]


def notify_pr_submitted(purchase_request):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _purchase_detail_url(purchase_request)

    lines = _request_common_lines(purchase_request)
    lines.extend(
        [
            "",
            "Your purchase request has been submitted successfully.",
            "Next step: wait for the current approval task to be claimed or reviewed.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {purchase_request.pr_no} submitted"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_current_task_activated(task):
    request_obj = task.get_request_object()
    if not request_obj:
        return 0

    if task.status == ApprovalTaskStatus.POOL:
        recipients = [
            candidate.user.email
            for candidate in task.candidates.select_related("user").filter(is_active=True)
            if candidate.user and candidate.user.email
        ]
        action_text = "This task is in the approval pool. Claim it if you will handle it."
    elif task.status == ApprovalTaskStatus.PENDING and task.assigned_user and task.assigned_user.email:
        recipients = [task.assigned_user.email]
        action_text = "This task is assigned to you. Please review and take action."
    else:
        recipients = []

    if hasattr(request_obj, "pr_no"):
        detail_url = _purchase_detail_url(request_obj)
    else:
        detail_url = _travel_detail_url(request_obj)

    matched_rule = getattr(request_obj, "matched_rule", None)
    matched_rule_text = (
        f"{matched_rule.rule_code} - {matched_rule.rule_name}"
        if matched_rule and getattr(matched_rule, "rule_code", None)
        else "-"
    )

    subject = f"[OA] Approval needed - {task.request_no} / {task.step_name}"
    body_lines = [
        f"Request No: {task.request_no}",
        f"Title/Purpose: {task.request_title}",
        f"Current Step: {task.step_name}",
        f"Task Status: {task.get_status_display()}",
        f"Task Ownership: {_task_assignment_label(task)}",
        f"Request Amount: {getattr(request_obj, 'currency', '')} {getattr(request_obj, 'estimated_total', '')}",
        f"Matched Approval Rule: {matched_rule_text}",
        "",
        action_text,
    ]

    if detail_url:
        body_lines.extend(["", f"Open Request: {detail_url}"])

    body = "\n".join(body_lines)

    return _send_notification(subject, body, recipients)


def notify_pr_approved(purchase_request):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _purchase_detail_url(purchase_request)

    lines = _request_common_lines(purchase_request)
    lines.extend(
        [
            "",
            "Your purchase request has been fully approved.",
            "Next step: record actual spend when purchasing is completed, then close the request when everything is done.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {purchase_request.pr_no} approved"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_pr_returned(purchase_request, comment=""):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _purchase_detail_url(purchase_request)

    lines = _request_common_lines(purchase_request)
    lines.extend(
        [
            "",
            "Your purchase request was returned for update.",
            f"Approver Comment: {comment or '-'}",
            "Next step: open the request, revise it, and resubmit.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {purchase_request.pr_no} returned"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_pr_rejected(purchase_request, comment=""):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _purchase_detail_url(purchase_request)

    lines = _request_common_lines(purchase_request)
    lines.extend(
        [
            "",
            "Your purchase request was rejected.",
            f"Approver Comment: {comment or '-'}",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {purchase_request.pr_no} rejected"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)