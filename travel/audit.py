from decimal import Decimal

from .models import TravelRequestContentAuditActionType


TRAVEL_HEADER_AUDIT_FIELDS = [
    ("purpose", "Purpose"),
    ("request_department", "Department"),
    ("project", "Project"),
    ("request_date", "Request Date"),
    ("start_date", "Start Date"),
    ("end_date", "End Date"),
    ("origin_city", "Origin City"),
    ("destination_city", "Destination City"),
    ("currency", "Currency"),
    ("notes", "Notes"),
]


TRAVEL_ITINERARY_AUDIT_FIELDS = [
    ("trip_date", "Trip Date"),
    ("from_city", "From City"),
    ("to_city", "To City"),
    ("transport_type", "Transport Type"),
    ("departure_time", "Departure Time"),
    ("arrival_time", "Arrival Time"),
    ("notes", "Notes"),
]


TRAVEL_EXPENSE_AUDIT_FIELDS = [
    ("expense_type", "Expense Type"),
    ("location_mode", "Location Mode"),
    ("expense_date", "Expense Date"),
    ("estimated_amount", "Estimated Amount"),
    ("currency", "Currency"),
    ("from_location", "From Location"),
    ("to_location", "To Location"),
    ("departure_dt", "Departure"),
    ("arrival_dt", "Arrival"),
    ("expense_location", "Expense Location"),
    ("checkin_date", "Check-in Date"),
    ("checkout_date", "Check-out Date"),
    ("nights", "Nights"),
    ("itinerary_line_no", "Itinerary Ref"),
    ("exception_reason", "Exception Reason"),
    ("notes", "Notes"),
]


def stringify_audit_value(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def snapshot_travel_header(travel_request):
    return {
        "purpose": travel_request.purpose or "",
        "request_department": str(travel_request.request_department) if travel_request.request_department else "",
        "project": str(travel_request.project) if travel_request.project else "",
        "request_date": stringify_audit_value(travel_request.request_date),
        "start_date": stringify_audit_value(travel_request.start_date),
        "end_date": stringify_audit_value(travel_request.end_date),
        "origin_city": travel_request.origin_city or "",
        "destination_city": travel_request.destination_city or "",
        "currency": travel_request.currency or "",
        "notes": travel_request.notes or "",
    }


def snapshot_travel_itineraries(travel_request):
    data = {}

    for line in travel_request.itineraries.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "trip_date": stringify_audit_value(line.trip_date),
            "from_city": line.from_city or "",
            "to_city": line.to_city or "",
            "transport_type": (
                line.get_transport_type_display()
                if hasattr(line, "get_transport_type_display")
                else (line.transport_type or "")
            ),
            "departure_time": stringify_audit_value(line.departure_time),
            "arrival_time": stringify_audit_value(line.arrival_time),
            "notes": line.notes or "",
        }

    return data


def snapshot_travel_expenses(travel_request):
    data = {}

    for line in travel_request.estimated_expense_lines.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "expense_type": (
                line.get_expense_type_display()
                if hasattr(line, "get_expense_type_display")
                else (line.expense_type or "")
            ),
            "location_mode": (
                line.get_location_mode_display()
                if hasattr(line, "get_location_mode_display")
                else (line.location_mode or "")
            ),
            "expense_date": stringify_audit_value(line.expense_date),
            "estimated_amount": stringify_audit_value(line.estimated_amount),
            "currency": line.currency or "",
            "from_location": line.from_location or "",
            "to_location": line.to_location or "",
            "departure_dt": stringify_audit_value(line.departure_dt),
            "arrival_dt": stringify_audit_value(line.arrival_dt),
            "expense_location": line.expense_location or "",
            "checkin_date": stringify_audit_value(line.checkin_date),
            "checkout_date": stringify_audit_value(line.checkout_date),
            "nights": stringify_audit_value(line.nights),
            "itinerary_line_no": stringify_audit_value(line.itinerary_line_no),
            "exception_reason": line.exception_reason or "",
            "notes": line.notes or "",
        }

    return data


def format_itinerary_summary(line_data):
    return (
        f"{line_data.get('trip_date', '')} / "
        f"{line_data.get('from_city', '')} -> {line_data.get('to_city', '')} / "
        f"{line_data.get('transport_type', '')}"
    )


def format_expense_summary(line_data):
    return (
        f"{line_data.get('expense_type', '')} / "
        f"{line_data.get('currency', '')} {line_data.get('estimated_amount', '')} / "
        f"{line_data.get('location_mode', '')}"
    )


def log_travel_create_content_audit(travel_request, acting_user):
    travel_request._add_content_audit(
        action_type=TravelRequestContentAuditActionType.HEADER_CREATED,
        changed_by=acting_user,
        section="HEADER",
        notes="Travel request created.",
    )

    for line in travel_request.itineraries.all().order_by("line_no", "id"):
        snapshot = {
            "line_no": line.line_no,
            "trip_date": stringify_audit_value(line.trip_date),
            "from_city": line.from_city or "",
            "to_city": line.to_city or "",
            "transport_type": (
                line.get_transport_type_display()
                if hasattr(line, "get_transport_type_display")
                else (line.transport_type or "")
            ),
        }

        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.ITINERARY_ADDED,
            changed_by=acting_user,
            section="ITINERARY",
            line_no=line.line_no,
            new_value=format_itinerary_summary(snapshot),
            notes="Initial itinerary line added during create.",
        )

    for line in travel_request.estimated_expense_lines.all().order_by("line_no", "id"):
        snapshot = {
            "line_no": line.line_no,
            "expense_type": (
                line.get_expense_type_display()
                if hasattr(line, "get_expense_type_display")
                else (line.expense_type or "")
            ),
            "currency": line.currency or "",
            "estimated_amount": stringify_audit_value(line.estimated_amount),
            "location_mode": (
                line.get_location_mode_display()
                if hasattr(line, "get_location_mode_display")
                else (line.location_mode or "")
            ),
        }

        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.EXPENSE_ADDED,
            changed_by=acting_user,
            section="EXPENSE",
            line_no=line.line_no,
            new_value=format_expense_summary(snapshot),
            notes="Initial estimated expense line added during create.",
        )


def log_travel_edit_content_audit(
    travel_request,
    old_header,
    old_itineraries,
    old_expenses,
    acting_user,
):
    new_header = snapshot_travel_header(travel_request)
    new_itineraries = snapshot_travel_itineraries(travel_request)
    new_expenses = snapshot_travel_expenses(travel_request)

    for field_key, field_label in TRAVEL_HEADER_AUDIT_FIELDS:
        old_value = old_header.get(field_key, "")
        new_value = new_header.get(field_key, "")
        if old_value != new_value:
            travel_request._add_content_audit(
                action_type=TravelRequestContentAuditActionType.HEADER_UPDATED,
                changed_by=acting_user,
                section="HEADER",
                field_name=field_label,
                old_value=old_value,
                new_value=new_value,
                notes=f"Header field '{field_label}' updated.",
            )

    old_itinerary_ids = set(old_itineraries.keys())
    new_itinerary_ids = set(new_itineraries.keys())

    for deleted_id in sorted(old_itinerary_ids - new_itinerary_ids):
        old_line = old_itineraries[deleted_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.ITINERARY_DELETED,
            changed_by=acting_user,
            section="ITINERARY",
            line_no=old_line.get("line_no"),
            old_value=format_itinerary_summary(old_line),
            notes="Itinerary line deleted.",
        )

    for added_id in sorted(new_itinerary_ids - old_itinerary_ids):
        new_line = new_itineraries[added_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.ITINERARY_ADDED,
            changed_by=acting_user,
            section="ITINERARY",
            line_no=new_line.get("line_no"),
            new_value=format_itinerary_summary(new_line),
            notes="Itinerary line added.",
        )

    for common_id in sorted(old_itinerary_ids & new_itinerary_ids):
        old_line = old_itineraries[common_id]
        new_line = new_itineraries[common_id]
        line_no = new_line.get("line_no") or old_line.get("line_no")

        for field_key, field_label in TRAVEL_ITINERARY_AUDIT_FIELDS:
            old_value = old_line.get(field_key, "")
            new_value = new_line.get(field_key, "")
            if old_value != new_value:
                travel_request._add_content_audit(
                    action_type=TravelRequestContentAuditActionType.ITINERARY_UPDATED,
                    changed_by=acting_user,
                    section="ITINERARY",
                    field_name=field_label,
                    line_no=line_no,
                    old_value=old_value,
                    new_value=new_value,
                    notes=f"Itinerary line {line_no} field '{field_label}' updated.",
                )

    old_expense_ids = set(old_expenses.keys())
    new_expense_ids = set(new_expenses.keys())

    for deleted_id in sorted(old_expense_ids - new_expense_ids):
        old_line = old_expenses[deleted_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.EXPENSE_DELETED,
            changed_by=acting_user,
            section="EXPENSE",
            line_no=old_line.get("line_no"),
            old_value=format_expense_summary(old_line),
            notes="Estimated expense line deleted.",
        )

    for added_id in sorted(new_expense_ids - old_expense_ids):
        new_line = new_expenses[added_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.EXPENSE_ADDED,
            changed_by=acting_user,
            section="EXPENSE",
            line_no=new_line.get("line_no"),
            new_value=format_expense_summary(new_line),
            notes="Estimated expense line added.",
        )

    for common_id in sorted(old_expense_ids & new_expense_ids):
        old_line = old_expenses[common_id]
        new_line = new_expenses[common_id]
        line_no = new_line.get("line_no") or old_line.get("line_no")

        for field_key, field_label in TRAVEL_EXPENSE_AUDIT_FIELDS:
            old_value = old_line.get(field_key, "")
            new_value = new_line.get(field_key, "")
            if old_value != new_value:
                travel_request._add_content_audit(
                    action_type=TravelRequestContentAuditActionType.EXPENSE_UPDATED,
                    changed_by=acting_user,
                    section="EXPENSE",
                    field_name=field_label,
                    line_no=line_no,
                    old_value=old_value,
                    new_value=new_value,
                    notes=f"Expense line {line_no} field '{field_label}' updated.",
                )