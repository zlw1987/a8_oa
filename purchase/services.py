from django.core.exceptions import ValidationError
from django.db import transaction

from common.choices import RequestStatus
from .audit import (
    snapshot_request_header,
    snapshot_request_lines,
    log_create_content_audit,
    log_edit_content_audit,
)


@transaction.atomic
def create_purchase_request_from_forms(*, form, formset, acting_user, action="draft"):
    purchase_request = form.save(commit=False)

    if not acting_user.is_superuser:
        purchase_request.requester = acting_user

    purchase_request.status = RequestStatus.DRAFT
    purchase_request.estimated_total = 0
    purchase_request.matched_rule = None
    purchase_request.save()

    formset.instance = purchase_request
    formset.save()

    purchase_request.estimated_total = purchase_request.get_lines_total()
    purchase_request.save(update_fields=["estimated_total"])

    log_create_content_audit(purchase_request, acting_user)

    if action == "submit":
        purchase_request.submit(acting_user=acting_user)

    return purchase_request


@transaction.atomic
def update_purchase_request_from_forms(*, purchase_request, form, formset, acting_user, action="draft"):
    old_header_snapshot = snapshot_request_header(purchase_request)
    old_line_snapshot = snapshot_request_lines(purchase_request)

    purchase_request = form.save(commit=False)

    if not acting_user.is_superuser:
        purchase_request.requester = acting_user

    purchase_request.save()

    formset.instance = purchase_request
    formset.save()

    purchase_request.estimated_total = purchase_request.get_lines_total()
    purchase_request.save(update_fields=["estimated_total"])

    log_edit_content_audit(
        purchase_request,
        old_header_snapshot,
        old_line_snapshot,
        acting_user,
    )

    if action == "submit":
        purchase_request.submit(acting_user=acting_user)

    return purchase_request