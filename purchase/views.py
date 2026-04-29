from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from approvals.models import ApprovalTask
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
    base_queryset = (
        PurchaseRequest.get_visible_queryset(request.user)
        .select_related("project", "request_department", "requester", "matched_rule")
    )

    search_q = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_project = request.GET.get("project", "").strip()

    project_options = (
        base_queryset.exclude(project__isnull=True)
        .values("project_id", "project__project_code", "project__project_name")
        .distinct()
        .order_by("project__project_code")
    )

    purchase_requests = base_queryset

    if search_q:
        purchase_requests = purchase_requests.filter(
            Q(pr_no__icontains=search_q)
            | Q(title__icontains=search_q)
            | Q(project__project_code__icontains=search_q)
            | Q(project__project_name__icontains=search_q)
        )

    if selected_status:
        purchase_requests = purchase_requests.filter(status=selected_status)

    if selected_project:
        purchase_requests = purchase_requests.filter(project_id=selected_project)

    purchase_requests = purchase_requests.order_by("-request_date", "-id")

    paginator = Paginator(purchase_requests, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    for pr in page_obj.object_list:
        decorate_purchase_list_item(pr, request.user, RequestStatus)

    context = {
        "purchase_requests": page_obj.object_list,
        "page_obj": page_obj,
        "pagination_querystring": _build_querystring(request.GET, ["page"]),
        "search_q": search_q,
        "selected_status": selected_status,
        "selected_project": selected_project,
        "status_choices": RequestStatus.choices,
        "project_options": project_options,
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
    budget_summary = _build_budget_summary(
        purchase_request.project,
        purchase_request.get_lines_total(),
    )

    workflow_ui = build_request_workflow_context(purchase_request, request.user)
    budget_summary = _build_budget_summary(
        purchase_request.project,
        purchase_request.get_lines_total(),
    )

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

    actual_spend_form = (
        PurchaseActualSpendForm(initial=ui_flags["actual_spend_initial"])
        if ui_flags["show_actual_spend_form"]
        else None
    )

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
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    task = get_object_or_404(ApprovalTask, pk=task_id, purchase_request=purchase_request)

    try:
        enforce_approval_permission(user_can_claim_task(request.user, task))
        task.claim(request.user)
        messages.success(request, f"Task '{task.step_name}' claimed successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def task_release(request, pk, task_id):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    task = get_object_or_404(ApprovalTask, pk=task_id, purchase_request=purchase_request)

    try:
        enforce_approval_permission(user_can_release_task(request.user, task))
        task.release_to_pool(request.user)
        messages.success(request, f"Task '{task.step_name}' released back to pool.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def task_approve(request, pk, task_id):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    task = get_object_or_404(ApprovalTask, pk=task_id, purchase_request=purchase_request)
    comment = request.POST.get("comment", "").strip()

    try:
        enforce_approval_permission(user_can_approve_task(request.user, task))
        task.approve(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' approved successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def task_return(request, pk, task_id):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    task = get_object_or_404(ApprovalTask, pk=task_id, purchase_request=purchase_request)
    comment = request.POST.get("comment", "").strip()

    try:
        enforce_approval_permission(user_can_return_task(request.user, task))
        task.return_to_requester(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' returned to requester successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)


@login_required
@require_POST
def task_reject(request, pk, task_id):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )
    task = get_object_or_404(ApprovalTask, pk=task_id, purchase_request=purchase_request)
    comment = request.POST.get("comment", "").strip()

    try:
        enforce_approval_permission(user_can_reject_task(request.user, task))
        task.reject(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' rejected successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)