from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from common.choices import BudgetEntryType, RequestType
from common.currency import COMPANY_BASE_CURRENCY, quantize_money, quantize_rate
from projects.models import ProjectBudgetEntry

from .models import (
    AccountingReviewDecision,
    AccountingReviewItem,
    AccountingReviewReason,
    AccountingReviewStatus,
    CardTransactionAllocation,
    CardTransactionMatchStatus,
    ExchangeRate,
    ExchangeRateSource,
    FXVarianceAction,
    FXVariancePolicy,
    OverBudgetAction,
    OverBudgetPolicy,
    PaymentMethod,
    ReceiptPolicy,
    VarianceType,
)


OPEN_REVIEW_STATUSES = [
    AccountingReviewStatus.PENDING_REVIEW,
    AccountingReviewStatus.RETURNED,
]


@dataclass
class ActualExpensePolicyResult:
    request_obj: object
    request_type: str
    approved_amount: Decimal
    existing_actual_total: Decimal
    current_actual_amount: Decimal
    new_actual_total: Decimal
    over_amount: Decimal
    over_percent: Decimal
    action: str
    policy: OverBudgetPolicy | None
    payment_method: str
    currency: str
    message: str
    transaction_currency: str = ""
    transaction_amount: Decimal = Decimal("0.00")
    base_currency: str = COMPANY_BASE_CURRENCY
    base_amount: Decimal = Decimal("0.00")
    exchange_rate: Decimal | None = None
    exchange_rate_date: object = None
    exchange_rate_source: str = ""
    variance_type: str = VarianceType.NONE
    fx_policy: FXVariancePolicy | None = None

    @property
    def is_over_budget(self):
        return self.over_amount > Decimal("0.00")

    @property
    def allows_recording(self):
        return self.action in [
            OverBudgetAction.ALLOW,
            OverBudgetAction.WARNING,
            OverBudgetAction.REVIEW,
            OverBudgetAction.AMENDMENT_REQUIRED,
        ]


@dataclass
class ReceiptPolicyResult:
    request_obj: object
    request_type: str
    amount: Decimal
    payment_method: str
    expense_type: str
    currency: str
    policy: ReceiptPolicy | None
    requires_receipt: bool
    requires_invoice: bool
    allows_exception: bool
    message: str

    @property
    def requires_review(self):
        return self.requires_receipt or self.requires_invoice


def _money(value):
    return quantize_money(value)


def _percent(value):
    return (value or Decimal("0.0000")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def get_request_type(request_obj):
    if hasattr(request_obj, "pr_no"):
        return RequestType.PURCHASE
    if hasattr(request_obj, "travel_no"):
        return RequestType.TRAVEL
    raise ValidationError("Unsupported request type for finance policy evaluation.")


def get_request_no(request_obj):
    return getattr(request_obj, "pr_no", "") or getattr(request_obj, "travel_no", "") or str(request_obj.pk)


def get_request_title(request_obj):
    return getattr(request_obj, "title", "") or getattr(request_obj, "purpose", "") or ""


def get_request_detail_url_name(request_obj):
    if hasattr(request_obj, "pr_no"):
        return "purchase:pr_detail"
    if hasattr(request_obj, "travel_no"):
        return "travel:tr_detail"
    return ""


def get_request_department(request_obj):
    return getattr(request_obj, "request_department", None)


def get_request_project_type(request_obj):
    project = getattr(request_obj, "project", None)
    return getattr(project, "project_type", "") if project else ""


def get_approved_amount(request_obj):
    return _money(getattr(request_obj, "estimated_total", Decimal("0.00")))


def get_existing_actual_total(request_obj):
    if hasattr(request_obj, "get_actual_spent_total"):
        return _money(request_obj.get_actual_spent_total())
    if hasattr(request_obj, "get_actual_total"):
        return _money(request_obj.get_actual_total())
    return _money(getattr(request_obj, "actual_total", Decimal("0.00")))


def resolve_exchange_rate(from_currency, to_currency=COMPANY_BASE_CURRENCY, rate_date=None, source=""):
    if from_currency == to_currency:
        return Decimal("1.00000000"), ExchangeRateSource.COMPANY_RATE
    if not rate_date:
        rate_date = timezone.localdate()
    queryset = ExchangeRate.objects.filter(
        from_currency=from_currency,
        to_currency=to_currency,
        effective_date__lte=rate_date,
    )
    if source:
        queryset = queryset.filter(source=source)
    rate = queryset.order_by("-effective_date", "-id").first()
    if not rate:
        raise ValidationError(f"No exchange rate found for {from_currency} to {to_currency} on or before {rate_date}.")
    return quantize_rate(rate.rate), rate.source


def build_money_snapshot(
    *,
    transaction_amount,
    transaction_currency,
    base_amount=None,
    base_currency=COMPANY_BASE_CURRENCY,
    exchange_rate=None,
    exchange_rate_date=None,
    exchange_rate_source="",
    override_reason="",
):
    transaction_amount = _money(transaction_amount)
    transaction_currency = transaction_currency or base_currency
    base_currency = base_currency or COMPANY_BASE_CURRENCY
    exchange_rate_date = exchange_rate_date or timezone.localdate()

    if base_amount is not None:
        base_amount = _money(base_amount)
        effective_rate = quantize_rate(exchange_rate or (base_amount / transaction_amount if transaction_amount else Decimal("0")))
        effective_source = (
            exchange_rate_source
            or (ExchangeRateSource.ACCOUNTING_OVERRIDE if override_reason else ExchangeRateSource.MANUAL)
        )
    elif transaction_currency == base_currency:
        base_amount = transaction_amount
        effective_rate = Decimal("1.00000000")
        effective_source = exchange_rate_source or ExchangeRateSource.COMPANY_RATE
    else:
        effective_rate, effective_source = resolve_exchange_rate(
            transaction_currency,
            base_currency,
            rate_date=exchange_rate_date,
            source=exchange_rate_source if exchange_rate_source and exchange_rate_source != ExchangeRateSource.ACCOUNTING_OVERRIDE else "",
        )
        base_amount = _money(transaction_amount * effective_rate)

    return {
        "transaction_currency": transaction_currency,
        "transaction_amount": transaction_amount,
        "base_currency": base_currency,
        "base_amount": base_amount,
        "exchange_rate": effective_rate,
        "exchange_rate_date": exchange_rate_date,
        "exchange_rate_source": effective_source,
        "exchange_rate_override_reason": override_reason or "",
    }


def classify_currency_variance(
    *,
    approved_transaction_amount,
    approved_transaction_currency,
    approved_base_amount,
    actual_transaction_amount,
    actual_transaction_currency,
    actual_base_amount,
):
    approved_base_amount = _money(approved_base_amount)
    actual_base_amount = _money(actual_base_amount)
    if actual_base_amount <= approved_base_amount:
        return VarianceType.NONE
    if not approved_transaction_currency or approved_transaction_currency != actual_transaction_currency:
        return VarianceType.BASE_CURRENCY_VARIANCE
    if _money(actual_transaction_amount) <= _money(approved_transaction_amount):
        return VarianceType.FX_VARIANCE
    return VarianceType.SPENDING_OVERRUN


def resolve_fx_variance_policy(*, variance_amount, variance_percent, currency=COMPANY_BASE_CURRENCY):
    queryset = FXVariancePolicy.objects.filter(is_active=True).order_by("priority", "policy_code", "id")
    queryset = queryset.filter(currency__in=["", currency or COMPANY_BASE_CURRENCY])
    for policy in queryset:
        if policy.fx_variance_amount_from is not None and variance_amount < policy.fx_variance_amount_from:
            continue
        if policy.fx_variance_amount_to is not None and variance_amount > policy.fx_variance_amount_to:
            continue
        if policy.fx_variance_percent_from is not None and variance_percent < policy.fx_variance_percent_from:
            continue
        if policy.fx_variance_percent_to is not None and variance_percent > policy.fx_variance_percent_to:
            continue
        return policy
    return None


def _map_fx_action_to_over_budget_action(fx_action):
    return {
        FXVarianceAction.ALLOW: OverBudgetAction.ALLOW,
        FXVarianceAction.WARNING: OverBudgetAction.WARNING,
        FXVarianceAction.REVIEW: OverBudgetAction.REVIEW,
        FXVarianceAction.FINANCE_REVIEW_REQUIRED: OverBudgetAction.REVIEW,
        FXVarianceAction.BLOCK: OverBudgetAction.BLOCK,
    }.get(fx_action, OverBudgetAction.REVIEW)


def _matches_threshold(policy, over_amount, over_percent):
    if policy.over_amount_from is not None and over_amount < policy.over_amount_from:
        return False
    if policy.over_amount_to is not None and over_amount > policy.over_amount_to:
        return False
    if policy.over_percent_from is not None and over_percent < policy.over_percent_from:
        return False
    if policy.over_percent_to is not None and over_percent > policy.over_percent_to:
        return False
    return True


def _matches_amount_threshold(policy, amount):
    if policy.amount_from is not None and amount < policy.amount_from:
        return False
    if policy.amount_to is not None and amount > policy.amount_to:
        return False
    return True


def resolve_over_budget_policy(
    *,
    request_obj,
    over_amount,
    over_percent,
    payment_method=PaymentMethod.REIMBURSEMENT,
    currency="",
):
    request_type = get_request_type(request_obj)
    department = get_request_department(request_obj)
    project_type = get_request_project_type(request_obj)

    queryset = OverBudgetPolicy.objects.filter(is_active=True).order_by("priority", "policy_code", "id")
    queryset = queryset.filter(request_type__in=["ALL", request_type])
    queryset = queryset.filter(payment_method__in=[PaymentMethod.ALL, payment_method])
    queryset = queryset.filter(department__isnull=True) | queryset.filter(department=department)
    queryset = queryset.filter(project_type__in=["", project_type])
    if currency:
        queryset = queryset.filter(currency__in=["", currency])
    else:
        queryset = queryset.filter(currency="")

    for policy in queryset:
        if _matches_threshold(policy, over_amount, over_percent):
            return policy
    return None


def resolve_receipt_policy(
    *,
    request_obj,
    amount,
    payment_method=PaymentMethod.REIMBURSEMENT,
    expense_type="",
    currency="",
):
    request_type = get_request_type(request_obj)
    department = get_request_department(request_obj)
    project_type = get_request_project_type(request_obj)
    effective_currency = currency or getattr(request_obj, "currency", "")
    queryset = ReceiptPolicy.objects.filter(is_active=True).order_by("priority", "policy_code", "id")
    queryset = queryset.filter(request_type__in=["ALL", request_type])
    queryset = queryset.filter(payment_method__in=[PaymentMethod.ALL, payment_method])
    queryset = queryset.filter(department__isnull=True) | queryset.filter(department=department)
    queryset = queryset.filter(project_type__in=["", project_type])
    queryset = queryset.filter(expense_type__in=["", expense_type or ""])
    if effective_currency:
        queryset = queryset.filter(currency__in=["", effective_currency])
    else:
        queryset = queryset.filter(currency="")

    amount = _money(amount)
    for policy in queryset:
        if _matches_amount_threshold(policy, amount):
            return policy
    return None


def evaluate_receipt_policy(
    request_obj,
    *,
    amount,
    payment_method=PaymentMethod.REIMBURSEMENT,
    expense_type="",
    currency="",
):
    amount = _money(amount)
    request_type = get_request_type(request_obj)
    effective_currency = currency or getattr(request_obj, "currency", "")
    policy = resolve_receipt_policy(
        request_obj=request_obj,
        amount=amount,
        payment_method=payment_method,
        expense_type=expense_type,
        currency=effective_currency,
    )
    requires_receipt = bool(policy.requires_receipt) if policy else False
    requires_invoice = bool(policy.requires_invoice) if policy else False
    allows_exception = bool(policy.allows_exception) if policy else True
    requirements = []
    if requires_receipt:
        requirements.append("receipt")
    if requires_invoice:
        requirements.append("invoice")
    message = "Required attachment is present."
    if requirements:
        message = f"Missing required {' and '.join(requirements)} for actual expense."
    return ReceiptPolicyResult(
        request_obj=request_obj,
        request_type=request_type,
        amount=amount,
        payment_method=payment_method,
        expense_type=expense_type or "",
        currency=effective_currency,
        policy=policy,
        requires_receipt=requires_receipt,
        requires_invoice=requires_invoice,
        allows_exception=allows_exception,
        message=message,
    )


def evaluate_actual_expense_policy(
    request_obj,
    *,
    current_actual_amount,
    current_transaction_amount=None,
    transaction_currency="",
    base_amount=None,
    base_currency=COMPANY_BASE_CURRENCY,
    exchange_rate=None,
    exchange_rate_date=None,
    exchange_rate_source="",
    exchange_rate_override_reason="",
    payment_method=PaymentMethod.REIMBURSEMENT,
    currency="",
):
    effective_currency = currency or getattr(request_obj, "currency", "") or base_currency
    snapshot = build_money_snapshot(
        transaction_amount=current_transaction_amount if current_transaction_amount is not None else current_actual_amount,
        transaction_currency=transaction_currency or effective_currency,
        base_amount=base_amount,
        base_currency=base_currency,
        exchange_rate=exchange_rate,
        exchange_rate_date=exchange_rate_date,
        exchange_rate_source=exchange_rate_source,
        override_reason=exchange_rate_override_reason,
    )
    current_actual_amount = snapshot["base_amount"]
    if current_actual_amount <= 0:
        raise ValidationError("Actual expense amount must be greater than 0.")

    request_type = get_request_type(request_obj)
    approved_amount = get_approved_amount(request_obj)
    existing_actual_total = get_existing_actual_total(request_obj)
    new_actual_total = _money(existing_actual_total + current_actual_amount)
    over_amount = _money(max(new_actual_total - approved_amount, Decimal("0.00")))
    if approved_amount > 0:
        over_percent = _percent(over_amount / approved_amount)
    else:
        over_percent = Decimal("1.0000") if over_amount > 0 else Decimal("0.0000")

    approved_transaction_amount = _money(getattr(request_obj, "transaction_amount", None) or approved_amount)
    approved_transaction_currency = getattr(request_obj, "transaction_currency", "") or effective_currency
    variance_type = classify_currency_variance(
        approved_transaction_amount=approved_transaction_amount,
        approved_transaction_currency=approved_transaction_currency,
        approved_base_amount=approved_amount,
        actual_transaction_amount=snapshot["transaction_amount"],
        actual_transaction_currency=snapshot["transaction_currency"],
        actual_base_amount=new_actual_total,
    )
    policy = None
    fx_policy = None
    action = OverBudgetAction.ALLOW

    if over_amount > 0:
        if variance_type == VarianceType.FX_VARIANCE:
            fx_policy = resolve_fx_variance_policy(
                variance_amount=over_amount,
                variance_percent=over_percent,
                currency=snapshot["base_currency"],
            )
            action = _map_fx_action_to_over_budget_action(fx_policy.action if fx_policy else FXVarianceAction.REVIEW)
        else:
            policy = resolve_over_budget_policy(
                request_obj=request_obj,
                over_amount=over_amount,
                over_percent=over_percent,
                payment_method=payment_method,
                currency=snapshot["base_currency"],
            )
            action = policy.action if policy else OverBudgetAction.REVIEW

    if action == OverBudgetAction.ALLOW:
        message = "Actual expense is within approved amount."
    elif action == OverBudgetAction.WARNING:
        message = "Actual expense exceeds approved amount but is allowed with warning."
    elif action == OverBudgetAction.REVIEW:
        if variance_type == VarianceType.FX_VARIANCE:
            message = "Actual expense exceeds approved base amount due to FX variance and was routed to accounting review."
        else:
            message = "Actual expense exceeds approved amount and was routed to accounting review."
    elif action == OverBudgetAction.AMENDMENT_REQUIRED:
        message = "Actual expense exceeds approved amount and requires a supplemental request or exception approval."
    else:
        message = "Actual expense exceeds approved amount and is blocked by finance policy."

    return ActualExpensePolicyResult(
        request_obj=request_obj,
        request_type=request_type,
        approved_amount=approved_amount,
        existing_actual_total=existing_actual_total,
        current_actual_amount=current_actual_amount,
        new_actual_total=new_actual_total,
        over_amount=over_amount,
        over_percent=over_percent,
        action=action,
        policy=policy,
        payment_method=payment_method,
        currency=effective_currency,
        message=message,
        transaction_currency=snapshot["transaction_currency"],
        transaction_amount=snapshot["transaction_amount"],
        base_currency=snapshot["base_currency"],
        base_amount=snapshot["base_amount"],
        exchange_rate=snapshot["exchange_rate"],
        exchange_rate_date=snapshot["exchange_rate_date"],
        exchange_rate_source=snapshot["exchange_rate_source"],
        variance_type=variance_type,
        fx_policy=fx_policy,
    )


def _request_has_attachment_for_receipt_policy(request_obj):
    attachments = getattr(request_obj, "attachments", None)
    if attachments is None:
        return False
    return attachments.exclude(document_type="ACCOUNTING_APPROVAL").exists()


def _receipt_review_exists(result, actual_expense=None, card_transaction=None, card_allocation=None):
    queryset = AccountingReviewItem.objects.filter(
        reason=AccountingReviewReason.MISSING_RECEIPT,
        status__in=OPEN_REVIEW_STATUSES,
    )
    if actual_expense is not None:
        if result.request_type == RequestType.PURCHASE:
            queryset = queryset.filter(purchase_actual_spend=actual_expense)
        elif result.request_type == RequestType.TRAVEL:
            queryset = queryset.filter(travel_actual_expense=actual_expense)
    if card_transaction is not None:
        queryset = queryset.filter(card_transaction=card_transaction)
    if card_allocation is not None:
        queryset = queryset.filter(card_allocation=card_allocation)
    return queryset.exists()


def apply_receipt_policy_result(
    result,
    *,
    actual_expense=None,
    card_transaction=None,
    card_allocation=None,
    acting_user=None,
):
    if not result.requires_review or _request_has_attachment_for_receipt_policy(result.request_obj):
        return None
    if _receipt_review_exists(result, actual_expense, card_transaction, card_allocation):
        return None

    content_type = None
    object_id = None
    if actual_expense is not None:
        content_type = ContentType.objects.get_for_model(actual_expense)
        object_id = actual_expense.pk

    required = []
    if result.requires_receipt:
        required.append("receipt")
    if result.requires_invoice:
        required.append("invoice")
    required_text = " and ".join(required) or "attachment"
    request_obj = result.request_obj
    return AccountingReviewItem.objects.create(
        source_type=result.request_type,
        purchase_request=request_obj if result.request_type == RequestType.PURCHASE else None,
        travel_request=request_obj if result.request_type == RequestType.TRAVEL else None,
        purchase_actual_spend=actual_expense if result.request_type == RequestType.PURCHASE else None,
        travel_actual_expense=actual_expense if result.request_type == RequestType.TRAVEL else None,
        card_transaction=card_transaction,
        card_allocation=card_allocation,
        source_content_type=content_type,
        source_object_id=object_id,
        reason=AccountingReviewReason.MISSING_RECEIPT,
        status=AccountingReviewStatus.PENDING_REVIEW,
        policy_action="",
        amount=result.amount,
        over_amount=Decimal("0.00"),
        over_percent=Decimal("0.0000"),
        title=f"{get_request_no(request_obj)} missing {required_text}",
        description=result.message,
        created_by=acting_user,
    )


def apply_receipt_policy_for_actual(
    request_obj,
    *,
    actual_expense=None,
    amount,
    payment_method=PaymentMethod.REIMBURSEMENT,
    expense_type="",
    currency="",
    card_transaction=None,
    card_allocation=None,
    acting_user=None,
):
    result = evaluate_receipt_policy(
        request_obj,
        amount=amount,
        payment_method=payment_method,
        expense_type=expense_type,
        currency=currency,
    )
    return apply_receipt_policy_result(
        result,
        actual_expense=actual_expense,
        card_transaction=card_transaction,
        card_allocation=card_allocation,
        acting_user=acting_user,
    )


def _set_request_pending_review_fields(result, *, note="", commit=True):
    request_obj = result.request_obj
    if not hasattr(request_obj, "is_over_estimate"):
        return

    request_obj.is_over_estimate = result.is_over_budget
    if result.is_over_budget:
        request_obj.actual_review_status = "PENDING_REVIEW"
        request_obj.pending_overage_amount = result.current_actual_amount
        request_obj.pending_overage_note = note or result.message
    else:
        request_obj.actual_review_status = "NOT_REQUIRED"
        request_obj.pending_overage_amount = Decimal("0.00")
        request_obj.pending_overage_note = ""

    if commit:
        request_obj.save(
            update_fields=[
                "is_over_estimate",
                "actual_review_status",
                "pending_overage_amount",
                "pending_overage_note",
            ]
        )


def create_accounting_review_item(
    result,
    *,
    reason=AccountingReviewReason.OVER_BUDGET,
    actual_expense=None,
    card_transaction=None,
    card_allocation=None,
    created_by=None,
    description="",
):
    request_obj = result.request_obj
    content_type = None
    object_id = None
    if actual_expense is not None:
        content_type = ContentType.objects.get_for_model(actual_expense)
        object_id = actual_expense.pk

    defaults = {
        "source_type": result.request_type,
        "purchase_request": request_obj if result.request_type == RequestType.PURCHASE else None,
        "travel_request": request_obj if result.request_type == RequestType.TRAVEL else None,
        "purchase_actual_spend": actual_expense if result.request_type == RequestType.PURCHASE else None,
        "travel_actual_expense": actual_expense if result.request_type == RequestType.TRAVEL else None,
        "card_transaction": card_transaction,
        "card_allocation": card_allocation,
        "source_content_type": content_type,
        "source_object_id": object_id,
        "reason": reason,
        "status": AccountingReviewStatus.PENDING_REVIEW,
        "policy": result.policy,
        "policy_action": result.action,
        "amount": result.current_actual_amount,
        "over_amount": result.over_amount,
        "over_percent": result.over_percent,
        "variance_type": result.variance_type,
        "transaction_currency": result.transaction_currency,
        "transaction_amount": result.transaction_amount,
        "base_currency": result.base_currency,
        "base_amount": result.base_amount,
        "exchange_rate": result.exchange_rate,
        "exchange_rate_date": result.exchange_rate_date,
        "exchange_rate_source": result.exchange_rate_source,
        "title": f"{get_request_no(request_obj)} over-budget review",
        "description": description or result.message,
        "created_by": created_by,
    }
    return AccountingReviewItem.objects.create(**defaults)


def _add_request_history(request_obj, *, acting_user=None, comment=""):
    writer = getattr(request_obj, "_add_history", None)
    if callable(writer):
        try:
            writer(
                action_type="SPEND_RECORDED",
                from_status=getattr(request_obj, "status", None),
                to_status=getattr(request_obj, "status", None),
                acting_user=acting_user,
                comment=comment,
            )
        except Exception:
            return


def apply_actual_expense_policy_result(
    result,
    *,
    actual_expense=None,
    card_transaction=None,
    card_allocation=None,
    acting_user=None,
):
    if result.action == OverBudgetAction.BLOCK:
        _set_request_pending_review_fields(result, note=result.message)
        raise ValidationError(result.message)

    if result.action == OverBudgetAction.AMENDMENT_REQUIRED:
        _set_request_pending_review_fields(result, note=result.message)
        return create_accounting_review_item(
            result,
            actual_expense=actual_expense,
            card_transaction=card_transaction,
            card_allocation=card_allocation,
            created_by=acting_user,
            description=result.message,
        )

    if result.action == OverBudgetAction.WARNING:
        request_obj = result.request_obj
        if result.is_over_budget and hasattr(request_obj, "actual_review_status"):
            request_obj.is_over_estimate = True
            request_obj.actual_review_status = "APPROVED_TO_PROCEED"
            request_obj.actual_review_comment = result.message
            request_obj.actual_reviewed_by = acting_user
            request_obj.actual_reviewed_at = timezone.now()
            request_obj.pending_overage_amount = Decimal("0.00")
            request_obj.pending_overage_note = ""
            request_obj.save(
                update_fields=[
                    "is_over_estimate",
                    "actual_review_status",
                    "actual_review_comment",
                    "actual_reviewed_by",
                    "actual_reviewed_at",
                    "pending_overage_amount",
                    "pending_overage_note",
                ]
            )
        _add_request_history(
            result.request_obj,
            acting_user=acting_user,
            comment=(
                f"Over-budget warning: approved {result.currency} {result.approved_amount}, "
                f"new actual total {result.currency} {result.new_actual_total}, "
                f"over {result.currency} {result.over_amount}."
            ),
        )
        return None

    if result.action == OverBudgetAction.ALLOW and result.is_over_budget:
        request_obj = result.request_obj
        if hasattr(request_obj, "actual_review_status"):
            request_obj.is_over_estimate = True
            request_obj.actual_review_status = "APPROVED_TO_PROCEED"
            request_obj.actual_review_comment = result.message
            request_obj.actual_reviewed_by = acting_user
            request_obj.actual_reviewed_at = timezone.now()
            request_obj.pending_overage_amount = Decimal("0.00")
            request_obj.pending_overage_note = ""
            request_obj.save(
                update_fields=[
                    "is_over_estimate",
                    "actual_review_status",
                    "actual_review_comment",
                    "actual_reviewed_by",
                    "actual_reviewed_at",
                    "pending_overage_amount",
                    "pending_overage_note",
                ]
            )
        return None

    if result.action == OverBudgetAction.REVIEW:
        _set_request_pending_review_fields(result, note=result.message)
        reason = (
            AccountingReviewReason.FX_VARIANCE
            if result.variance_type == VarianceType.FX_VARIANCE
            else AccountingReviewReason.BASE_CURRENCY_VARIANCE
            if result.variance_type == VarianceType.BASE_CURRENCY_VARIANCE
            else AccountingReviewReason.OVER_BUDGET
        )
        return create_accounting_review_item(
            result,
            reason=reason,
            actual_expense=actual_expense,
            card_transaction=card_transaction,
            card_allocation=card_allocation,
            created_by=acting_user,
            description=result.message,
        )

    return None


def unresolved_review_items_for_request(request_obj):
    request_type = get_request_type(request_obj)
    queryset = AccountingReviewItem.objects.filter(status__in=OPEN_REVIEW_STATUSES)
    if request_type == RequestType.PURCHASE:
        queryset = queryset.filter(purchase_request=request_obj)
    elif request_type == RequestType.TRAVEL:
        queryset = queryset.filter(travel_request=request_obj)
    return queryset


def create_duplicate_card_review_item(card_transaction, *, created_by=None):
    if not card_transaction.has_possible_duplicate():
        return None
    if card_transaction.review_items.filter(
        reason=AccountingReviewReason.DUPLICATE_CARD,
        status__in=OPEN_REVIEW_STATUSES,
    ).exists():
        return None
    return AccountingReviewItem.objects.create(
        source_type="CARD_TRANSACTION",
        card_transaction=card_transaction,
        reason=AccountingReviewReason.DUPLICATE_CARD,
        status=AccountingReviewStatus.PENDING_REVIEW,
        amount=card_transaction.amount,
        title=f"Possible duplicate card transaction {card_transaction.reference_no}",
        description=(
            "Same merchant, amount, transaction date, and reference were found. "
            "Review before treating this as a legitimate separate transaction."
        ),
        created_by=created_by,
    )


@transaction.atomic
def mark_card_transaction_reviewed(card_transaction, *, acting_user=None):
    if card_transaction.match_status != CardTransactionMatchStatus.MATCHED:
        raise ValidationError("Only fully matched card transactions can be marked reviewed.")
    if card_transaction.review_items.filter(status__in=OPEN_REVIEW_STATUSES).exists():
        raise ValidationError("Cannot mark card transaction reviewed while review items are unresolved.")
    card_transaction.match_status = CardTransactionMatchStatus.REVIEWED
    card_transaction.save(update_fields=["match_status"])
    return card_transaction


def validate_request_can_close(request_obj):
    if unresolved_review_items_for_request(request_obj).exists():
        raise ValidationError("Cannot close request while accounting review items are unresolved.")
    supplemental_requests = getattr(request_obj, "supplemental_requests", None)
    if supplemental_requests is not None:
        open_statuses = [
            "DRAFT",
            "SUBMITTED",
            "PENDING",
            "PENDING_APPROVAL",
            "RETURNED",
        ]
        if supplemental_requests.filter(status__in=open_statuses).exists():
            raise ValidationError("Cannot close request while amendment requests are still open.")
    if hasattr(request_obj, "approval_tasks"):
        if request_obj.approval_tasks.filter(status__in=["WAITING", "POOL", "PENDING"]).exists():
            raise ValidationError("Cannot close request while approval tasks are still open.")
    if hasattr(request_obj, "card_allocations"):
        if request_obj.card_allocations.filter(card_transaction__match_status__in=["UNMATCHED", "PARTIALLY_MATCHED"]).exists():
            raise ValidationError("Cannot close request while linked card transactions are not fully reconciled.")


@transaction.atomic
def resolve_accounting_review_items_for_request(request_obj, *, decision, comment="", acting_user=None):
    status_map = {
        AccountingReviewDecision.APPROVE_EXCEPTION: AccountingReviewStatus.APPROVED_EXCEPTION,
        AccountingReviewDecision.RETURN: AccountingReviewStatus.RETURNED,
        AccountingReviewDecision.REJECT: AccountingReviewStatus.REJECTED,
        AccountingReviewDecision.RESOLVE: AccountingReviewStatus.RESOLVED,
    }
    status = status_map.get(decision)
    if not status:
        raise ValidationError("Invalid accounting review decision.")
    items = unresolved_review_items_for_request(request_obj)
    now = timezone.now()
    count = items.update(
        status=status,
        decision=decision,
        comment=comment or "",
        reviewed_by=acting_user,
        reviewed_at=now,
    )
    return count


@transaction.atomic
def allocate_card_transaction(
    *,
    card_transaction,
    amount,
    purchase_request=None,
    travel_request=None,
    project=None,
    acting_user=None,
    notes="",
):
    amount = _money(amount)
    if amount > card_transaction.get_unallocated_amount():
        raise ValidationError("Allocation amount cannot exceed the unallocated card transaction amount.")

    allocation = CardTransactionAllocation(
        card_transaction=card_transaction,
        amount=amount,
        purchase_request=purchase_request,
        travel_request=travel_request,
        project=project,
        created_by=acting_user,
        notes=notes or "",
    )
    allocation.full_clean()

    request_obj = purchase_request or travel_request
    result = None
    allocated_transaction_amount = amount
    if card_transaction.base_amount:
        allocated_transaction_amount = _money(card_transaction.transaction_amount * amount / card_transaction.base_amount)
    if request_obj is not None:
        result = evaluate_actual_expense_policy(
            request_obj,
            current_actual_amount=amount,
            current_transaction_amount=allocated_transaction_amount,
            transaction_currency=card_transaction.transaction_currency,
            base_amount=amount,
            base_currency=card_transaction.base_currency,
            exchange_rate=card_transaction.exchange_rate,
            exchange_rate_date=card_transaction.exchange_rate_date,
            exchange_rate_source=card_transaction.exchange_rate_source,
            payment_method=PaymentMethod.COMPANY_CARD,
            currency=card_transaction.base_currency,
        )
        if not result.allows_recording:
            apply_actual_expense_policy_result(
                result,
                card_transaction=card_transaction,
                card_allocation=None,
                acting_user=acting_user,
            )

    allocation.policy = result.policy if result else None
    allocation.policy_action = result.action if result else ""
    allocation.save()

    if request_obj is not None and result is not None:
        apply_actual_expense_policy_result(
            result,
            card_transaction=card_transaction,
            card_allocation=allocation,
            acting_user=acting_user,
        )
        if purchase_request is not None:
            purchase_request.record_actual_spend(
                spend_date=card_transaction.transaction_date,
                amount=amount,
                acting_user=acting_user,
                vendor_name=card_transaction.merchant_name,
                reference_no=card_transaction.reference_no,
                notes=notes or "Company card allocation.",
                transaction_currency=card_transaction.transaction_currency,
                transaction_amount=allocated_transaction_amount,
                base_amount=amount,
                exchange_rate=card_transaction.exchange_rate,
                exchange_rate_date=card_transaction.exchange_rate_date,
                exchange_rate_source=card_transaction.exchange_rate_source,
                skip_finance_policy=True,
                payment_method=PaymentMethod.COMPANY_CARD,
                card_transaction=card_transaction,
                card_allocation=allocation,
            )
        elif travel_request is not None:
            travel_request.record_actual_expense(
                expense_type="MISC",
                expense_date=card_transaction.transaction_date,
                actual_amount=amount,
                acting_user=acting_user,
                currency=card_transaction.currency,
                transaction_currency=card_transaction.transaction_currency,
                transaction_amount=allocated_transaction_amount,
                base_amount=amount,
                exchange_rate=card_transaction.exchange_rate,
                exchange_rate_date=card_transaction.exchange_rate_date,
                exchange_rate_source=card_transaction.exchange_rate_source,
                vendor_name=card_transaction.merchant_name,
                reference_no=card_transaction.reference_no,
                notes=notes or "Company card allocation.",
                skip_finance_policy=True,
                payment_method=PaymentMethod.COMPANY_CARD,
                card_transaction=card_transaction,
                card_allocation=allocation,
            )
    elif project is not None:
        allocated_transaction_amount = amount
        if card_transaction.base_amount:
            allocated_transaction_amount = _money(card_transaction.transaction_amount * amount / card_transaction.base_amount)
        ProjectBudgetEntry.objects.create(
            project=project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.PROJECT,
            source_id=project.id,
            amount=amount,
            currency=card_transaction.base_currency,
            source_transaction_currency=card_transaction.transaction_currency,
            source_transaction_amount=allocated_transaction_amount,
            source_exchange_rate=card_transaction.exchange_rate,
            source_exchange_rate_source=card_transaction.exchange_rate_source,
            notes=f"Company card transaction {card_transaction.reference_no} allocated directly to project.",
            created_by=acting_user,
        )

    card_transaction.refresh_match_status()
    return allocation
