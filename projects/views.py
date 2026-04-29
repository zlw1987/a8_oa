from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from common.choices import BudgetEntryType, RequestType
from purchase.models import PurchaseRequest
from travel.models import TravelRequest
from .forms import ProjectBudgetAdjustmentForm, ProjectCreateForm, ProjectMemberAddForm
from .models import Project, ProjectBudgetEntry, ProjectMember
from .access import (
    get_visible_projects_queryset_for_user,
    get_manageable_departments_queryset_for_user,
    user_can_create_project,
    user_can_manage_project_members,
    user_can_manage_project_budget,
)

def _can_manage_project_budget(user, project):
    if user.is_superuser:
        return True

    if project.project_manager_id == user.id:
        return True

    if getattr(project.owning_department, "manager_id", None) == user.id:
        return True

    return False


def _sum_budget_entries(project, entry_type, source_type=None):
    qs = ProjectBudgetEntry.objects.filter(project=project, entry_type=entry_type)
    if source_type:
        qs = qs.filter(source_type=source_type)
    return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

def _decorate_budget_entries(entries):
    purchase_ids = [entry.source_id for entry in entries if entry.source_type == RequestType.PURCHASE]
    travel_ids = [entry.source_id for entry in entries if entry.source_type == RequestType.TRAVEL]

    purchase_map = {
        obj.id: obj
        for obj in PurchaseRequest.objects.filter(id__in=purchase_ids).only("id", "pr_no", "title")
    }
    travel_map = {
        obj.id: obj
        for obj in TravelRequest.objects.filter(id__in=travel_ids).only("id", "travel_no", "purpose")
    }

    for entry in entries:
        entry.source_no = f"{entry.source_type} #{entry.source_id}" if entry.source_id else entry.source_type
        entry.source_detail_url = ""
        entry.source_summary = "-"
        entry.entry_type_explained = entry.entry_type
        entry.amount_direction = "neutral"

        if entry.source_type == RequestType.PURCHASE:
            purchase = purchase_map.get(entry.source_id)
            if purchase:
                entry.source_no = purchase.pr_no
                entry.source_summary = purchase.title
                entry.source_detail_url = reverse("purchase:pr_detail", args=[purchase.id])

        elif entry.source_type == RequestType.TRAVEL:
            travel = travel_map.get(entry.source_id)
            if travel:
                entry.source_no = travel.travel_no
                entry.source_summary = travel.purpose
                entry.source_detail_url = reverse("travel:tr_detail", args=[travel.id])

        elif entry.source_type == RequestType.PROJECT:
            entry.source_no = entry.project.project_code
            entry.source_summary = entry.project.project_name
            entry.source_detail_url = reverse("projects:project_detail", args=[entry.project.id])

        if entry.entry_type == BudgetEntryType.RESERVE:
            entry.entry_type_explained = "Reserve budget for submitted request"
            entry.amount_direction = "hold"
        elif entry.entry_type == BudgetEntryType.CONSUME:
            entry.entry_type_explained = "Convert budget into actual spending"
            entry.amount_direction = "use"
        elif entry.entry_type == BudgetEntryType.RELEASE:
            entry.entry_type_explained = "Release reserved budget back to available"
            entry.amount_direction = "return"
        elif entry.entry_type == BudgetEntryType.ADJUST:
            if entry.amount >= 0:
                entry.entry_type_explained = "Increase project budget"
            else:
                entry.entry_type_explained = "Decrease project budget"
            entry.amount_direction = "adjust"

    return entries


@login_required
def project_list(request):
    projects = list(
        get_visible_projects_queryset_for_user(request.user).order_by("project_code", "id")
    )

    for project in projects:
        project.project_detail_url = reverse("projects:project_detail", args=[project.id])
        project.project_budget_url = reverse("projects:project_budget_ledger", args=[project.id])

    context = {
        "projects": projects,
        "can_create_project": user_can_create_project(request.user),
        "project_create_url": reverse("projects:project_create"),
    }
    return render(request, "projects/project_list.html", context)


@login_required
def project_create(request):
    if not user_can_create_project(request.user):
        raise PermissionDenied("You do not have permission to create projects.")

    if request.method == "POST":
        form = ProjectCreateForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()

            ProjectMember.objects.get_or_create(
                project=project,
                user=request.user,
                defaults={
                    "is_active": True,
                    "added_by": request.user,
                },
            )

            if project.project_manager_id:
                ProjectMember.objects.get_or_create(
                    project=project,
                    user=project.project_manager,
                    defaults={
                        "is_active": True,
                        "added_by": request.user,
                    },
                )
            messages.success(request, f"Project {project.project_code} created successfully.")
            return redirect("projects:project_detail", pk=project.id)
    else:
        form = ProjectCreateForm(user=request.user)

    context = {
        "form": form,
    }
    return render(request, "projects/project_create.html", context)

@login_required
def project_add_member(request, pk):
    if request.method != "POST":
        return redirect("projects:project_members", pk=pk)

    project = get_object_or_404(get_visible_projects_queryset_for_user(request.user), pk=pk)

    if not user_can_manage_project_members(request.user, project):
        raise PermissionDenied("You do not have permission to manage project members.")

    form = ProjectMemberAddForm(request.POST, project=project)

    if form.is_valid():
        member_user = form.cleaned_data["user"]
        membership, created = ProjectMember.objects.get_or_create(
            project=project,
            user=member_user,
            defaults={
                "is_active": True,
                "added_by": request.user,
            },
        )

        if not created and not membership.is_active:
            membership.is_active = True
            membership.added_by = request.user
            membership.save(update_fields=["is_active", "added_by"])

        messages.success(request, f"{member_user} added to {project.project_code}.")
    else:
        for error in form.errors.get("user", []):
            messages.error(request, error)

    return redirect("projects:project_members", pk=project.pk)

@login_required
def project_remove_member(request, pk, member_id):
    if request.method != "POST":
        return redirect("projects:project_members", pk=pk)

    project = get_object_or_404(get_visible_projects_queryset_for_user(request.user), pk=pk)

    if not user_can_manage_project_members(request.user, project):
        raise PermissionDenied("You do not have permission to manage project members.")

    membership = get_object_or_404(ProjectMember, pk=member_id, project=project)

    if membership.user_id == project.project_manager_id:
        messages.error(request, "Project manager cannot be removed from project membership.")
        return redirect("projects:project_members", pk=project.pk)

    if membership.user_id == project.created_by_id:
        messages.error(request, "Project creator cannot be removed from project membership.")
        return redirect("projects:project_members", pk=project.pk)

    membership.is_active = False
    membership.save(update_fields=["is_active"])
    messages.success(request, f"{membership.user} removed from {project.project_code}.")

    return redirect("projects:project_members", pk=project.pk)

@login_required
def project_members(request, pk):
    project = get_object_or_404(get_visible_projects_queryset_for_user(request.user), pk=pk)

    if not user_can_manage_project_members(request.user, project):
        raise PermissionDenied("You do not have permission to manage project members.")

    members = project.members.select_related("user", "added_by").order_by("user__username", "id")
    form = ProjectMemberAddForm(project=project)

    context = {
        "project": project,
        "members": members,
        "form": form,
    }
    return render(request, "projects/project_members.html", context)

@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        get_visible_projects_queryset_for_user(request.user),
        pk=pk,
    )

    recent_entries = list(
        ProjectBudgetEntry.objects.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at", "-id")[:10]
    )
    _decorate_budget_entries(recent_entries)

    recent_purchase_requests = list(
        PurchaseRequest.objects.filter(project=project)
        .select_related("requester", "request_department")
        .order_by("-request_date", "-id")[:5]
    )

    recent_travel_requests = list(
        TravelRequest.objects.filter(project=project)
        .select_related("requester", "request_department")
        .order_by("-request_date", "-id")[:5]
    )

    context = {
        "project": project,
        "recent_entries": recent_entries,
        "recent_purchase_requests": recent_purchase_requests,
        "recent_travel_requests": recent_travel_requests,
        "budget_amount": project.budget_amount,
        "adjustment_amount": project.get_adjustment_amount(),
        "effective_budget_amount": project.get_effective_budget_amount(),
        "reserved_amount": project.get_reserved_amount(),
        "consumed_amount": project.get_consumed_amount(),
        "available_amount": project.get_available_amount(),
        "project_budget_url": reverse("projects:project_budget_ledger", args=[project.id]),
        "can_manage_budget": user_can_manage_project_budget(request.user, project),
        "project_adjust_budget_url": reverse("projects:project_add_budget_adjustment", args=[project.id]),
        "can_manage_members": user_can_manage_project_members(request.user, project),
    }
    return render(request, "projects/project_detail.html", context)


@login_required
def project_budget_ledger(request, pk):
    project = get_object_or_404(
        get_visible_projects_queryset_for_user(request.user),
        pk=pk,
    )

    entries = list(
        ProjectBudgetEntry.objects.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at", "-id")
    )
    for entry in entries:
        if entry.source_type == "PURCHASE":
            entry.source_label = f"Purchase #{entry.source_id}"
        elif entry.source_type == "TRAVEL":
            entry.source_label = f"Travel #{entry.source_id}"
        else:
            entry.source_label = f"{entry.source_type} #{entry.source_id}" if entry.source_id else entry.source_type

        if entry.entry_type == "RESERVE":
            entry.entry_type_explained = "Reserve budget for submitted request"
        elif entry.entry_type == "CONSUME":
            entry.entry_type_explained = "Convert budget into actual spending"
        elif entry.entry_type == "RELEASE":
            entry.entry_type_explained = "Release reserved budget back to available"
        else:
            entry.entry_type_explained = entry.entry_type
    _decorate_budget_entries(entries)

    context = {
        "project": project,
        "entries": entries,
        "budget_amount": project.budget_amount,
        "adjustment_amount": project.get_adjustment_amount(),
        "effective_budget_amount": project.get_effective_budget_amount(),
        "reserved_amount": project.get_reserved_amount(),
        "consumed_amount": project.get_consumed_amount(),
        "released_total": _sum_budget_entries(project, BudgetEntryType.RELEASE),
        "adjust_total": _sum_budget_entries(project, BudgetEntryType.ADJUST),
        "available_amount": project.get_available_amount(),
        "project_adjusted": _sum_budget_entries(project, BudgetEntryType.ADJUST, RequestType.PROJECT),
        "purchase_reserved": _sum_budget_entries(project, BudgetEntryType.RESERVE, RequestType.PURCHASE),
        "purchase_consumed": _sum_budget_entries(project, BudgetEntryType.CONSUME, RequestType.PURCHASE),
        "purchase_released": _sum_budget_entries(project, BudgetEntryType.RELEASE, RequestType.PURCHASE),
        "purchase_adjusted": _sum_budget_entries(project, BudgetEntryType.ADJUST, RequestType.PURCHASE),
        "travel_reserved": _sum_budget_entries(project, BudgetEntryType.RESERVE, RequestType.TRAVEL),
        "travel_consumed": _sum_budget_entries(project, BudgetEntryType.CONSUME, RequestType.TRAVEL),
        "travel_released": _sum_budget_entries(project, BudgetEntryType.RELEASE, RequestType.TRAVEL),
        "travel_adjusted": _sum_budget_entries(project, BudgetEntryType.ADJUST, RequestType.TRAVEL),
        "can_manage_budget": user_can_manage_project_budget(request.user, project),
        "project_adjust_budget_url": reverse("projects:project_add_budget_adjustment", args=[project.id]),
        "ledger_legend": [
            ("RESERVE", "Reserve budget for submitted request"),
            ("CONSUME", "Convert budget into actual spending"),
            ("RELEASE", "Release reserved budget back to available"),
            ("ADJUST", "Manual project budget adjustment"),
        ],
    }
    return render(request, "projects/project_budget_ledger.html", context)


@login_required
def project_add_budget_adjustment(request, pk):
    project = get_object_or_404(
        get_visible_projects_queryset_for_user(request.user),
        pk=pk,
    )

    if not user_can_manage_project_budget(request.user, project):
        raise PermissionDenied("You do not have permission to adjust this project budget.")

    if request.method == "POST":
        form = ProjectBudgetAdjustmentForm(request.POST)
        if form.is_valid():
            ProjectBudgetEntry.objects.create(
                project=project,
                entry_type=BudgetEntryType.ADJUST,
                source_type=RequestType.PROJECT,
                source_id=project.id,
                amount=form.cleaned_data["amount"],
                notes=form.cleaned_data["notes"],
                created_by=request.user,
            )
            messages.success(request, f"Budget adjustment recorded for {project.project_code}.")
            return redirect("projects:project_budget_ledger", pk=project.id)
    else:
        form = ProjectBudgetAdjustmentForm()

    context = {
        "project": project,
        "form": form,
    }
    return render(request, "projects/project_budget_adjustment.html", context)