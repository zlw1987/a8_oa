from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
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
)
from .models import (
    PurchaseRequest,
    PurchaseRequestAttachment,
    PurchaseRequestContentAuditActionType,
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


def _get_request_status_badge_class(status):
    mapping = {
        RequestStatus.DRAFT: "badge-neutral",
        RequestStatus.SUBMITTED: "badge-warning",
        RequestStatus.PENDING: "badge-warning",
        RequestStatus.APPROVED: "badge-success",
        RequestStatus.REJECTED: "badge-danger",
        RequestStatus.RETURNED: "badge-info",
        RequestStatus.CANCELLED: "badge-dark",
        RequestStatus.CLOSED: "badge-dark",
    }
    return mapping.get(status, "badge-neutral")

def _stringify_audit_value(value):
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


def _snapshot_request_header(purchase_request):
    return {
        "title": purchase_request.title or "",
        "request_department": str(purchase_request.request_department) if purchase_request.request_department else "",
        "project": str(purchase_request.project) if purchase_request.project else "",
        "request_date": _stringify_audit_value(purchase_request.request_date),
        "needed_by_date": _stringify_audit_value(purchase_request.needed_by_date),
        "currency": purchase_request.currency or "",
        "justification": purchase_request.justification or "",
        "vendor_suggestion": purchase_request.vendor_suggestion or "",
        "delivery_location": purchase_request.delivery_location or "",
        "notes": purchase_request.notes or "",
    }


def _snapshot_request_lines(purchase_request):
    data = {}

    for line in purchase_request.lines.all().order_by("line_no", "id"):
        data[line.id] = {
            "line_no": line.line_no,
            "item_name": line.item_name or "",
            "item_description": line.item_description or "",
            "quantity": _stringify_audit_value(line.quantity),
            "uom": line.get_uom_display() if hasattr(line, "get_uom_display") else (line.uom or ""),
            "unit_price": _stringify_audit_value(line.unit_price),
            "notes": line.notes or "",
        }

    return data


def _format_line_summary(line_data):
    return (
        f"{line_data.get('item_name', '')} / "
        f"Qty {line_data.get('quantity', '')} / "
        f"UOM {line_data.get('uom', '')} / "
        f"Unit Price {line_data.get('unit_price', '')}"
    )


def _log_create_content_audit(purchase_request, acting_user):
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
            "quantity": _stringify_audit_value(line.quantity),
            "uom": line.get_uom_display() if hasattr(line, "get_uom_display") else (line.uom or ""),
            "unit_price": _stringify_audit_value(line.unit_price),
            "notes": line.notes or "",
        }

        purchase_request._add_content_audit(
            action_type=PurchaseRequestContentAuditActionType.LINE_ADDED,
            changed_by=acting_user,
            line_no=line.line_no,
            new_value=_format_line_summary(line_snapshot),
            notes="Initial line added during create.",
        )


def _log_edit_content_audit(purchase_request, old_header, old_lines, acting_user):
    new_header = _snapshot_request_header(purchase_request)
    new_lines = _snapshot_request_lines(purchase_request)

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
            old_value=_format_line_summary(old_line),
            notes="Line deleted.",
        )

    for added_id in sorted(new_ids - old_ids):
        new_line = new_lines[added_id]
        purchase_request._add_content_audit(
            action_type=PurchaseRequestContentAuditActionType.LINE_ADDED,
            changed_by=acting_user,
            line_no=new_line.get("line_no"),
            new_value=_format_line_summary(new_line),
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
        pr.current_step = pr.get_current_step_name()
        pr.current_approver = pr.get_current_approver()
        pr.approval_progress = pr.get_approval_progress_text()
        pr.can_edit = pr.can_user_edit(request.user)
        pr.status_badge_class = _get_request_status_badge_class(pr.status)

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

    lines = purchase_request.lines.all().order_by("line_no")
    attachments = purchase_request.attachments.all()
    content_audits = purchase_request.content_audits.all()
    approval_tasks = purchase_request.approval_tasks.all().order_by("step_no")
    histories = purchase_request.history_entries.all()
    current_task = purchase_request.get_current_task()
    budget_summary = _build_budget_summary(
        purchase_request.project,
        purchase_request.get_lines_total(),
    )

    can_edit = purchase_request.can_user_edit(request.user)
    attachment_form = PurchaseRequestAttachmentForm() if can_edit else None
    can_submit = purchase_request.can_user_submit(request.user)
    can_cancel = purchase_request.can_user_cancel(request.user)

    can_claim_current_task = False
    can_release_current_task = False
    can_approve_current_task = False
    can_return_current_task = False
    can_reject_current_task = False

    if current_task:
        can_claim_current_task = (
            current_task.status == ApprovalTaskStatus.POOL
            and current_task.can_user_claim(request.user)
        )

        can_release_current_task = (
            current_task.status == ApprovalTaskStatus.PENDING
            and current_task.assigned_user_id == request.user.id
            and current_task.candidates.exists()
        )

        can_approve_current_task = (
            current_task.status == ApprovalTaskStatus.PENDING
            and current_task.assigned_user_id == request.user.id
        )

        can_return_current_task = (
            current_task.status == ApprovalTaskStatus.PENDING
            and current_task.assigned_user_id == request.user.id
        )

        can_reject_current_task = (
            current_task.status == ApprovalTaskStatus.PENDING
            and current_task.assigned_user_id == request.user.id
        )

    context = {
        "purchase_request": purchase_request,
        "lines": lines,
        "approval_tasks": approval_tasks,
        "histories": histories,
        "current_task": current_task,
        "current_step": purchase_request.get_current_step_name(),
        "current_approver": purchase_request.get_current_approver(),
        "approval_progress": purchase_request.get_approval_progress_text(),
        "budget_summary": budget_summary,
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_cancel": can_cancel,
        "can_claim_current_task": can_claim_current_task,
        "can_release_current_task": can_release_current_task,
        "can_approve_current_task": can_approve_current_task,
        "can_return_current_task": can_return_current_task,
        "can_reject_current_task": can_reject_current_task,
        "content_audits":content_audits,
        "attachments": attachments,
        "attachment_form": attachment_form,
        "can_manage_attachments": can_edit,
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
                with transaction.atomic():
                    purchase_request = form.save(commit=False)

                    if not request.user.is_superuser:
                        purchase_request.requester = request.user

                    purchase_request.status = RequestStatus.DRAFT
                    purchase_request.estimated_total = 0
                    purchase_request.matched_rule = None
                    purchase_request.save()

                    formset.instance = purchase_request
                    formset.save()

                    purchase_request.estimated_total = purchase_request.get_lines_total()
                    purchase_request.save(update_fields=["estimated_total"])

                    _log_create_content_audit(purchase_request, request.user)

                    if action == "submit":
                        purchase_request.submit(acting_user=request.user)
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

    if not purchase_request.can_user_edit(request.user):
        messages.error(
            request,
            f"{purchase_request.pr_no} cannot be edited by you in its current status."
        )
        return redirect("purchase:pr_detail", pk=purchase_request.pk)

    if request.method == "POST":
        action = request.POST.get("action", "draft")

        old_header_snapshot = _snapshot_request_header(purchase_request)
        old_line_snapshot = _snapshot_request_lines(purchase_request)

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
                with transaction.atomic():
                    purchase_request = form.save(commit=False)

                    if not request.user.is_superuser:
                        purchase_request.requester = request.user

                    purchase_request.save()

                    formset.instance = purchase_request
                    formset.save()

                    purchase_request.estimated_total = purchase_request.get_lines_total()
                    purchase_request.save(update_fields=["estimated_total"])

                    _log_edit_content_audit(
                        purchase_request,
                        old_header_snapshot,
                        old_line_snapshot,
                        request.user,
                    )

                    if action == "submit":
                        purchase_request.submit(acting_user=request.user)
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

    if not purchase_request.can_user_edit(request.user):
        raise PermissionDenied("You do not have permission to upload attachments for this purchase request.")

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

    if not purchase_request.can_user_edit(request.user):
        raise PermissionDenied("You do not have permission to delete attachments for this purchase request.")

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
def pr_submit(request, pk):
    purchase_request = get_object_or_404(
        PurchaseRequest.get_visible_queryset(request.user),
        pk=pk,
    )

    if not purchase_request.can_user_submit(request.user):
        raise PermissionDenied("You do not have permission to submit this purchase request.")

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

    if not purchase_request.can_user_cancel(request.user):
        raise PermissionDenied("You do not have permission to cancel this purchase request.")

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
        task.reject(request.user, comment=comment)
        messages.success(request, f"Task '{task.step_name}' rejected successfully.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)

    return redirect("purchase:pr_detail", pk=purchase_request.pk)