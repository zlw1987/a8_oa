from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AccountingReviewDecisionForm,
    AccountingReviewFilterForm,
    CardTransactionAllocationForm,
    CardTransactionForm,
    OverBudgetPolicyForm,
    ReceiptPolicyForm,
)
from .models import (
    AccountingReviewItem,
    AccountingReviewStatus,
    CardTransaction,
    OverBudgetPolicy,
    ReceiptPolicy,
)
from .reporting import build_finance_report_context
from .presentation import (
    apply_accounting_review_tab,
    build_accounting_review_tabs,
    enrich_review_item,
    enrich_review_items,
)
from .services import (
    allocate_card_transaction,
    create_duplicate_card_review_item,
    mark_card_transaction_reviewed,
)


def _enforce_finance_setup_permission(user):
    if not user.is_authenticated or not user.is_staff:
        raise PermissionDenied("You do not have permission to manage finance setup.")


def _enforce_accounting_permission(user):
    if not user.is_authenticated or not user.is_staff:
        raise PermissionDenied("You do not have permission to perform accounting actions.")


@login_required
def over_budget_policy_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = OverBudgetPolicy.objects.select_related("department").order_by("priority", "policy_code")
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(policy_code__icontains=q) | Q(policy_name__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/over_budget_policy_list.html",
        {"page_obj": page_obj, "q": q},
    )


@login_required
def over_budget_policy_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = OverBudgetPolicyForm(request.POST)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Over-budget policy '{policy.policy_code}' created.")
            return redirect("finance:over_budget_policy_edit", pk=policy.pk)
    else:
        form = OverBudgetPolicyForm()
    return render(request, "finance/over_budget_policy_form.html", {"form": form, "page_mode": "create"})


@login_required
def over_budget_policy_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    policy = get_object_or_404(OverBudgetPolicy, pk=pk)
    if request.method == "POST":
        form = OverBudgetPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Over-budget policy '{policy.policy_code}' updated.")
            return redirect("finance:over_budget_policy_edit", pk=policy.pk)
    else:
        form = OverBudgetPolicyForm(instance=policy)
    return render(
        request,
        "finance/over_budget_policy_form.html",
        {"form": form, "policy": policy, "page_mode": "edit"},
    )


@login_required
def receipt_policy_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = ReceiptPolicy.objects.select_related("department").order_by("priority", "policy_code")
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(policy_code__icontains=q) | Q(policy_name__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/receipt_policy_list.html",
        {"page_obj": page_obj, "q": q},
    )


@login_required
def receipt_policy_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = ReceiptPolicyForm(request.POST)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Receipt policy '{policy.policy_code}' created.")
            return redirect("finance:receipt_policy_edit", pk=policy.pk)
    else:
        form = ReceiptPolicyForm()
    return render(request, "finance/receipt_policy_form.html", {"form": form, "page_mode": "create"})


@login_required
def receipt_policy_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    policy = get_object_or_404(ReceiptPolicy, pk=pk)
    if request.method == "POST":
        form = ReceiptPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Receipt policy '{policy.policy_code}' updated.")
            return redirect("finance:receipt_policy_edit", pk=policy.pk)
    else:
        form = ReceiptPolicyForm(instance=policy)
    return render(
        request,
        "finance/receipt_policy_form.html",
        {"form": form, "policy": policy, "page_mode": "edit"},
    )


@login_required
def accounting_review_queue(request):
    _enforce_accounting_permission(request.user)
    queryset = (
        AccountingReviewItem.objects.select_related(
            "purchase_request",
            "travel_request",
            "purchase_request__requester",
            "travel_request__requester",
            "policy",
            "assigned_reviewer",
            "reviewed_by",
            "purchase_request__request_department",
            "travel_request__request_department",
            "purchase_request__project",
            "travel_request__project",
            "card_transaction",
            "card_allocation",
            "card_allocation__card_transaction",
        )
        .order_by("status", "-created_at", "-id")
    )
    active_tab = request.GET.get("tab") or "pending"
    queryset = apply_accounting_review_tab(queryset, active_tab)
    form = AccountingReviewFilterForm(request.GET or None)
    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        status = form.cleaned_data.get("status")
        reason = form.cleaned_data.get("reason")
        source_type = form.cleaned_data.get("source_type")
        policy_action = form.cleaned_data.get("policy_action")
        requester = (form.cleaned_data.get("requester") or "").strip()
        department = (form.cleaned_data.get("department") or "").strip()
        project = (form.cleaned_data.get("project") or "").strip()
        min_age_days = form.cleaned_data.get("min_age_days")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if status:
            queryset = queryset.filter(status=status)
        if reason:
            queryset = queryset.filter(reason=reason)
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        if policy_action:
            queryset = queryset.filter(policy_action=policy_action)
        if requester:
            queryset = queryset.filter(
                Q(purchase_request__requester__username__icontains=requester)
                | Q(travel_request__requester__username__icontains=requester)
            )
        if department:
            queryset = queryset.filter(
                Q(purchase_request__request_department__dept_name__icontains=department)
                | Q(purchase_request__request_department__dept_code__icontains=department)
                | Q(travel_request__request_department__dept_name__icontains=department)
                | Q(travel_request__request_department__dept_code__icontains=department)
            )
        if project:
            queryset = queryset.filter(
                Q(purchase_request__project__project_code__icontains=project)
                | Q(purchase_request__project__project_name__icontains=project)
                | Q(travel_request__project__project_code__icontains=project)
                | Q(travel_request__project__project_name__icontains=project)
            )
        if min_age_days is not None:
            queryset = queryset.filter(created_at__lte=timezone.now() - timedelta(days=min_age_days))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    enrich_review_items(page_obj.object_list)
    pending_count = queryset.filter(status=AccountingReviewStatus.PENDING_REVIEW).count()
    return render(
        request,
        "finance/accounting_review_queue.html",
        {
            "filter_form": form,
            "page_obj": page_obj,
            "pending_count": pending_count,
            "review_tabs": build_accounting_review_tabs(active_tab, reverse("finance:accounting_review_queue")),
            "active_tab": active_tab,
        },
    )


@login_required
def accounting_review_detail(request, pk):
    _enforce_accounting_permission(request.user)
    item = get_object_or_404(
        AccountingReviewItem.objects.select_related(
            "purchase_request",
            "travel_request",
            "purchase_request__requester",
            "travel_request__requester",
            "purchase_request__request_department",
            "travel_request__request_department",
            "purchase_request__project",
            "travel_request__project",
            "purchase_actual_spend",
            "travel_actual_expense",
            "card_transaction",
            "card_allocation",
            "card_allocation__card_transaction",
            "policy",
            "assigned_reviewer",
            "reviewed_by",
            "created_by",
        ),
        pk=pk,
    )
    enrich_review_item(item)
    initial_decision = request.GET.get("decision") or ""
    form = AccountingReviewDecisionForm(initial={"decision": initial_decision})
    requester_id = None
    if item.purchase_request_id:
        requester_id = item.purchase_request.requester_id
    elif item.travel_request_id:
        requester_id = item.travel_request.requester_id
    can_decide = item.is_unresolved and requester_id != request.user.id
    return render(
        request,
        "finance/accounting_review_detail.html",
        {
            "item": item,
            "form": form,
            "can_decide": can_decide,
        },
    )


@login_required
@require_POST
def accounting_review_decide(request, pk):
    _enforce_accounting_permission(request.user)
    item = get_object_or_404(AccountingReviewItem, pk=pk)
    requester_id = None
    if item.purchase_request_id:
        requester_id = item.purchase_request.requester_id
    elif item.travel_request_id:
        requester_id = item.travel_request.requester_id
    if requester_id and requester_id == request.user.id:
        raise PermissionDenied("Requester cannot review their own actual expense.")

    form = AccountingReviewDecisionForm(request.POST)
    if form.is_valid():
        item.decision = form.cleaned_data["decision"]
        if item.decision == "APPROVE_EXCEPTION":
            item.status = "APPROVED_EXCEPTION"
        elif item.decision == "RETURN":
            item.status = "RETURNED"
        elif item.decision == "REJECT":
            item.status = "REJECTED"
        else:
            item.status = "RESOLVED"
        item.comment = form.cleaned_data.get("comment") or ""
        item.reviewed_by = request.user
        from django.utils import timezone

        item.reviewed_at = timezone.now()
        item.save(update_fields=["decision", "status", "comment", "reviewed_by", "reviewed_at", "updated_at"])
        messages.success(request, "Accounting review item updated.")
    else:
        messages.error(request, "Invalid review decision.")
    next_url = request.POST.get("next") or reverse("finance:accounting_review_queue")
    return redirect(next_url)


@login_required
def card_transaction_list(request):
    _enforce_accounting_permission(request.user)
    queryset = CardTransaction.objects.select_related("cardholder").order_by("-statement_date", "-transaction_date", "-id")
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if q:
        queryset = queryset.filter(Q(merchant_name__icontains=q) | Q(reference_no__icontains=q) | Q(cardholder__username__icontains=q))
    if status:
        queryset = queryset.filter(match_status=status)
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/card_transaction_list.html",
        {"page_obj": page_obj, "q": q, "status": status},
    )


@login_required
def card_transaction_create(request):
    _enforce_accounting_permission(request.user)
    if request.method == "POST":
        form = CardTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.imported_by = request.user
            transaction.save()
            if transaction.has_possible_duplicate():
                create_duplicate_card_review_item(transaction, created_by=request.user)
                messages.warning(request, "Possible duplicate card transaction detected.")
            messages.success(request, "Card transaction created.")
            return redirect("finance:card_transaction_detail", pk=transaction.pk)
    else:
        form = CardTransactionForm()
    return render(request, "finance/card_transaction_form.html", {"form": form})


@login_required
def card_transaction_detail(request, pk):
    _enforce_accounting_permission(request.user)
    transaction = get_object_or_404(CardTransaction.objects.select_related("cardholder"), pk=pk)
    allocation_form = CardTransactionAllocationForm(initial={"amount": transaction.get_unallocated_amount()})
    allocations = transaction.allocations.select_related("purchase_request", "travel_request", "project", "created_by")
    return render(
        request,
        "finance/card_transaction_detail.html",
        {
            "transaction": transaction,
            "allocation_form": allocation_form,
            "allocations": allocations,
            "possible_duplicate": transaction.has_possible_duplicate(),
        },
    )


@login_required
@require_POST
def card_transaction_allocate(request, pk):
    _enforce_accounting_permission(request.user)
    transaction = get_object_or_404(CardTransaction, pk=pk)
    form = CardTransactionAllocationForm(request.POST)
    if form.is_valid():
        try:
            allocate_card_transaction(
                card_transaction=transaction,
                amount=form.cleaned_data["amount"],
                purchase_request=form.cleaned_data.get("purchase_request"),
                travel_request=form.cleaned_data.get("travel_request"),
                project=form.cleaned_data.get("project"),
                acting_user=request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
            messages.success(request, "Card transaction allocation saved.")
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
    else:
        for field_name, errors in form.errors.items():
            label = form.fields[field_name].label or field_name
            for error in errors:
                messages.error(request, f"{label}: {error}")
    return redirect("finance:card_transaction_detail", pk=transaction.pk)


@login_required
@require_POST
def card_transaction_mark_reviewed(request, pk):
    _enforce_accounting_permission(request.user)
    transaction = get_object_or_404(CardTransaction, pk=pk)
    try:
        mark_card_transaction_reviewed(transaction, acting_user=request.user)
        messages.success(request, "Card transaction marked reviewed.")
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
    return redirect("finance:card_transaction_detail", pk=transaction.pk)


@login_required
def finance_reports(request):
    _enforce_accounting_permission(request.user)
    return render(request, "finance/reports.html", build_finance_report_context())
