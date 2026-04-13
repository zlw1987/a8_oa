from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    TravelRequestForm,
    TravelItineraryCreateFormSet,
    TravelItineraryEditFormSet,
    TravelEstimatedExpenseCreateFormSet,
    TravelEstimatedExpenseEditFormSet,
    TravelRequestAttachmentForm,
    TravelActualExpenseForm,
)
from .models import (
    TravelRequest,
    TravelRequestAttachment,
    TravelRequestContentAuditActionType,
)


def _get_estimated_total_from_formset(formset):
    total = Decimal("0.00")

    for expense_form in formset.forms:
        cleaned_data = getattr(expense_form, "cleaned_data", None)
        if not cleaned_data:
            continue

        if cleaned_data.get("DELETE"):
            continue

        expense_type = cleaned_data.get("expense_type")
        if not expense_type:
            continue

        amount = cleaned_data.get("estimated_amount") or Decimal("0.00")
        total += amount

    return total

def _stringify_audit_value(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


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


def _snapshot_travel_header(travel_request):
    return {
        "purpose": travel_request.purpose or "",
        "request_department": str(travel_request.request_department) if travel_request.request_department else "",
        "project": str(travel_request.project) if travel_request.project else "",
        "request_date": _stringify_audit_value(travel_request.request_date),
        "start_date": _stringify_audit_value(travel_request.start_date),
        "end_date": _stringify_audit_value(travel_request.end_date),
        "origin_city": travel_request.origin_city or "",
        "destination_city": travel_request.destination_city or "",
        "currency": travel_request.currency or "",
        "notes": travel_request.notes or "",
    }


def _snapshot_travel_itineraries(travel_request):
    data = {}

    for line in travel_request.itineraries.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "trip_date": _stringify_audit_value(line.trip_date),
            "from_city": line.from_city or "",
            "to_city": line.to_city or "",
            "transport_type": line.get_transport_type_display() if hasattr(line, "get_transport_type_display") else (line.transport_type or ""),
            "departure_time": _stringify_audit_value(line.departure_time),
            "arrival_time": _stringify_audit_value(line.arrival_time),
            "notes": line.notes or "",
        }

    return data


def _snapshot_travel_expenses(travel_request):
    data = {}

    for line in travel_request.estimated_expense_lines.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "expense_type": line.get_expense_type_display() if hasattr(line, "get_expense_type_display") else (line.expense_type or ""),
            "location_mode": line.get_location_mode_display() if hasattr(line, "get_location_mode_display") else (line.location_mode or ""),
            "expense_date": _stringify_audit_value(line.expense_date),
            "estimated_amount": _stringify_audit_value(line.estimated_amount),
            "currency": line.currency or "",
            "from_location": line.from_location or "",
            "to_location": line.to_location or "",
            "departure_dt": _stringify_audit_value(line.departure_dt),
            "arrival_dt": _stringify_audit_value(line.arrival_dt),
            "expense_location": line.expense_location or "",
            "checkin_date": _stringify_audit_value(line.checkin_date),
            "checkout_date": _stringify_audit_value(line.checkout_date),
            "nights": _stringify_audit_value(line.nights),
            "itinerary_line_no": _stringify_audit_value(line.itinerary_line_no),
            "exception_reason": line.exception_reason or "",
            "notes": line.notes or "",
        }

    return data


def _format_itinerary_summary(line_data):
    return (
        f"{line_data.get('trip_date', '')} / "
        f"{line_data.get('from_city', '')} -> {line_data.get('to_city', '')} / "
        f"{line_data.get('transport_type', '')}"
    )


def _format_expense_summary(line_data):
    return (
        f"{line_data.get('expense_type', '')} / "
        f"{line_data.get('currency', '')} {line_data.get('estimated_amount', '')} / "
        f"{line_data.get('location_mode', '')}"
    )


def _log_travel_create_content_audit(travel_request, acting_user):
    travel_request._add_content_audit(
        action_type=TravelRequestContentAuditActionType.HEADER_CREATED,
        changed_by=acting_user,
        section="HEADER",
        notes="Travel request created.",
    )

    for line in travel_request.itineraries.all().order_by("line_no", "id"):
        snapshot = {
            "line_no": line.line_no,
            "trip_date": _stringify_audit_value(line.trip_date),
            "from_city": line.from_city or "",
            "to_city": line.to_city or "",
            "transport_type": line.get_transport_type_display() if hasattr(line, "get_transport_type_display") else (line.transport_type or ""),
        }

        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.ITINERARY_ADDED,
            changed_by=acting_user,
            section="ITINERARY",
            line_no=line.line_no,
            new_value=_format_itinerary_summary(snapshot),
            notes="Initial itinerary line added during create.",
        )

    for line in travel_request.estimated_expense_lines.all().order_by("line_no", "id"):
        snapshot = {
            "line_no": line.line_no,
            "expense_type": line.get_expense_type_display() if hasattr(line, "get_expense_type_display") else (line.expense_type or ""),
            "currency": line.currency or "",
            "estimated_amount": _stringify_audit_value(line.estimated_amount),
            "location_mode": line.get_location_mode_display() if hasattr(line, "get_location_mode_display") else (line.location_mode or ""),
        }

        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.EXPENSE_ADDED,
            changed_by=acting_user,
            section="EXPENSE",
            line_no=line.line_no,
            new_value=_format_expense_summary(snapshot),
            notes="Initial estimated expense line added during create.",
        )


def _log_travel_edit_content_audit(travel_request, old_header, old_itineraries, old_expenses, acting_user):
    new_header = _snapshot_travel_header(travel_request)
    new_itineraries = _snapshot_travel_itineraries(travel_request)
    new_expenses = _snapshot_travel_expenses(travel_request)

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
            old_value=_format_itinerary_summary(old_line),
            notes="Itinerary line deleted.",
        )

    for added_id in sorted(new_itinerary_ids - old_itinerary_ids):
        new_line = new_itineraries[added_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.ITINERARY_ADDED,
            changed_by=acting_user,
            section="ITINERARY",
            line_no=new_line.get("line_no"),
            new_value=_format_itinerary_summary(new_line),
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
            old_value=_format_expense_summary(old_line),
            notes="Estimated expense line deleted.",
        )

    for added_id in sorted(new_expense_ids - old_expense_ids):
        new_line = new_expenses[added_id]
        travel_request._add_content_audit(
            action_type=TravelRequestContentAuditActionType.EXPENSE_ADDED,
            changed_by=acting_user,
            section="EXPENSE",
            line_no=new_line.get("line_no"),
            new_value=_format_expense_summary(new_line),
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

@login_required
def tr_list(request):
    travel_requests = (
        TravelRequest.get_visible_queryset(request.user)
        .select_related("requester", "request_department", "project")
        .order_by("-request_date", "-id")
    )

    for tr in travel_requests:
        tr.can_edit = tr.can_user_edit(request.user)

    context = {
        "travel_requests": travel_requests,
    }
    return render(request, "travel/tr_list.html", context)


@login_required
def tr_detail(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    
    can_record_actual_expense = travel_request.can_user_record_actual_expense(request.user)
    actual_expense_form = (
        TravelActualExpenseForm(
            travel_request=travel_request,
            initial={"expense_date": travel_request.end_date, "currency": travel_request.currency},
        )
        if can_record_actual_expense else None
    )

    itineraries = travel_request.itineraries.all().order_by("line_no")
    expense_lines = travel_request.estimated_expense_lines.all().order_by("line_no")
    actual_expense_lines = travel_request.actual_expense_lines.all().order_by("line_no")
    attachments = travel_request.attachments.all()
    content_audits = travel_request.content_audits.all()
    histories = travel_request.history_entries.all()
    can_manage_attachments = travel_request.can_user_manage_attachments(request.user)
    attachment_form = TravelRequestAttachmentForm() if can_manage_attachments else None

    context = {
        "travel_request": travel_request,
        "itineraries": itineraries,
        "expense_lines": expense_lines,
        "histories": histories,
        "content_audits": content_audits,
        "current_step": travel_request.get_current_step_name(),
        "current_approver": travel_request.get_current_approver(),
        "approval_progress": travel_request.get_approval_progress_text(),
        "can_edit": travel_request.can_user_edit(request.user),
        "can_submit": travel_request.can_user_submit(request.user),
        "can_cancel": travel_request.can_user_cancel(request.user),
        "attachments": attachments,
        "attachment_form": attachment_form,
        "can_manage_attachments": can_manage_attachments,
        "actual_expense_lines": actual_expense_lines,
        "can_record_actual_expense": can_record_actual_expense,
        "actual_expense_form": actual_expense_form,
    }
    return render(request, "travel/tr_detail.html", context)


@login_required
def tr_create(request):
    if request.method == "POST":
        form = TravelRequestForm(request.POST, user=request.user)
        itinerary_formset = TravelItineraryCreateFormSet(request.POST, prefix="itineraries")
        expense_formset = TravelEstimatedExpenseCreateFormSet(request.POST, prefix="expenses")

        form_valid = form.is_valid()
        itinerary_valid = itinerary_formset.is_valid()
        expense_valid = expense_formset.is_valid()

        estimated_total_preview = (
            _get_estimated_total_from_formset(expense_formset)
            if expense_valid
            else Decimal("0.00")
        )

        if form_valid and itinerary_valid and expense_valid:
            try:
                with transaction.atomic():
                    travel_request = form.save(commit=False)

                    if not request.user.is_superuser:
                        travel_request.requester = request.user

                    travel_request.estimated_total = Decimal("0.00")
                    travel_request.save()

                    itinerary_formset.instance = travel_request
                    itinerary_formset.save()

                    expense_formset.instance = travel_request
                    expense_formset.save()

                    travel_request.refresh_estimated_total(commit=True)

                    _log_travel_create_content_audit(travel_request, request.user)

                    messages.success(request, f"{travel_request.travel_no} saved as draft successfully.")
                return redirect("travel:tr_detail", pk=travel_request.pk)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
    else:
        initial = {
            "currency": "USD",
        }
        form = TravelRequestForm(user=request.user, initial=initial)
        itinerary_formset = TravelItineraryCreateFormSet(prefix="itineraries")
        expense_formset = TravelEstimatedExpenseCreateFormSet(prefix="expenses")
        estimated_total_preview = Decimal("0.00")

    context = {
        "form": form,
        "itinerary_formset": itinerary_formset,
        "expense_formset": expense_formset,
        "page_mode": "create",
        "estimated_total_preview": estimated_total_preview,
    }
    return render(request, "travel/tr_edit.html", context)


@login_required
def tr_edit(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_edit(request.user):
        messages.error(request, f"{travel_request.travel_no} cannot be edited by you in its current status.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    if request.method == "POST":
        old_header_snapshot = _snapshot_travel_header(travel_request)
        old_itinerary_snapshot = _snapshot_travel_itineraries(travel_request)
        old_expense_snapshot = _snapshot_travel_expenses(travel_request)

        form = TravelRequestForm(request.POST, instance=travel_request, user=request.user)
        itinerary_formset = TravelItineraryEditFormSet(
            request.POST,
            instance=travel_request,
            prefix="itineraries",
        )
        expense_formset = TravelEstimatedExpenseEditFormSet(
            request.POST,
            instance=travel_request,
            prefix="expenses",
        )

        form_valid = form.is_valid()
        itinerary_valid = itinerary_formset.is_valid()
        expense_valid = expense_formset.is_valid()

        estimated_total_preview = (
            _get_estimated_total_from_formset(expense_formset)
            if expense_valid
            else travel_request.estimated_total
        )

        if form_valid and itinerary_valid and expense_valid:
            try:
                with transaction.atomic():
                    travel_request = form.save(commit=False)

                    if not request.user.is_superuser:
                        travel_request.requester = request.user

                    travel_request.save()

                    itinerary_formset.instance = travel_request
                    itinerary_formset.save()

                    expense_formset.instance = travel_request
                    expense_formset.save()

                    travel_request.refresh_estimated_total(commit=True)

                    _log_travel_edit_content_audit(
                        travel_request,
                        old_header_snapshot,
                        old_itinerary_snapshot,
                        old_expense_snapshot,
                        request.user,
                    )

                    messages.success(request, f"{travel_request.travel_no} updated successfully.")
                return redirect("travel:tr_detail", pk=travel_request.pk)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
    else:
        form = TravelRequestForm(instance=travel_request, user=request.user)
        itinerary_formset = TravelItineraryEditFormSet(
            instance=travel_request,
            prefix="itineraries",
        )
        expense_formset = TravelEstimatedExpenseEditFormSet(
            instance=travel_request,
            prefix="expenses",
        )
        estimated_total_preview = travel_request.estimated_total

    context = {
        "form": form,
        "itinerary_formset": itinerary_formset,
        "expense_formset": expense_formset,
        "travel_request": travel_request,
        "page_mode": "edit",
        "estimated_total_preview": estimated_total_preview,
    }
    return render(request, "travel/tr_edit.html", context)

@login_required
def tr_submit(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_submit(request.user):
        messages.error(request, "You do not have permission to submit this travel request.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    try:
        travel_request.submit(acting_user=request.user)
        messages.success(request, f"{travel_request.travel_no} submitted successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("travel:tr_detail", pk=travel_request.pk)


@login_required
def tr_cancel(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_cancel(request.user):
        messages.error(request, "You do not have permission to cancel this travel request.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    try:
        travel_request.cancel(acting_user=request.user)
        messages.success(request, f"{travel_request.travel_no} cancelled successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("travel:tr_detail", pk=travel_request.pk)

@login_required
def tr_upload_attachment(request, pk):
    if request.method != "POST":
        return redirect("travel:tr_detail", pk=pk)

    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_manage_attachments(request.user):
        messages.error(request, "You do not have permission to manage attachments for this travel request.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    form = TravelRequestAttachmentForm(request.POST, request.FILES)

    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.travel_request = travel_request
        attachment.uploaded_by = request.user
        attachment.save()
        messages.success(request, f"Attachment '{attachment.title}' uploaded successfully.")
    else:
        for field_name, errors in form.errors.items():
            label = form.fields[field_name].label or field_name
            for error in errors:
                messages.error(request, f"{label}: {error}")

    return redirect("travel:tr_detail", pk=travel_request.pk)

@login_required
def tr_delete_attachment(request, pk, attachment_id):
    if request.method != "POST":
        return redirect("travel:tr_detail", pk=pk)

    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_manage_attachments(request.user):
        messages.error(request, "You do not have permission to manage attachments for this travel request.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    attachment = get_object_or_404(
        TravelRequestAttachment,
        pk=attachment_id,
        travel_request=travel_request,
    )

    attachment_title = attachment.title or attachment.filename
    attachment.delete()
    messages.success(request, f"Attachment '{attachment_title}' deleted successfully.")

    return redirect("travel:tr_detail", pk=travel_request.pk)

@login_required
def tr_record_actual_expense(request, pk):
    if request.method != "POST":
        return redirect("travel:tr_detail", pk=pk)

    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not travel_request.can_user_record_actual_expense(request.user):
        messages.error(request, "You do not have permission to record actual expense for this travel request.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    form = TravelActualExpenseForm(request.POST, travel_request=travel_request)

    if form.is_valid():
        try:
            travel_request.record_actual_expense(
                expense_type=form.cleaned_data["expense_type"],
                expense_date=form.cleaned_data["expense_date"],
                actual_amount=form.cleaned_data["actual_amount"],
                acting_user=request.user,
                estimated_expense_line=form.cleaned_data.get("estimated_expense_line"),
                purchase_request_line=form.cleaned_data.get("purchase_request_line"),
                currency=form.cleaned_data.get("currency") or travel_request.currency,
                vendor_name=form.cleaned_data.get("vendor_name", ""),
                reference_no=form.cleaned_data.get("reference_no", ""),
                expense_location=form.cleaned_data.get("expense_location", ""),
                notes=form.cleaned_data.get("notes", ""),
            )
            messages.success(request, f"Actual expense recorded successfully for {travel_request.travel_no}.")
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
    else:
        for field_name, errors in form.errors.items():
            label = form.fields[field_name].label or field_name
            for error in errors:
                messages.error(request, f"{label}: {error}")

    return redirect("travel:tr_detail", pk=travel_request.pk)