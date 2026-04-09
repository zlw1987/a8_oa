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


def notify_pr_submitted(purchase_request):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {purchase_request.pr_no} submitted"
    body = (
        f"Purchase Request: {purchase_request.pr_no}\n"
        f"Title: {purchase_request.title}\n"
        f"Status: {purchase_request.get_status_display()}\n"
        f"Project: {purchase_request.project}\n"
        f"Amount: {purchase_request.currency} {purchase_request.estimated_total}\n\n"
        "Your purchase request has been submitted successfully."
    )

    return _send_notification(subject, body, recipients)


def notify_current_task_activated(task):
    purchase_request = task.purchase_request

    if task.status == ApprovalTaskStatus.POOL:
        recipients = [
            candidate.user.email
            for candidate in task.candidates.select_related("user").filter(is_active=True)
            if candidate.user and candidate.user.email
        ]
        audience_text = "This task is available in the approval pool."
    elif task.status == ApprovalTaskStatus.PENDING and task.assigned_user and task.assigned_user.email:
        recipients = [task.assigned_user.email]
        audience_text = "This task is assigned to you."
    else:
        recipients = []

    subject = f"[OA] Approval needed - {purchase_request.pr_no} / {task.step_name}"
    body = (
        f"Purchase Request: {purchase_request.pr_no}\n"
        f"Title: {purchase_request.title}\n"
        f"Current Step: {task.step_name}\n"
        f"Task Status: {task.get_status_display()}\n"
        f"Request Amount: {purchase_request.currency} {purchase_request.estimated_total}\n\n"
        f"{audience_text}"
    )

    return _send_notification(subject, body, recipients)


def notify_pr_approved(purchase_request):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {purchase_request.pr_no} approved"
    body = (
        f"Purchase Request: {purchase_request.pr_no}\n"
        f"Title: {purchase_request.title}\n"
        f"Status: {purchase_request.get_status_display()}\n\n"
        "Your purchase request has been fully approved."
    )

    return _send_notification(subject, body, recipients)


def notify_pr_returned(purchase_request, comment=""):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {purchase_request.pr_no} returned"
    body = (
        f"Purchase Request: {purchase_request.pr_no}\n"
        f"Title: {purchase_request.title}\n"
        f"Status: {purchase_request.get_status_display()}\n\n"
        "Your purchase request was returned for update.\n"
        f"Comment: {comment or '-'}"
    )

    return _send_notification(subject, body, recipients)


def notify_pr_rejected(purchase_request, comment=""):
    requester = purchase_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {purchase_request.pr_no} rejected"
    body = (
        f"Purchase Request: {purchase_request.pr_no}\n"
        f"Title: {purchase_request.title}\n"
        f"Status: {purchase_request.get_status_display()}\n\n"
        "Your purchase request was rejected.\n"
        f"Comment: {comment or '-'}"
    )

    return _send_notification(subject, body, recipients)