from datetime import timedelta
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from .forms import (
    AccountingPeriodCloseForm,
    AccountingPeriodForm,
    AccountingPeriodReopenForm,
    AccountingReviewDecisionForm,
    AccountingReviewFilterForm,
    CardTransactionAllocationForm,
    CardTransactionForm,
    CurrencyForm,
    DirectProjectCostPolicyForm,
    ExchangeRateForm,
    FXVariancePolicyForm,
    OverBudgetPolicyForm,
    ReceiptPolicyForm,
)
from common.currency import COMPANY_BASE_CURRENCY
from common.permissions import can_manage_finance_setup, can_perform_accounting_work
from .models import (
    AccountingPeriod,
    AccountingPeriodStatus,
    AccountingReviewItem,
    AccountingReviewStatus,
    CardTransaction,
    Currency,
    DirectProjectCostPolicy,
    ExchangeRate,
    FXVariancePolicy,
    OverBudgetPolicy,
    ReceiptPolicy,
)
from .reporting import build_finance_report_context
from .presentation import (
    apply_accounting_review_tab,
    build_accounting_review_tab_counts,
    build_accounting_review_tabs,
    build_card_review_action,
    build_card_transaction_summary,
    enrich_card_review_items,
    enrich_review_item,
    enrich_review_items,
    has_active_accounting_review_filters,
    has_active_advanced_accounting_review_filters,
)
from .services import (
    allocate_card_transaction,
    build_actual_expense_evidence_status,
    build_accounting_period_close_checklist,
    build_duplicate_actual_expense_candidates,
    create_duplicate_card_review_item,
    enforce_accounting_period_open,
    mark_card_transaction_reviewed,
)


def _enforce_finance_setup_permission(user):
    if not can_manage_finance_setup(user):
        raise PermissionDenied("You do not have permission to manage finance setup.")


def _enforce_accounting_permission(user):
    if not can_perform_accounting_work(user):
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
def direct_project_cost_policy_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = (
        DirectProjectCostPolicy.objects.select_related("department", "project")
        .order_by("priority", "policy_code")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(policy_code__icontains=q) | Q(policy_name__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/direct_project_cost_policy_list.html",
        {"page_obj": page_obj, "q": q},
    )


@login_required
def direct_project_cost_policy_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = DirectProjectCostPolicyForm(request.POST)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Direct project cost policy '{policy.policy_code}' created.")
            return redirect("finance:direct_project_cost_policy_edit", pk=policy.pk)
    else:
        form = DirectProjectCostPolicyForm()
    return render(request, "finance/direct_project_cost_policy_form.html", {"form": form, "page_mode": "create"})


@login_required
def direct_project_cost_policy_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    policy = get_object_or_404(DirectProjectCostPolicy, pk=pk)
    if request.method == "POST":
        form = DirectProjectCostPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Direct project cost policy '{policy.policy_code}' updated.")
            return redirect("finance:direct_project_cost_policy_edit", pk=policy.pk)
    else:
        form = DirectProjectCostPolicyForm(instance=policy)
    return render(
        request,
        "finance/direct_project_cost_policy_form.html",
        {"form": form, "policy": policy, "page_mode": "edit"},
    )


@login_required
def currency_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = Currency.objects.order_by("code")
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(code__icontains=q) | Q(name__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/currency_list.html",
        {
            "page_obj": page_obj,
            "q": q,
            "base_currency": COMPANY_BASE_CURRENCY,
        },
    )


@login_required
def currency_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = CurrencyForm(request.POST)
        if form.is_valid():
            currency = form.save()
            messages.success(request, f"Currency {currency.code} created.")
            return redirect("finance:currency_edit", pk=currency.pk)
    else:
        form = CurrencyForm()
    return render(request, "finance/currency_form.html", {"form": form, "page_mode": "create"})


@login_required
def currency_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    currency = get_object_or_404(Currency, pk=pk)
    if request.method == "POST":
        form = CurrencyForm(request.POST, instance=currency)
        if form.is_valid():
            currency = form.save()
            messages.success(request, f"Currency {currency.code} updated.")
            return redirect("finance:currency_edit", pk=currency.pk)
    else:
        form = CurrencyForm(instance=currency)
    return render(request, "finance/currency_form.html", {"form": form, "currency": currency, "page_mode": "edit"})


@login_required
def exchange_rate_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = ExchangeRate.objects.order_by("-effective_date", "from_currency", "to_currency")
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(from_currency__icontains=q) | Q(to_currency__icontains=q) | Q(source__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/exchange_rate_list.html",
        {"page_obj": page_obj, "q": q, "base_currency": COMPANY_BASE_CURRENCY},
    )


@login_required
def exchange_rate_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = ExchangeRateForm(request.POST)
        if form.is_valid():
            rate = form.save(commit=False)
            rate.created_by = request.user
            rate.save()
            messages.success(request, "Exchange rate created.")
            return redirect("finance:exchange_rate_edit", pk=rate.pk)
    else:
        form = ExchangeRateForm(initial={"to_currency": COMPANY_BASE_CURRENCY})
    return render(request, "finance/exchange_rate_form.html", {"form": form, "page_mode": "create"})


@login_required
def exchange_rate_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    rate = get_object_or_404(ExchangeRate, pk=pk)
    if request.method == "POST":
        form = ExchangeRateForm(request.POST, instance=rate)
        if form.is_valid():
            form.save()
            messages.success(request, "Exchange rate updated.")
            return redirect("finance:exchange_rate_edit", pk=rate.pk)
    else:
        form = ExchangeRateForm(instance=rate)
    return render(request, "finance/exchange_rate_form.html", {"form": form, "rate": rate, "page_mode": "edit"})


@login_required
def fx_variance_policy_list(request):
    _enforce_finance_setup_permission(request.user)
    queryset = FXVariancePolicy.objects.order_by("priority", "policy_code")
    q = (request.GET.get("q") or "").strip()
    if q:
        queryset = queryset.filter(Q(policy_code__icontains=q) | Q(policy_name__icontains=q))
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/fx_variance_policy_list.html",
        {"page_obj": page_obj, "q": q, "base_currency": COMPANY_BASE_CURRENCY},
    )


@login_required
def fx_variance_policy_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = FXVariancePolicyForm(request.POST)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"FX variance policy '{policy.policy_code}' created.")
            return redirect("finance:fx_variance_policy_edit", pk=policy.pk)
    else:
        form = FXVariancePolicyForm()
    return render(request, "finance/fx_variance_policy_form.html", {"form": form, "page_mode": "create"})


@login_required
def fx_variance_policy_edit(request, pk):
    _enforce_finance_setup_permission(request.user)
    policy = get_object_or_404(FXVariancePolicy, pk=pk)
    if request.method == "POST":
        form = FXVariancePolicyForm(request.POST, instance=policy)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"FX variance policy '{policy.policy_code}' updated.")
            return redirect("finance:fx_variance_policy_edit", pk=policy.pk)
    else:
        form = FXVariancePolicyForm(instance=policy)
    return render(
        request,
        "finance/fx_variance_policy_form.html",
        {"form": form, "policy": policy, "page_mode": "edit"},
    )


@login_required
def accounting_period_list(request):
    _enforce_accounting_permission(request.user)
    queryset = AccountingPeriod.objects.order_by("-start_date", "-id")
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    current_open_period = queryset.filter(status=AccountingPeriodStatus.OPEN).first()
    return render(
        request,
        "finance/accounting_period_list.html",
        {
            "page_obj": page_obj,
            "current_open_period": current_open_period,
            "can_manage_periods": can_manage_finance_setup(request.user),
        },
    )


@login_required
def accounting_period_create(request):
    _enforce_finance_setup_permission(request.user)
    if request.method == "POST":
        form = AccountingPeriodForm(request.POST)
        if form.is_valid():
            period = form.save()
            messages.success(request, f"Accounting period {period.period_code} created.")
            return redirect("finance:accounting_period_detail", pk=period.pk)
    else:
        form = AccountingPeriodForm()
    return render(request, "finance/accounting_period_form.html", {"form": form, "page_mode": "create"})


@login_required
def accounting_period_detail(request, pk):
    _enforce_accounting_permission(request.user)
    period = get_object_or_404(AccountingPeriod, pk=pk)
    checklist = build_accounting_period_close_checklist(period)
    return render(
        request,
        "finance/accounting_period_detail.html",
        {
            "period": period,
            "close_checklist": checklist,
            "close_form": AccountingPeriodCloseForm(),
            "reopen_form": AccountingPeriodReopenForm(),
            "can_manage_periods": can_manage_finance_setup(request.user),
        },
    )


@login_required
@require_POST
def accounting_period_close(request, pk):
    _enforce_finance_setup_permission(request.user)
    period = get_object_or_404(AccountingPeriod, pk=pk)
    form = AccountingPeriodCloseForm(request.POST)
    if form.is_valid():
        period.status = AccountingPeriodStatus.CLOSED
        period.closed_by = request.user
        period.closed_at = timezone.now()
        period.notes = form.cleaned_data["notes"]
        period.save(update_fields=["status", "closed_by", "closed_at", "notes"])
        messages.success(request, f"Accounting period {period.period_code} closed.")
    else:
        messages.error(request, "Close notes are required.")
    return redirect("finance:accounting_period_detail", pk=period.pk)


@login_required
@require_POST
def accounting_period_reopen(request, pk):
    _enforce_finance_setup_permission(request.user)
    period = get_object_or_404(AccountingPeriod, pk=pk)
    form = AccountingPeriodReopenForm(request.POST)
    if form.is_valid():
        reason = form.cleaned_data["reason"]
        period.status = AccountingPeriodStatus.OPEN
        period.notes = f"{period.notes}\n\nReopened by {request.user} at {timezone.now()}: {reason}".strip()
        period.save(update_fields=["status", "notes"])
        messages.success(request, f"Accounting period {period.period_code} reopened.")
    else:
        messages.error(request, "Reopen reason is required.")
    return redirect("finance:accounting_period_detail", pk=period.pk)


@login_required
def accounting_review_queue(request):
    _enforce_accounting_permission(request.user)
    base_queryset = (
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
    tab_counts = build_accounting_review_tab_counts(base_queryset)
    queryset = apply_accounting_review_tab(base_queryset, active_tab)
    form = AccountingReviewFilterForm(request.GET or None)
    has_active_filters = False
    advanced_filters_open = False
    if form.is_valid():
        has_active_filters = has_active_accounting_review_filters(form.cleaned_data)
        advanced_filters_open = has_active_advanced_accounting_review_filters(form.cleaned_data)
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
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)
    page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
    enrich_review_items(page_obj.object_list)
    pending_count = queryset.filter(status=AccountingReviewStatus.PENDING_REVIEW).count()
    base_url = reverse("finance:accounting_review_queue")
    reset_url = f"{base_url}?tab={active_tab}"
    return render(
        request,
        "finance/accounting_review_queue.html",
        {
            "filter_form": form,
            "page_obj": page_obj,
            "pending_count": pending_count,
            "review_tabs": build_accounting_review_tabs(active_tab, base_url, counts=tab_counts),
            "active_tab": active_tab,
            "has_active_filters": has_active_filters,
            "advanced_filters_open": advanced_filters_open,
            "reset_url": reset_url,
            "pagination_querystring": pagination_query.urlencode(),
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
    actual_expense = item.purchase_actual_spend or item.travel_actual_expense
    evidence_status = build_actual_expense_evidence_status(actual_expense) if actual_expense else None
    duplicate_candidates = (
        build_duplicate_actual_expense_candidates(actual_expense)
        if item.reason == "DUPLICATE_EXPENSE" and actual_expense
        else []
    )
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
            "actual_expense": actual_expense,
            "evidence_status": evidence_status,
            "duplicate_candidates": duplicate_candidates,
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
            try:
                enforce_accounting_period_open(
                    form.cleaned_data["transaction_date"],
                    action_label="create card transaction",
                    user=request.user,
                )
                transaction = form.save(commit=False)
                transaction.imported_by = request.user
                transaction.save()
                if transaction.has_possible_duplicate():
                    create_duplicate_card_review_item(transaction, created_by=request.user)
                    messages.warning(request, "Possible duplicate card transaction detected.")
                messages.success(request, "Card transaction created.")
                return redirect("finance:card_transaction_detail", pk=transaction.pk)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
    else:
        form = CardTransactionForm()
    return render(request, "finance/card_transaction_form.html", {"form": form})


@login_required
def card_transaction_detail(request, pk):
    _enforce_accounting_permission(request.user)
    transaction = get_object_or_404(CardTransaction.objects.select_related("cardholder"), pk=pk)
    unallocated_amount = transaction.get_unallocated_amount()
    allocation_form = CardTransactionAllocationForm(initial={"amount": unallocated_amount})
    allocation_form.fields["amount"].widget.attrs.update({
        "max": unallocated_amount,
        "data-unallocated-amount": unallocated_amount,
    })
    allocations = transaction.allocations.select_related("purchase_request", "travel_request", "project", "created_by", "policy")
    review_items = list(
        transaction.review_items.select_related(
            "purchase_request",
            "travel_request",
            "card_transaction",
            "card_allocation",
            "card_allocation__card_transaction",
            "policy",
        )
    )
    enrich_card_review_items(review_items)
    card_summary = build_card_transaction_summary(transaction)
    review_action = build_card_review_action(transaction)
    return render(
        request,
        "finance/card_transaction_detail.html",
        {
            "transaction": transaction,
            "allocation_form": allocation_form,
            "allocations": allocations,
            "review_items": review_items,
            "possible_duplicate": transaction.has_possible_duplicate(),
            "card_summary": card_summary,
            "review_action": review_action,
            "can_allocate": unallocated_amount > 0,
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
    context = build_finance_report_context()
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="finance_reports.csv"'
        writer = csv.writer(response)
        writer.writerow(["Report", "Key", "Description", "Base Currency", "Amount", "Transaction Currency", "Transaction Amount"])
        for row in context["project_budget_rows"]:
            writer.writerow(["Project Budget", row["project"].project_code, "Budget", row["currency"], row["budget"], "", ""])
            writer.writerow(["Project Budget", row["project"].project_code, "Reserved", row["currency"], row["reserved"], "", ""])
            writer.writerow(["Project Budget", row["project"].project_code, "Consumed", row["currency"], row["consumed"], "", ""])
            writer.writerow(["Project Budget", row["project"].project_code, "Available", row["currency"], row["available"], "", ""])
        for row in context["department_spending_rows"]:
            writer.writerow(["Department Spending", row["department"].dept_code, "Consumed", row["currency"], row["consumed"], "", ""])
        for row in context["open_reserve_rows"]:
            writer.writerow(["Open Reserve", row["type"], getattr(row["request"], "pr_no", "") or getattr(row["request"], "travel_no", ""), row["currency"], row["remaining"], "", ""])
        for item in context["over_budget_items"]:
            writer.writerow([
                "Over-Budget Exception",
                item.title,
                item.get_status_display(),
                item.report_currency,
                item.report_amount,
                item.transaction_currency,
                item.transaction_amount,
            ])
        for transaction in context["unmatched_card_transactions"]:
            writer.writerow([
                "Unmatched Card",
                transaction.reference_no,
                transaction.merchant_name,
                transaction.base_currency,
                transaction.base_amount,
                transaction.transaction_currency,
                transaction.transaction_amount,
            ])
        return response
    return render(request, "finance/reports.html", context)
