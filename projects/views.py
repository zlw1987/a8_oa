from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from common.choices import BudgetEntryType, RequestType
from purchase.models import PurchaseRequest
from travel.models import TravelRequest
from .models import Project, ProjectBudgetEntry


def _get_visible_projects_queryset(user):
    qs = Project.objects.select_related("project_manager", "owning_department")

    if user.is_superuser:
        return qs

    filters = (
        Q(project_manager=user)
        | Q(purchase_requests__requester=user)
        | Q(travel_requests__requester=user)
    )

    primary_department = getattr(user, "primary_department", None)
    if primary_department:
        filters |= Q(owning_department=primary_department)

    return qs.filter(filters).distinct()


def _sum_budget_entries(project, entry_type, source_type=None):
    qs = ProjectBudgetEntry.objects.filter(project=project, entry_type=entry_type)
    if source_type:
        qs = qs.filter(source_type=source_type)
    return qs.aggregate(total=Sum("amount"))["total"] or 0


def _decorate_budget_entries(entries):
    purchase_ids = [entry.source_id for entry in entries if entry.source_type == RequestType.PURCHASE]
    travel_ids = [entry.source_id for entry in entries if entry.source_type == RequestType.TRAVEL]

    purchase_map = {
        obj.id: obj
        for obj in PurchaseRequest.objects.filter(id__in=purchase_ids).only("id", "pr_no")
    }
    travel_map = {
        obj.id: obj
        for obj in TravelRequest.objects.filter(id__in=travel_ids).only("id", "travel_no")
    }

    for entry in entries:
        entry.source_no = f"{entry.source_type} #{entry.source_id}"
        entry.source_detail_url = ""

        if entry.source_type == RequestType.PURCHASE:
            purchase = purchase_map.get(entry.source_id)
            if purchase:
                entry.source_no = purchase.pr_no
                entry.source_detail_url = reverse("purchase:pr_detail", args=[purchase.id])

        elif entry.source_type == RequestType.TRAVEL:
            travel = travel_map.get(entry.source_id)
            if travel:
                entry.source_no = travel.travel_no
                entry.source_detail_url = reverse("travel:tr_detail", args=[travel.id])

    return entries


@login_required
def project_budget_ledger(request, pk):
    project = get_object_or_404(_get_visible_projects_queryset(request.user), pk=pk)

    entries = list(
        ProjectBudgetEntry.objects.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at", "-id")
    )
    _decorate_budget_entries(entries)

    context = {
        "project": project,
        "entries": entries,
        "budget_amount": project.budget_amount,
        "reserved_amount": project.get_reserved_amount(),
        "consumed_amount": project.get_consumed_amount(),
        "released_total": _sum_budget_entries(project, BudgetEntryType.RELEASE),
        "adjust_total": _sum_budget_entries(project, BudgetEntryType.ADJUST),
        "available_amount": project.get_available_amount(),
        "purchase_reserved": _sum_budget_entries(project, BudgetEntryType.RESERVE, RequestType.PURCHASE),
        "purchase_consumed": _sum_budget_entries(project, BudgetEntryType.CONSUME, RequestType.PURCHASE),
        "purchase_released": _sum_budget_entries(project, BudgetEntryType.RELEASE, RequestType.PURCHASE),
        "travel_reserved": _sum_budget_entries(project, BudgetEntryType.RESERVE, RequestType.TRAVEL),
        "travel_consumed": _sum_budget_entries(project, BudgetEntryType.CONSUME, RequestType.TRAVEL),
        "travel_released": _sum_budget_entries(project, BudgetEntryType.RELEASE, RequestType.TRAVEL),
    }
    return render(request, "projects/project_budget_ledger.html", context)