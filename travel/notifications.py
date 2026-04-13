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


def notify_tr_submitted(travel_request):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {travel_request.travel_no} submitted"
    body = (
        f"Travel Request: {travel_request.travel_no}\n"
        f"Purpose: {travel_request.purpose}\n"
        f"Status: {travel_request.get_status_display()}\n"
        f"Project: {travel_request.project}\n"
        f"Estimated Total: {travel_request.currency} {travel_request.estimated_total}\n\n"
        "Your travel request has been submitted successfully."
    )

    return _send_notification(subject, body, recipients)


def notify_tr_approved(travel_request):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {travel_request.travel_no} approved"
    body = (
        f"Travel Request: {travel_request.travel_no}\n"
        f"Purpose: {travel_request.purpose}\n"
        f"Status: {travel_request.get_status_display()}\n\n"
        "Your travel request has been fully approved."
    )

    return _send_notification(subject, body, recipients)


def notify_tr_returned(travel_request, comment=""):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {travel_request.travel_no} returned"
    body = (
        f"Travel Request: {travel_request.travel_no}\n"
        f"Purpose: {travel_request.purpose}\n"
        f"Status: {travel_request.get_status_display()}\n\n"
        "Your travel request was returned for update.\n"
        f"Comment: {comment or '-'}"
    )

    return _send_notification(subject, body, recipients)


def notify_tr_rejected(travel_request, comment=""):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    subject = f"[OA] {travel_request.travel_no} rejected"
    body = (
        f"Travel Request: {travel_request.travel_no}\n"
        f"Purpose: {travel_request.purpose}\n"
        f"Status: {travel_request.get_status_display()}\n\n"
        "Your travel request was rejected.\n"
        f"Comment: {comment or '-'}"
    )

    return _send_notification(subject, body, recipients)