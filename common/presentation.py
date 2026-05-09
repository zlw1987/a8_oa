STATUS_TONE_MAP = {
    "DRAFT": "neutral",
    "NOT_STARTED": "neutral",
    "SUBMITTED": "info",
    "PENDING": "info",
    "PENDING_APPROVAL": "info",
    "PENDING_REVIEW": "attention",
    "POOL": "info",
    "WAITING": "neutral",
    "APPROVED": "success",
    "APPROVED_TO_PROCEED": "success",
    "APPROVED_EXCEPTION": "success",
    "RESOLVED": "success",
    "MATCHED": "success",
    "REVIEWED": "success",
    "RETURNED": "warning",
    "WARNING": "warning",
    "PARTIAL": "warning",
    "PARTIALLY_MATCHED": "warning",
    "REJECTED": "danger",
    "BLOCK": "danger",
    "BLOCKED": "danger",
    "CANCELLED": "dark",
    "CLOSED": "dark",
    "AMENDMENT_REQUIRED": "attention",
    "REVIEW": "attention",
    "UNMATCHED": "attention",
}


def get_status_badge_tone(status):
    if not status:
        return "neutral"
    return STATUS_TONE_MAP.get(str(status).upper(), "neutral")


def build_action_state(label, enabled, reason="", url="", method="get", style="secondary"):
    return {
        "label": label,
        "enabled": bool(enabled),
        "reason": reason or "",
        "url": url or "",
        "method": method,
        "style": style,
    }


def format_money(currency, amount):
    return f"{currency} {amount}"


def build_summary_card(label, value, tone="neutral", detail=""):
    return {
        "label": label,
        "value": value,
        "tone": tone,
        "detail": detail,
    }


def build_checklist_item(label, passed, detail="", link=""):
    return {
        "label": label,
        "passed": bool(passed),
        "detail": detail or "",
        "link": link or "",
    }


def build_open_issue(issue_type, severity, explanation, owner="", link=""):
    return {
        "type": issue_type,
        "severity": severity,
        "explanation": explanation,
        "owner": owner or "",
        "link": link or "",
        "tone": get_status_badge_tone(severity),
    }
