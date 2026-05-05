from django.conf import settings
from django.core.mail import send_mail


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


def _travel_detail_url(travel_request):
    return _build_absolute_url(f"/travel/{travel_request.id}/")


def _travel_common_lines(travel_request):
    matched_rule = getattr(travel_request, "matched_rule", None)
    matched_rule_text = (
        f"{matched_rule.rule_code} - {matched_rule.rule_name}"
        if matched_rule and getattr(matched_rule, "rule_code", None)
        else "-"
    )

    return [
        f"Travel Request: {travel_request.travel_no}",
        f"Purpose: {travel_request.purpose}",
        f"Status: {travel_request.get_status_display()}",
        f"Project: {travel_request.project}",
        f"Estimated Total: {travel_request.currency} {travel_request.estimated_total}",
        f"Matched Approval Rule: {matched_rule_text}",
    ]


def notify_tr_submitted(travel_request):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _travel_detail_url(travel_request)

    lines = _travel_common_lines(travel_request)
    lines.extend(
        [
            "",
            "Your travel request has been submitted successfully.",
            "Next step: wait for the current approval task to be claimed or reviewed.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {travel_request.travel_no} submitted"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_tr_approved(travel_request):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _travel_detail_url(travel_request)

    lines = _travel_common_lines(travel_request)
    lines.extend(
        [
            "",
            "Your travel request has been fully approved.",
            "Next step: after the trip, record actual expenses and close the request when everything is complete.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {travel_request.travel_no} approved"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_tr_returned(travel_request, comment=""):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _travel_detail_url(travel_request)

    lines = _travel_common_lines(travel_request)
    lines.extend(
        [
            "",
            "Your travel request was returned for update.",
            f"Approver Comment: {comment or '-'}",
            "Next step: open the request, revise it, and resubmit.",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {travel_request.travel_no} returned"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_tr_rejected(travel_request, comment=""):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _travel_detail_url(travel_request)

    lines = _travel_common_lines(travel_request)
    lines.extend(
        [
            "",
            "Your travel request was rejected.",
            f"Approver Comment: {comment or '-'}",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {travel_request.travel_no} rejected"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)


def notify_tr_closed(travel_request, comment=""):
    requester = travel_request.requester
    recipients = [requester.email] if requester and requester.email else []

    detail_url = _travel_detail_url(travel_request)

    lines = _travel_common_lines(travel_request)
    lines.extend(
        [
            f"Actual Total: {travel_request.currency} {travel_request.actual_total}",
            "",
            "Your travel request has been closed.",
            f"Close Comment: {comment or '-'}",
        ]
    )

    if detail_url:
        lines.extend(["", f"Open Request: {detail_url}"])

    subject = f"[OA] {travel_request.travel_no} closed"
    body = "\n".join(lines)

    return _send_notification(subject, body, recipients)