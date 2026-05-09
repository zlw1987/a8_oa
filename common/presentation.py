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


def build_action_state(label, enabled, reason="", url="", method="get"):
    return {
        "label": label,
        "enabled": bool(enabled),
        "reason": reason or "",
        "url": url or "",
        "method": method,
    }
