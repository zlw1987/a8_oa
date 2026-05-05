from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse

from approvals.action_handlers import handle_task_action
from .filters import PurchaseRequestListFilterForm
from approvals.models import ApprovalTask
from projects.presentation import build_project_budget_summary
from common.choices import ApprovalTaskStatus, RequestStatus
from .forms import (
    PurchaseRequestForm,
    PurchaseRequestLineCreateFormSet,
    PurchaseRequestLineEditFormSet,
    PurchaseRequestAttachmentForm,
    PurchaseActualSpendForm,
)
from .models import (
    PurchaseRequest,
    PurchaseRequestAttachment,
)
from purchase.access import (
    user_can_view_purchase,
    user_can_edit_purchase,
    user_can_submit_purchase,
    user_can_cancel_purchase,
    enforce_purchase_permission,
    user_can_manage_attachment,
    user_can_close_purchase,
    user_can_record_actual_spend,
)
from approvals.access import (
    user_can_claim_task,
    user_can_release_task,
    user_can_approve_task,
    user_can_return_task,
    user_can_reject_task,
    enforce_approval_permission,
)
from .presentation import (
    decorate_purchase_list_item,
    build_purchase_detail_ui_flags,
)
from approvals.presentation import build_request_workflow_context
from .audit import (
    snapshot_request_header,
    snapshot_request_lines,
    log_create_content_audit,
    log_edit_content_audit,
)
from .services import (
    create_purchase_request_from_forms,
    update_purchase_request_from_forms,
)

def _get_request_total_from_formset(formset):
    total = Decimal("0.00")

    for line_form in formset.forms:
        cleaned_data = getattr(line_form, "cleaned_data", None)
        if not cleaned_data:
            continue

        if cleaned_data.get("DELETE"):
            continue

        item_name = cleaned_data.get("item_name")
        if not item_name:
            continue

        quantity = cleaned_data.get("quantity") or Decimal("0.00")
        unit_price = cleaned_data.get("unit_price") or Decimal("0.00")
        total += quantity * unit_price

    return total


def _build_budget_summary(project, request_total):
    if not project:
        return None

    reserved_amount = project.get_reserved_amount()
    available_amount = project.get_available_amount()
    remaining_after_request = available_amount - request_total

    return {
        "project_code": project.project_code,
        "project_name": project.project_name,
        "budget_amount": project.budget_amount,
        "reserved_amount": reserved_amount,
        "available_amount": available_amount,
        "request_total": request_total,
        "remaining_after_request": remaining_after_request,
        "over_available": request_total > available_amount,
    }


def _build_querystring(request_get, exclude_keys=None):
    params = request_get.copy()
    exclude_keys = exclude_keys or []

    for key in exclude_keys:
        if key in params:
            del params[key]

    return params.urlencode()

@login_required
def pr_list(request):
    queryset = (
        PurchaseRequest.get_visible_queryset(request.user)
        .select_related("requester", "request_department", "project", "matched_rule")
        .order_by("-request_date", "-id")
    )

    filter_form = PurchaseRequestListFilterForm(
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
                Q(pr_no__icontains=keyword)
                | Q(title__icontains=keyword)
                | Q(justification__icontains=keyword)
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

    for pr in page_obj.object_list:
        decorate_purchase_list_item(pr, request.user, RequestStatus)

    querydict = request.GET.copy()
    querydict.pop("page", None)
    filter_query = querydict.urlencode()

    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "pagination_querystring": filter_query,
    }
    return render(request, "purchase/pr_list.html", context)

@login_required
def pr_detail(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    enforce_purchase_permission(user_can_view_purchase(request.user, purchase_request))

    lines = purchase_request.lines.all().order_by("line_no")
    attachments = purchase_request.attachments.all()
    actual_spend_entries = purchase_request.actual_spend_entries.all()
    content_audits = purchase_request.content_audits.all()
    approval_tasks = purchase_request.approval_tasks.all().order_by("step_no")
    histories = purchase_request.history_entries.all()

    workflow_ui = build_request_workflow_context(purchase_request, request.user)

    current_task = workflow_ui["current_task"]

    current_task_ui = {
        "task": current_task,
        "assignment_label": workflow_ui["current_task_assignment_label"],
        "can_claim": workflow_ui["can_claim_current_task"],
        "can_release": workflow_ui["can_release_current_task"],
        "can_approve": workflow_ui["can_approve_current_task"],
        "can_return": workflow_ui["can_return_current_task"],
        "can_reject": workflow_ui["can_reject_current_task"],
        "claim_url": reverse("purchase:task_claim", args=[purchase_request.id, current_task.id]) if current_task else "",
        "release_url": reverse("purchase:task_release", args=[purchase_request.id, current_task.id]) if current_task else "",
        "approve_url": reverse("purchase:task_approve", args=[purchase_request.id, current_task.id]) if current_task else "",
        "return_url": reverse("purchase:task_return", args=[purchase_request.id, current_task.id]) if current_task else "",
        "reject_url": reverse("purchase:task_reject", args=[purchase_request.id, current_task.id]) if current_task else "",
        "due_at": current_task.due_at if current_task else None,
        "completed_at": current_task.completed_at if current_task else None,
        "due_status": current_task.due_status_label if current_task else "-",
        "is_overdue": current_task.is_overdue if current_task else False,
    }

    budget_summary = build_project_budget_summary(
        purchase_request.project,
        purchase_request.get_lines_total(),
    )   

    budget_snapshot_ui = None
    if budget_summary:
        budget_snapshot_ui = {
            "cards": [
                {
                    "label": "This Request Total",
                    "value": f"{purchase_request.currency} {budget_summary['request_total']}",
                },
                {
                    "label": "Available Amount",
                    "value": f"{purchase_request.currency} {budget_summary['available_amount']}",
                },
                {
                    "label": "Reserved Amount",
                    "value": f"{purchase_request.currency} {budget_summary['reserved_amount']}",
                },
                {
                    "label": "Remaining After This Request",
                    "value": f"{purchase_request.currency} {budget_summary['remaining_after_request']}",
                },
            ],
            "rows": [
                {
                    "label": "Project",
                    "value": f"{budget_summary['project_code']} - {budget_summary['project_name']}",
                },
                {
                    "label": "Project Budget",
                    "value": f"{purchase_request.currency} {budget_summary['budget_amount']}",
                },
            ],
            "warning": (
                "Warning: This request exceeds the currently available project budget."
                if budget_summary["over_available"]
                else ""
            ),
        }

    budget_meaning = {
        "rows": [
            {
                "label": "Project Budget",
                "meaning": "Original project budget before manual adjustments.",
            },
            {
                "label": "Reserved Amount",
                "meaning": "Budget already held by submitted or approved requests but not yet fully converted into actual spending.",
            },
            {
                "label": "Available Amount",
                "meaning": "Budget currently available for new requests and approved overspend.",
            },
            {
                "label": "This Request Total",
                "meaning": "Total amount this purchase request plans to use.",
            },
            {
                "label": "Remaining After This Request",
                "meaning": "Available Amount - This Request Total.",
            },
        ]
    }

    request_header = {
        "request_label": "Purchase Request",
        "request_no": purchase_request.pr_no,
        "request_title": purchase_request.title,
        "request_status": purchase_request.get_status_display(),
        "requester": purchase_request.requester,
        "request_department": purchase_request.request_department,
        "project": purchase_request.project,
        "matched_rule": purchase_request.matched_rule,
        "current_step": workflow_ui["current_step"],
        "current_approver": workflow_ui["current_approver"],
        "approval_progress": workflow_ui["approval_progress"],
        "current_task_assignment_label": workflow_ui["current_task_assignment_label"],
        "request_currency": purchase_request.currency,
        "request_amount": purchase_request.estimated_total,
    }

    ui_flags = build_purchase_detail_ui_flags(
        purchase_request,
        request.user,
        workflow_ui["current_task"],
    )

    attachment_form = (
        PurchaseRequestAttachmentForm()
        if ui_flags["show_attachment_form"]
        else None
    )

    attachments_ui = {
        "can_manage": ui_flags["can_manage_attachments"],
        "upload_url": reverse("purchase:pr_upload_attachment", args=[purchase_request.id]),
    }

    for attachment in attachments:
        attachment.delete_url = reverse(
            "purchase:pr_delete_attachment",
            args=[purchase_request.id, attachment.id],
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

     
    actual_spend_form = (
        PurchaseActualSpendForm(initial=ui_flags["actual_spend_initial"])
        if ui_flags["show_actual_spend_form"]
        else None
    )
    detail_actions = {
        "back_url": reverse("purchase:pr_list"),
        "project_budget_url": (
            reverse("projects:project_budget_ledger", args=[purchase_request.project.id])
            if purchase_request.project
            else ""
        ),
        "edit_url": reverse("purchase:pr_edit", args=[purchase_request.id]),
        "submit_url": reverse("purchase:pr_submit", args=[purchase_request.id]),
        "cancel_url": reverse("purchase:pr_cancel", args=[purchase_request.id]),
        "can_edit": ui_flags["can_edit"],
        "can_submit": ui_flags["can_submit"],
        "can_cancel": ui_flags["can_cancel"],
    }
    context = {
        "purchase_request": purchase_request,
        "lines": lines,
        "approval_tasks": approval_tasks,
        "histories": histories,

        "current_task": workflow_ui["current_task"],
        "current_step": workflow_ui["current_step"],
        "current_approver": workflow_ui["current_approver"],
        "approval_progress": workflow_ui["approval_progress"],
        "can_claim_current_task": workflow_ui["can_claim_current_task"],
        "can_release_current_task": workflow_ui["can_release_current_task"],
        "can_approve_current_task": workflow_ui["can_approve_current_task"],
        "can_return_current_task": workflow_ui["can_return_current_task"],
        "can_reject_current_task": workflow_ui["can_reject_current_task"],

        "budget_summary": budget_summary,

        "can_edit": ui_flags["can_edit"],
        "can_submit": ui_flags["can_submit"],
        "can_cancel": ui_flags["can_cancel"],

        "can_manage_attachments": ui_flags["can_manage_attachments"],
        "can_record_actual_spend": ui_flags["can_record_actual_spend"],
        "can_close_purchase": ui_flags["can_close_purchase"],

        "content_audits":content_audits,
        "attachments": attachments,
        "attachment_form": attachment_form,
        "actual_spend_entries": actual_spend_entries,
        "actual_spent_total": purchase_request.get_actual_spent_total(),
        "actual_spend_form": actual_spend_form,
        "reserved_remaining": purchase_request.get_reserved_remaining_amount(),
        "current_task_assignment_label": workflow_ui["current_task_assignment_label"],
        "request_header": request_header,
        "detail_actions": detail_actions,
        "current_task_ui": current_task_ui,
        "budget_meaning": budget_meaning,
        "budget_snapshot_ui": budget_snapshot_ui,
        "attachments_ui": attachments_ui,
        "approval_workflow_ui": approval_workflow_ui,
    }
    return render(request, "purchase/pr_detail.html", context)


@login_required
def pr_create(request):
    if request.method == "POST":
        action = request.POST.get("action", "draft")

        form = PurchaseRequestForm(request.POST, user=request.user)
        formset = PurchaseRequestLineCreateFormSet(request.POST, prefix="lines")

        form_valid = form.is_valid()
        formset_valid = formset.is_valid()

        selected_project = form.cleaned_data.get("project") if form_valid else None
        request_total = _get_request_total_from_formset(formset) if formset_valid else Decimal("0.00")
        budget_summary = _build_budget_summary(selected_project, request_total)

        if form_valid and formset_valid:
            try:
                purchase_request = create_purchase_request_from_forms(
                    form=form,
                    formset=formset,
                    acting_user=request.user,
                    action=action,
                )

                if action == "submit":
                    messages.success(request, f"{purchase_request.pr_no} submitted successfully.")
                else:
                    messages.success(request, f"{purchase_request.pr_no} saved as draft.")

                return redirect("purchase:pr_detail", pk=purchase_request.pk)

            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
    else:
        initial = {
            "request_date": date.today(),
            "currency": "USD",
        }
        form = PurchaseRequestForm(user=request.user, initial=initial)
        formset = PurchaseRequestLineCreateFormSet(prefix="lines")
        budget_summary = None

    context = {
        "form": form,
        "formset": formset,
        "page_mode": "create",
        "budget_summary": budget_summary,
        "auto_numbering": True,
    }
    return render(request, "purchase/pr_edit.html", context)


@login_required
def pr_edit(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not user_can_edit_purchase(request.user, purchase_request):
        messages.error(
            request,
            f"{purchase_request.pr_no} cannot be edited by you in its current status."
        )
        return redirect("purchase:pr_detail", pk=purchase_request.pk)

    if request.method == "POST":
        action = request.POST.get("action", "draft")

        old_header_snapshot = snapshot_request_header(purchase_request)
        old_line_snapshot = snapshot_request_lines(purchase_request)

        form = PurchaseRequestForm(request.POST, instance=purchase_request, user=request.user)
        formset = PurchaseRequestLineEditFormSet(
            request.POST,
            instance=purchase_request,
            prefix="lines",
        )

        form_valid = form.is_valid()
        formset_valid = formset.is_valid()

        selected_project = form.cleaned_data.get("project") if form_valid else purchase_request.project
        request_total = (
            _get_request_total_from_formset(formset)
            if formset_valid
            else purchase_request.get_lines_total()
        )
        budget_summary = _build_budget_summary(selected_project, request_total)

        if form_valid and formset_valid:
            try:
                purchase_request = update_purchase_request_from_forms(
                    purchase_request=purchase_request,
                    form=form,
                    formset=formset,
                    acting_user=request.user,
                    action=action,
                )

                if action == "submit":
                    messages.success(request, f"{purchase_request.pr_no} updated and submitted successfully.")
                else:
                    messages.success(request, f"{purchase_request.pr_no} updated successfully.")

                return redirect("purchase:pr_detail", pk=purchase_request.pk)

            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
    else:
        form = PurchaseRequestForm(instance=purchase_request, user=request.user)
        formset = PurchaseRequestLineEditFormSet(
            instance=purchase_request,
            prefix="lines",
        )
        budget_summary = _build_budget_summary(
            purchase_request.project,
            purchase_request.get_lines_total(),
        )

    context = {
        "form": form,
        "formset": formset,
        "purchase_request": purchase_request,
        "page_mode": "edit",
        "budget_summary": budget_summary,
        "auto_numbering": False,
    }
    return render(request, "purchase/pr_edit.html", context)

@login_required
@require_POST
def pr_upload_attachment(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_manage_attachment(request.user, purchase_request)
    )

    form = PurchaseRequestAttachmentForm(request.POST, request.FILES)

    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.purchase_request = purchase_request
        attachment.uploaded_by = request.user
        attachment.save()
        messages.success(request, f"Attachment '{attachment.title}' uploaded successfully.")
    else:
        for field_name, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field_name}: {error}")

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def pr_delete_attachment(request, pk, attachment_id):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_manage_attachment(request.user, purchase_request)
    )

    attachment = get_object_or_404(
        PurchaseRequestAttachment,
        pk=attachment_id,
        purchase_request=purchase_request,
    )

    attachment_title = attachment.title or attachment.filename
    attachment.delete()
    messages.success(request, f"Attachment '{attachment_title}' deleted successfully.")

    return redirect("purchase:pr_detail", pk=purchase_request.pk)

@login_required
@require_POST
def pr_close(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_close_purchase(request.user, purchase_request)
    )

    comment = request.POST.get("comment", "").strip()

    try:
        purchase_request.close_purchase(
            acting_user=request.user,
            comment=comment,
        )
        messages.success(
            request,
            f"{purchase_request.pr_no} closed successfully."
        )
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)

@login_required
@require_POST
def pr_record_actual_spend(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_record_actual_spend(request.user, purchase_request)
    )

    form = PurchaseActualSpendForm(request.POST)

    if form.is_valid():
        try:
            purchase_request.record_actual_spend(
                spend_date=form.cleaned_data["spend_date"],
                amount=form.cleaned_data["amount"],
                acting_user=request.user,
                vendor_name=form.cleaned_data.get("vendor_name", ""),
                reference_no=form.cleaned_data.get("reference_no", ""),
                notes=form.cleaned_data.get("notes", ""),
            )
            messages.success(
                request,
                f"Actual spend recorded successfully for {purchase_request.pr_no}."
            )
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
    else:
        for field_name, errors in form.errors.items():
            label = form.fields[field_name].label or field_name
            for error in errors:
                messages.error(request, f"{label}: {error}")

    return redirect("purchase:pr_detail", pk=purchase_request.pk)

@login_required
@require_POST
def pr_submit(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_submit_purchase(request.user, purchase_request)
    )

    try:
        purchase_request.submit(acting_user=request.user)
        messages.success(request, f"{purchase_request.pr_no} submitted successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def pr_cancel(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    enforce_purchase_permission(
        user_can_cancel_purchase(request.user, purchase_request)
    )

    try:
        purchase_request.cancel(acting_user=request.user)
        messages.success(request, f"{purchase_request.pr_no} cancelled successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def task_claim(request, pk, task_id):
    return handle_task_action(
        request,
        request_obj_queryset=PurchaseRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        request_fk_name="purchase_request",
        success_message="Task '{step_name}' claimed successfully.",
        detail_route_name="purchase:pr_detail",
        action=lambda task, user: task.claim(user),
    )


@login_required
@require_POST
def task_release(request, pk, task_id):
    return handle_task_action(
        request,
        request_obj_queryset=PurchaseRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        request_fk_name="purchase_request",
        success_message="Task '{step_name}' released back to pool.",
        detail_route_name="purchase:pr_detail",
        action=lambda task, user: task.release_to_pool(user),
    )


@login_required
@require_POST
def task_approve(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=PurchaseRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        request_fk_name="purchase_request",
        success_message="Task '{step_name}' approved successfully.",
        detail_route_name="purchase:pr_detail",
        action=lambda task, user, comment: task.approve(user, comment=comment),
        comment=comment,
    )


@login_required
@require_POST
def task_return(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=PurchaseRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        request_fk_name="purchase_request",
        success_message="Task '{step_name}' returned successfully.",
        detail_route_name="purchase:pr_detail",
        action=lambda task, user, comment: task.return_to_requester(user, comment=comment),
        comment=comment,
    )


@login_required
@require_POST
def task_reject(request, pk, task_id):
    comment = request.POST.get("comment", "").strip()
    return handle_task_action(
        request,
        request_obj_queryset=PurchaseRequest.get_visible_queryset(request.user),
        request_pk=pk,
        task_id=task_id,
        request_fk_name="purchase_request",
        success_message="Task '{step_name}' rejected successfully.",
        detail_route_name="purchase:pr_detail",
        action=lambda task, user, comment: task.reject(user, comment=comment),
        comment=comment,
    )