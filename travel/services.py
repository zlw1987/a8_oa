from decimal import Decimal

from django.db import transaction

from .audit import (
    snapshot_travel_header,
    snapshot_travel_itineraries,
    snapshot_travel_expenses,
    log_travel_create_content_audit,
    log_travel_edit_content_audit,
)


@transaction.atomic
def create_travel_request_from_forms(*, form, itinerary_formset, expense_formset, acting_user):
    travel_request = form.save(commit=False)

    if not acting_user.is_superuser:
        travel_request.requester = acting_user

    travel_request.estimated_total = Decimal("0.00")
    travel_request.save()

    itinerary_formset.instance = travel_request
    itinerary_formset.save()

    expense_formset.instance = travel_request
    expense_formset.save()

    travel_request.refresh_estimated_total(commit=True)

    log_travel_create_content_audit(travel_request, acting_user)

    return travel_request


@transaction.atomic
def update_travel_request_from_forms(
    *,
    travel_request,
    form,
    itinerary_formset,
    expense_formset,
    acting_user,
):
    old_header_snapshot = snapshot_travel_header(travel_request)
    old_itinerary_snapshot = snapshot_travel_itineraries(travel_request)
    old_expense_snapshot = snapshot_travel_expenses(travel_request)

    travel_request = form.save(commit=False)

    if not acting_user.is_superuser:
        travel_request.requester = acting_user

    travel_request.save()

    itinerary_formset.instance = travel_request
    itinerary_formset.save()

    expense_formset.instance = travel_request
    expense_formset.save()

    travel_request.refresh_estimated_total(commit=True)

    log_travel_edit_content_audit(
        travel_request,
        old_header_snapshot,
        old_itinerary_snapshot,
        old_expense_snapshot,
        acting_user,
    )

    return travel_request