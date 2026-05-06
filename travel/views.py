from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from approvals.models import ApprovalNotificationLog
from approvals.action_handlers import handle_task_action
from approvals.models import ApprovalTask
from .filters import TravelRequestListFilterForm
from projects.presentation import build_project_budget_summary
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
    TravelRequestStatus,
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
    queryset = (
        TravelRequest.get_visible_queryset(request.user)
        .select_related("requester", "request_department", "project", "matched_rule")
        .order_by("-request_date", "-id")
    )

    filter_form = TravelRequestListFilterForm(
        request.GET or None,
        visible_queryset=queryset,
    )

    if filter_form.is_valid():
        keyword = (filter_form.cleaned_data.get("keyword") or "").strip()
        status = filter_form.cleaned_data.get("status")
        department = filter_form.cleaned_data.get("department")
        requester = filter_form.cleaned_data.get("requester")
        project = filter_form.cleaned_data.get("project")
        request_date_from = filter_form.cleaned_data.get("request_date_from")
        request_date_to = filter_form.cleaned_data.get("request_date_to")

        if keyword:
            queryset = queryset.filter(
                Q(travel_no__icontains=keyword)
                | Q(purpose__icontains=keyword)
                | Q(notes__icontains=keyword)
            )

        if status:
            queryset = queryset.filter(status=status)

        if department:
            queryset = queryset.filter(request_department=department)

        if requester:
            queryset = queryset.filter(requester=requester)

        if project:
            queryset = queryset.filter(project=project)

        if request_date_from:
            queryset = queryset.filter(request_date__gte=request_date_from)

        if request_date_to:
            queryset = queryset.filter(request_date__lte=request_date_to)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for tr in page_obj.object_list:
        decorate_travel_list_item(tr, request.user)

    querydict = request.GET.copy()
    querydict.pop("page", None)
    pagination_querystring = querydict.urlencode()

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "pagination_querystring": pagination_querystring,
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

    budget_summary = build_project_budget_summary(
        travel_request.project,
        travel_request.estimated_total,
    )
    request_ct = ContentType.objects.get_for_model(TravelRequest)
    reserved_remaining = travel_request.get_reserved_remaining_amount()

    notification_logs = ApprovalNotificationLog.objects.filter(
        task__request_content_type=request_ct,
        task__request_object_id=travel_request.id,
    ).select_related("task").order_by("-sent_at", "-id")[:30]

    budget_snapshot_ui = None
    if budget_summary:
        budget_snapshot_ui = {
            "cards": [
                {
                    "label": "This Request Total",
                    "value": f"{travel_request.currency} {budget_summary['request_total']}",
                },
                {
                    "label": "Available Amount",
                    "value": f"{travel_request.currency} {budget_summary['available_amount']}",
                },
                {
                    "label": "Reserved Remaining",
                    "value": f"{travel_request.currency} {reserved_remaining}",
                },
                {
                    "label": "Remaining After This Request",
                    "value": f"{travel_request.currency} {budget_summary['remaining_after_request']}",
                },
            ],
            "rows": [
                {
                    "label": "Project",
                    "value": f"{budget_summary['project_code']} - {budget_summary['project_name']}",
                },
                {
                    "label": "Project Budget",
                    "value": f"{travel_request.currency} {budget_summary['budget_amount']}",
                },
                {
                    "label": "Adjustments",
                    "value": f"{travel_request.currency} {budget_summary['adjustment_amount']}",
                },
                {
                    "label": "Effective Budget",
                    "value": f"{travel_request.currency} {budget_summary['effective_budget_amount']}",
                },
                {
                    "label": "Reserved Amount",
                    "value": f"{travel_request.currency} {budget_summary['reserved_amount']}",
                },
                {
                    "label": "Consumed Amount",
                    "value": f"{travel_request.currency} {budget_summary['consumed_amount']}",
                },
            ],
            "warning": (
                "Warning: This travel request exceeds the currently available project budget."
                if budget_summary["over_available"]
                else ""
            ),
        }
    current_task = workflow_ui["current_task"]

    current_task_ui = {
        "task": current_task,
        "assignment_label": workflow_ui["current_task_assignment_label"],
        "can_claim": workflow_ui["can_claim_current_task"],
        "can_release": workflow_ui["can_release_current_task"],
        "can_approve": workflow_ui["can_approve_current_task"],
        "can_return": workflow_ui["can_return_current_task"],
        "can_reject": workflow_ui["can_reject_current_task"],
        "claim_url": reverse("travel:task_claim", args=[travel_request.id, current_task.id]) if current_task else "",
        "release_url": reverse("travel:task_release", args=[travel_request.id, current_task.id]) if current_task else "",
        "approve_url": reverse("travel:task_approve", args=[travel_request.id, current_task.id]) if current_task else "",
        "return_url": reverse("travel:task_return", args=[travel_request.id, current_task.id]) if current_task else "",
        "reject_url": reverse("travel:task_reject", args=[travel_request.id, current_task.id]) if current_task else "",
        "due_at": current_task.due_at if current_task else None,
        "completed_at": current_task.completed_at if current_task else None,
        "due_status": current_task.due_status_label if current_task else "-",
        "is_overdue": current_task.is_overdue if current_task else False,
        "notification_logs": notification_logs,
    }

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
    budget_meaning = {
        "rows": [
            {
                "label": "Reserved Amount",
                "meaning": "Budget currently held by submitted or approved requests that has not yet become actual spending.",
            },
            {
                "label": "Consumed Amount",
                "meaning": "Budget already converted into actual spending.",
            },
            {
                "label": "Reserved Remaining for This Request",
                "meaning": "Budget still reserved under this travel request and not yet released or consumed.",
            },
            {
                "label": "Remaining After This Request",
                "meaning": "Available Amount - This Request Total.",
            },
        ]
    }

    request_header = {
        "request_label": "Travel Request",
        "request_no": travel_request.travel_no,
        "request_title": travel_request.purpose,
        "request_status": travel_request.get_status_display(),
        "requester": travel_request.requester,
        "request_department": travel_request.request_department,
        "project": travel_request.project,
        "matched_rule": travel_request.matched_rule,
        "current_step": workflow_ui["current_step"],
        "current_approver": workflow_ui["current_approver"],
        "approval_progress": workflow_ui["approval_progress"],
        "current_task_assignment_label": workflow_ui["current_task_assignment_label"],
        "request_currency": travel_request.currency,
        "request_amount": travel_request.estimated_total,
    }

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

    for attachment in attachments:
        attachment.delete_url = reverse(
            "travel:tr_delete_attachment",
            args=[travel_request.id, attachment.id],
        )

    attachments_ui = {
        "can_manage": ui_flags["can_manage_attachments"],
        "upload_url": reverse("travel:tr_upload_attachment", args=[travel_request.id]),
    }
    request_ct = ContentType.objects.get_for_model(travel_request.__class__)
    approval_tasks = list(
        ApprovalTask.objects.filter(
            request_content_type=request_ct,
            request_object_id=travel_request.id,
        ).select_related("assigned_user").order_by("step_no", "id")
    )
    approval_workflow_ui = {
        "rows": [
            {
                "step_no": task.step_no,
                "step_name": task.step_name,
                "status": task.get_status_display() if hasattr(task, "get_status_display") else task.status,
                "assigned_user": task.assigned_user,
                "comment": task.comment,
                "due_at": task.due_at,
                "completed_at": task.completed_at,
                "due_status": task.due_status_label,
            }
            for task in approval_tasks
        ]
    }

    detail_actions = {
        "back_url": reverse("travel:tr_list"),
        "project_budget_url": (
            reverse("projects:project_budget_ledger", args=[travel_request.project.id])
            if travel_request.project
            else ""
        ),
        "edit_url": reverse("travel:tr_edit", args=[travel_request.id]),
        "submit_url": reverse("travel:tr_submit", args=[travel_request.id]),
        "cancel_url": reverse("travel:tr_cancel", args=[travel_request.id]),
        "can_edit": ui_flags["can_edit"],
        "can_submit": ui_flags["can_submit"],
        "can_cancel": ui_flags["can_cancel"],
    }

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
        "budget_summary": budget_summary,
        "reserved_remaining": travel_request.get_reserved_remaining_amount(),
        "request_header": request_header,
        "detail_actions": detail_actions,
        "current_task_ui": current_task_ui,
        "budget_meaning": budget_meaning,
        "budget_snapshot_ui": budget_snapshot_ui,
        "attachments_ui": attachments_ui,
        "approval_workflow_ui": approval_workflow_ui,
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
def task_claim(request, pk, task_id):
    return handle_task_action(
        request,
        request_obj_queryset=TravelRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        success_message="Task '{step_name}' claimed successfully.",
        detail_route_name="travel:tr_detail",
        action=lambda task, user: task.claim(user),
        use_generic_request_object=True,
    )


@login_required
@require_POST
def task_release(request, pk, task_id):
    return handle_task_action(
        request,
        request_obj_queryset=TravelRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        success_message="Task '{step_name}' released back to pool.",
        detail_route_name="travel:tr_detail",
        action=lambda task, user: task.release_to_pool(user),
        use_generic_request_object=True,
    )


@login_required
@require_POST
def task_approve(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=TravelRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        success_message="Task '{step_name}' approved successfully.",
        detail_route_name="travel:tr_detail",
        action=lambda task, user, comment: task.approve(user, comment=comment),
        comment=comment,
        use_generic_request_object=True,
    )


@login_required
@require_POST
def task_return(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=TravelRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        success_message="Task '{step_name}' returned successfully.",
        detail_route_name="travel:tr_detail",
        action=lambda task, user, comment: task.return_to_requester(user, comment=comment),
        comment=comment,
        use_generic_request_object=True,
    )


@login_required
@require_POST
def task_reject(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=TravelRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        success_message="Task '{step_name}' rejected successfully.",
        detail_route_name="travel:tr_detail",
        action=lambda task, user, comment: task.reject(user, comment=comment),
        comment=comment,
        use_generic_request_object=True,
    )

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