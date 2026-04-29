from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
from travel.access import (
    user_can_view_travel,
    user_can_edit_travel,
    user_can_submit_travel,
    user_can_cancel_travel,
    user_can_close_travel,
    user_can_record_actual_expense_travel,
    user_can_manage_travel_attachment,
    enforce_travel_permission,
)
from approvals.presentation import build_request_workflow_context

from .presentation import (
    decorate_travel_list_item,
    build_travel_detail_ui_flags,
)
from .services import (
    create_travel_request_from_forms,
    update_travel_request_from_forms,
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

@login_required
def tr_list(request):
    travel_requests = (
        TravelRequest.get_visible_queryset(request.user)
        .select_related("requester", "request_department", "project")
        .order_by("-request_date", "-id")
    )

    for tr in travel_requests:
        decorate_travel_list_item(tr, request.user)

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
    enforce_travel_permission(user_can_view_travel(request.user, travel_request))

    workflow_ui = build_request_workflow_context(travel_request, request.user)
    ui_flags = build_travel_detail_ui_flags(
        travel_request,
        request.user,
        workflow_ui["current_task"],
    )

    actual_expense_form = (
        TravelActualExpenseForm(
            travel_request=travel_request,
            initial=ui_flags["actual_expense_initial"],
        )
        if ui_flags["show_actual_expense_form"]
        else None
    )

    itineraries = travel_request.itineraries.all().order_by("line_no")
    expense_lines = travel_request.estimated_expense_lines.all().order_by("line_no")
    actual_expense_lines = travel_request.actual_expense_lines.all().order_by("line_no")
    attachments = travel_request.attachments.all()
    content_audits = travel_request.content_audits.all()
    histories = travel_request.history_entries.all()

    attachment_form = (
        TravelRequestAttachmentForm()
        if ui_flags["show_attachment_form"]
        else None
    )

    context = {
        "travel_request": travel_request,
        "itineraries": itineraries,
        "expense_lines": expense_lines,
        "actual_expense_lines": actual_expense_lines,
        "attachments": attachments,
        "attachment_form": attachment_form,
        "actual_expense_form": actual_expense_form,
        "histories": histories,
        "content_audits": content_audits,

        "current_task": workflow_ui["current_task"],
        "current_step": workflow_ui["current_step"],
        "current_approver": workflow_ui["current_approver"],
        "approval_progress": workflow_ui["approval_progress"],
        "can_claim_current_task": workflow_ui["can_claim_current_task"],
        "can_release_current_task": workflow_ui["can_release_current_task"],
        "can_approve_current_task": workflow_ui["can_approve_current_task"],
        "can_return_current_task": workflow_ui["can_return_current_task"],
        "can_reject_current_task": workflow_ui["can_reject_current_task"],

        "can_edit": ui_flags["can_edit"],
        "can_submit": ui_flags["can_submit"],
        "can_cancel": ui_flags["can_cancel"],
        "can_close": ui_flags["can_close"],
        "can_record_actual_expense": ui_flags["can_record_actual_expense"],
        "can_manage_attachments": ui_flags["can_manage_attachments"],
        "current_task_assignment_label": workflow_ui["current_task_assignment_label"],
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
                travel_request = create_travel_request_from_forms(
                    form=form,
                    itinerary_formset=itinerary_formset,
                    expense_formset=expense_formset,
                    acting_user=request.user,
                )

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

    if not user_can_edit_travel(request.user, travel_request):
        messages.error(request, f"{travel_request.travel_no} cannot be edited by you in its current status.")
        return redirect("travel:tr_detail", pk=travel_request.pk)

    if request.method == "POST":

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
                travel_request = update_travel_request_from_forms(
                    travel_request=travel_request,
                    form=form,
                    itinerary_formset=itinerary_formset,
                    expense_formset=expense_formset,
                    acting_user=request.user,
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
@require_POST
def tr_submit(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_travel_permission(
        user_can_submit_travel(request.user, travel_request)
    )

    try:
        travel_request.submit(acting_user=request.user)
        messages.success(request, f"{travel_request.travel_no} submitted successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("travel:tr_detail", pk=travel_request.pk)


@login_required
@require_POST
def tr_cancel(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_travel_permission(
        user_can_cancel_travel(request.user, travel_request)
    )

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

    enforce_travel_permission(
        user_can_manage_travel_attachment(request.user, travel_request)
    )

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

    enforce_travel_permission(
        user_can_manage_travel_attachment(request.user, travel_request)
    )

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

    enforce_travel_permission(
        user_can_record_actual_expense_travel(request.user, travel_request)
    )

    form = TravelActualExpenseForm(request.POST, travel_request=travel_request)

    if form.is_valid():
        try:
            travel_request.record_actual_expense(
                expense_type=form.cleaned_data["expense_type"],
                expense_date=form.cleaned_data["expense_date"],
                actual_amount=form.cleaned_data["actual_amount"],
                acting_user=request.user,
                estimated_expense_line=form.cleaned_data.get("estimated_expense_line"),
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

@login_required
@require_POST
def tr_close(request, pk):
    travel_request = get_object_or_404(
        TravelRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_travel_permission(
        user_can_close_travel(request.user, travel_request)
    )

    comment = request.POST.get("comment", "").strip()

    try:
        travel_request.close_request(
            acting_user=request.user,
            comment=comment,
        )
        messages.success(request, f"{travel_request.travel_no} closed successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("travel:tr_detail", pk=travel_request.pk)