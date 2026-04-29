from decimal import Decimal

from .models import PurchaseRequestContentAuditActionType


def stringify_audit_value(value):
    if value is None:
        return ""

    if isinstance(value, Decimal):
        return format(value, "f")

    return str(value)

HEADER_AUDIT_FIELDS = [
    ("title", "Title"),
    ("request_department", "Department"),
    ("project", "Project"),
    ("request_date", "Request Date"),
    ("needed_by_date", "Needed By"),
    ("currency", "Currency"),
    ("justification", "Justification"),
    ("vendor_suggestion", "Vendor Suggestion"),
    ("delivery_location", "Delivery Location"),
    ("notes", "Notes"),
]
LINE_AUDIT_FIELDS = [
    ("item_name", "Item Name"),
    ("item_description", "Description"),
    ("quantity", "Quantity"),
    ("uom", "UOM"),
    ("unit_price", "Unit Price"),
    ("notes", "Notes"),
]

def snapshot_request_header(purchase_request):
    return {
        "title": purchase_request.title or "",
        "request_department": str(purchase_request.request_department) if purchase_request.request_department else "",
        "project": str(purchase_request.project) if purchase_request.project else "",
        "request_date": stringify_audit_value(purchase_request.request_date),
        "needed_by_date": stringify_audit_value(purchase_request.needed_by_date),
        "currency": purchase_request.currency or "",
        "justification": purchase_request.justification or "",
        "vendor_suggestion": purchase_request.vendor_suggestion or "",
        "delivery_location": purchase_request.delivery_location or "",
        "notes": purchase_request.notes or "",
    }

def snapshot_request_lines(purchase_request):
    data = {}

    for line in purchase_request.lines.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "item_name": line.item_name or "",
            "item_description": line.item_description or "",
            "quantity": stringify_audit_value(line.quantity),
            "uom": line.get_uom_display() if hasattr(line, "get_uom_display") else (line.uom or ""),
            "unit_price": stringify_audit_value(line.unit_price),
            "notes": line.notes or "",
        }

    return data

def format_line_summary(line_data):
    return (
        f"{line_data.get('item_name', '')} / "
        f"Qty {line_data.get('quantity', '')} / "
        f"UOM {line_data.get('uom', '')} / "
        f"Unit Price {line_data.get('unit_price', '')}"
    )

def log_create_content_audit(purchase_request, acting_user):
    purchase_request._add_content_audit(
        action_type=PurchaseRequestContentAuditActionType.HEADER_CREATED,
        changed_by=acting_user,
        notes="Purchase request created.",
    )

    for line in purchase_request.lines.all().order_by("line_no", "id"):
        line_snapshot = {
            "line_no": line.line_no,
            "item_name": line.item_name or "",
            "item_description": line.item_description or "",
            "quantity": stringify_audit_value(line.quantity),
            "uom": line.get_uom_display() if hasattr(line, "get_uom_display") else (line.uom or ""),
            "unit_price": stringify_audit_value(line.unit_price),
            "notes": line.notes or "",
        }

        purchase_request._add_content_audit(
            action_type=PurchaseRequestContentAuditActionType.LINE_ADDED,
            changed_by=acting_user,
            line_no=line.line_no,
            new_value=format_line_summary(line_snapshot),
            notes="Initial line added during create.",
        )

def log_edit_content_audit(purchase_request, old_header, old_lines, acting_user):
    new_header = snapshot_request_header(purchase_request)
    new_lines = snapshot_request_lines(purchase_request)

    for field_key, field_label in HEADER_AUDIT_FIELDS:
        old_value = old_header.get(field_key, "")
        new_value = new_header.get(field_key, "")

        if old_value != new_value:
            purchase_request._add_content_audit(
                action_type=PurchaseRequestContentAuditActionType.HEADER_UPDATED,
                changed_by=acting_user,
                field_name=field_label,
                old_value=old_value,
                new_value=new_value,
                notes=f"Header field '{field_label}' updated.",
            )

    old_ids = set(old_lines.keys())
    new_ids = set(new_lines.keys())

    for deleted_id in sorted(old_ids - new_ids):
        old_line = old_lines[deleted_id]
        purchase_request._add_content_audit(
            action_type=PurchaseRequestContentAuditActionType.LINE_DELETED,
            changed_by=acting_user,
            line_no=old_line.get("line_no"),
            old_value=format_line_summary(old_line),
            notes="Line deleted.",
        )

    for added_id in sorted(new_ids - old_ids):
        new_line = new_lines[added_id]
        purchase_request._add_content_audit(
            action_type=PurchaseRequestContentAuditActionType.LINE_ADDED,
            changed_by=acting_user,
            line_no=new_line.get("line_no"),
            new_value=format_line_summary(new_line),
            notes="Line added.",
        )

    for common_id in sorted(old_ids & new_ids):
        old_line = old_lines[common_id]
        new_line = new_lines[common_id]
        line_no = new_line.get("line_no") or old_line.get("line_no")

        for field_key, field_label in LINE_AUDIT_FIELDS:
            old_value = old_line.get(field_key, "")
            new_value = new_line.get(field_key, "")

            if old_value != new_value:
                purchase_request._add_content_audit(
                    action_type=PurchaseRequestContentAuditActionType.LINE_UPDATED,
                    changed_by=acting_user,
                    field_name=field_label,
                    line_no=line_no,
                    old_value=old_value,
                    new_value=new_value,
                    notes=f"Line {line_no} field '{field_label}' updated.",
                )