from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models

from common.choices import CurrencyCode, RequestType
from projects.models import ProjectType


class PaymentMethod(models.TextChoices):
    ALL = "ALL", "All"
    REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
    COMPANY_CARD = "COMPANY_CARD", "Company Card"
    AP_INVOICE = "AP_INVOICE", "AP Invoice"
    MANUAL = "MANUAL", "Manual Accounting Entry"


class ExchangeRateSource(models.TextChoices):
    COMPANY_RATE = "COMPANY_RATE", "Company Rate"
    CARD_STATEMENT = "CARD_STATEMENT", "Card Statement"
    EMPLOYEE_CARD_STATEMENT = "EMPLOYEE_CARD_STATEMENT", "Employee Card Statement"
    ACCOUNTING_OVERRIDE = "ACCOUNTING_OVERRIDE", "Accounting Override"
    MANUAL = "MANUAL", "Manual"


class VarianceType(models.TextChoices):
    NONE = "NONE", "None"
    FX_VARIANCE = "FX_VARIANCE", "FX Variance"
    SPENDING_OVERRUN = "SPENDING_OVERRUN", "Spending Overrun"
    MIXED_VARIANCE = "MIXED_VARIANCE", "Mixed Variance"
    BASE_CURRENCY_VARIANCE = "BASE_CURRENCY_VARIANCE", "Base Currency Variance"
    NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"


class OverBudgetAction(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    WARNING = "WARNING", "Warning"
    REVIEW = "REVIEW", "Review"
    AMENDMENT_REQUIRED = "AMENDMENT_REQUIRED", "Amendment Required"
    BLOCK = "BLOCK", "Block"


class FXVarianceAction(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    WARNING = "WARNING", "Warning"
    REVIEW = "REVIEW", "Review"
    FINANCE_REVIEW_REQUIRED = "FINANCE_REVIEW_REQUIRED", "Finance Review Required"
    BLOCK = "BLOCK", "Block"


class AccountingPeriodStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSING = "CLOSING", "Closing"
    CLOSED = "CLOSED", "Closed"


class DirectProjectCostAction(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    REVIEW = "REVIEW", "Review"
    REQUIRE_PROJECT_OWNER_APPROVAL = "REQUIRE_PROJECT_OWNER_APPROVAL", "Require Project Owner Approval"
    BLOCK = "BLOCK", "Block"


class Currency(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=10, blank=True, default="")
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "PS_A8_FIN_CUR"
        verbose_name = "Currency"
        verbose_name_plural = "Currencies"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=10)
    to_currency = models.CharField(max_length=10, default=CurrencyCode.USD)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    effective_date = models.DateField()
    source = models.CharField(max_length=30, choices=ExchangeRateSource, default=ExchangeRateSource.COMPANY_RATE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_exchange_rates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_FIN_FX_RATE"
        verbose_name = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"
        ordering = ["-effective_date", "from_currency", "to_currency"]
        indexes = [models.Index(fields=["from_currency", "to_currency", "effective_date", "source"])]

    def __str__(self):
        return f"{self.from_currency}->{self.to_currency} {self.rate} @ {self.effective_date}"


class OverBudgetPolicy(models.Model):
    REQUEST_TYPE_CHOICES = [
        ("ALL", "All"),
        (RequestType.PURCHASE, "Purchase Request"),
        (RequestType.TRAVEL, "Travel Request"),
    ]

    policy_code = models.CharField(max_length=30, unique=True)
    policy_name = models.CharField(max_length=120)
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES, default="ALL")
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="over_budget_policies",
    )
    project_type = models.CharField(max_length=30, choices=ProjectType, blank=True, default="")
    payment_method = models.CharField(max_length=30, choices=PaymentMethod, default=PaymentMethod.ALL)
    currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    over_amount_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    over_amount_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    over_percent_from = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    over_percent_to = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    action = models.CharField(max_length=30, choices=OverBudgetAction, default=OverBudgetAction.REVIEW)
    requires_comment = models.BooleanField(default=False)
    requires_attachment = models.BooleanField(default=False)
    requires_manager_review = models.BooleanField(default=False)
    requires_finance_review = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_FIN_OB_POL"
        verbose_name = "Over-Budget Policy"
        verbose_name_plural = "Over-Budget Policies"
        ordering = ["priority", "policy_code"]

    def __str__(self):
        return f"{self.policy_code} - {self.policy_name}"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.over_amount_from is not None
            and self.over_amount_to is not None
            and self.over_amount_from > self.over_amount_to
        ):
            errors["over_amount_to"] = "Over amount to must be greater than or equal to over amount from."
        if (
            self.over_percent_from is not None
            and self.over_percent_to is not None
            and self.over_percent_from > self.over_percent_to
        ):
            errors["over_percent_to"] = "Over percent to must be greater than or equal to over percent from."
        if errors:
            raise ValidationError(errors)


class FXVariancePolicy(models.Model):
    policy_code = models.CharField(max_length=30, unique=True)
    policy_name = models.CharField(max_length=120)
    currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    fx_variance_amount_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fx_variance_amount_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fx_variance_percent_from = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    fx_variance_percent_to = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    action = models.CharField(max_length=30, choices=FXVarianceAction, default=FXVarianceAction.REVIEW)
    requires_comment = models.BooleanField(default=False)
    requires_finance_review = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_FIN_FX_POL"
        verbose_name = "FX Variance Policy"
        verbose_name_plural = "FX Variance Policies"
        ordering = ["priority", "policy_code"]

    def __str__(self):
        return f"{self.policy_code} - {self.policy_name}"


class AccountingPeriod(models.Model):
    period_code = models.CharField(max_length=20, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=AccountingPeriodStatus, default=AccountingPeriodStatus.OPEN)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closed_accounting_periods",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_FIN_PERIOD"
        verbose_name = "Accounting Period"
        verbose_name_plural = "Accounting Periods"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.period_code} / {self.status}"

    def contains(self, value):
        return self.start_date <= value <= self.end_date


class DirectProjectCostPolicy(models.Model):
    policy_code = models.CharField(max_length=30, unique=True)
    policy_name = models.CharField(max_length=120)
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="direct_project_cost_policies",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="direct_cost_policies",
    )
    project_type = models.CharField(max_length=30, choices=ProjectType, blank=True, default="")
    payment_method = models.CharField(max_length=30, choices=PaymentMethod, default=PaymentMethod.COMPANY_CARD)
    amount_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    action = models.CharField(max_length=40, choices=DirectProjectCostAction, default=DirectProjectCostAction.REVIEW)
    requires_receipt = models.BooleanField(default=True)
    requires_project_owner_review = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_FIN_DPC_POL"
        verbose_name = "Direct Project Cost Policy"
        verbose_name_plural = "Direct Project Cost Policies"
        ordering = ["priority", "policy_code"]

    def __str__(self):
        return f"{self.policy_code} - {self.policy_name}"


class ReceiptPolicy(models.Model):
    REQUEST_TYPE_CHOICES = [
        ("ALL", "All"),
        (RequestType.PURCHASE, "Purchase Request"),
        (RequestType.TRAVEL, "Travel Request"),
    ]

    policy_code = models.CharField(max_length=30, unique=True)
    policy_name = models.CharField(max_length=120)
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES, default="ALL")
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="receipt_policies",
    )
    project_type = models.CharField(max_length=30, choices=ProjectType, blank=True, default="")
    expense_type = models.CharField(max_length=30, blank=True, default="")
    payment_method = models.CharField(max_length=30, choices=PaymentMethod, default=PaymentMethod.ALL)
    currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    amount_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requires_receipt = models.BooleanField(default=True)
    requires_invoice = models.BooleanField(default=False)
    allows_exception = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_FIN_RCPT_POL"
        verbose_name = "Receipt Policy"
        verbose_name_plural = "Receipt Policies"
        ordering = ["priority", "policy_code"]

    def __str__(self):
        return f"{self.policy_code} - {self.policy_name}"

    def clean(self):
        super().clean()
        if self.amount_from is not None and self.amount_to is not None and self.amount_from > self.amount_to:
            raise ValidationError({"amount_to": "Amount to must be greater than or equal to amount from."})


class AccountingReviewReason(models.TextChoices):
    OVER_BUDGET = "OVER_BUDGET", "Over Budget"
    FX_VARIANCE = "FX_VARIANCE", "FX Variance"
    BASE_CURRENCY_VARIANCE = "BASE_CURRENCY_VARIANCE", "Base Currency Variance"
    MISSING_RECEIPT = "MISSING_RECEIPT", "Missing Receipt"
    UNMATCHED_CARD = "UNMATCHED_CARD", "Unmatched Card Transaction"
    DUPLICATE_CARD = "DUPLICATE_CARD", "Duplicate Card Transaction"
    DIRECT_PROJECT_COST = "DIRECT_PROJECT_COST", "Direct Project Cost"
    POLICY_EXCEPTION = "POLICY_EXCEPTION", "Policy Exception"
    MANUAL_FLAG = "MANUAL_FLAG", "Manual Flag"


class AccountingReviewStatus(models.TextChoices):
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
    APPROVED_EXCEPTION = "APPROVED_EXCEPTION", "Approved Exception"
    RETURNED = "RETURNED", "Returned"
    REJECTED = "REJECTED", "Rejected"
    RESOLVED = "RESOLVED", "Resolved"


class AccountingReviewDecision(models.TextChoices):
    NONE = "", "-"
    APPROVE_EXCEPTION = "APPROVE_EXCEPTION", "Approve Exception"
    RETURN = "RETURN", "Return"
    REJECT = "REJECT", "Reject"
    RESOLVE = "RESOLVE", "Resolve"


class AccountingReviewItem(models.Model):
    SOURCE_TYPE_CHOICES = [
        (RequestType.PURCHASE, "Purchase Request"),
        (RequestType.TRAVEL, "Travel Request"),
        ("CARD_TRANSACTION", "Card Transaction"),
        ("CARD_ALLOCATION", "Card Allocation"),
    ]

    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES)
    purchase_request = models.ForeignKey(
        "purchase.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="accounting_review_items",
    )
    travel_request = models.ForeignKey(
        "travel.TravelRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="accounting_review_items",
    )
    purchase_actual_spend = models.ForeignKey(
        "purchase.PurchaseActualSpend",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounting_review_items",
    )
    travel_actual_expense = models.ForeignKey(
        "travel.TravelActualExpenseLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounting_review_items",
    )
    card_transaction = models.ForeignKey(
        "finance.CardTransaction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="review_items",
    )
    card_allocation = models.ForeignKey(
        "finance.CardTransactionAllocation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="review_items",
    )
    source_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="finance_review_items",
    )
    source_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_object = GenericForeignKey("source_content_type", "source_object_id")
    reason = models.CharField(max_length=30, choices=AccountingReviewReason)
    status = models.CharField(
        max_length=30,
        choices=AccountingReviewStatus,
        default=AccountingReviewStatus.PENDING_REVIEW,
    )
    policy = models.ForeignKey(
        OverBudgetPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_items",
    )
    direct_project_cost_policy = models.ForeignKey(
        DirectProjectCostPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_items",
    )
    policy_action = models.CharField(max_length=30, choices=OverBudgetAction, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    over_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    over_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    variance_type = models.CharField(max_length=30, choices=VarianceType, blank=True, default="")
    transaction_currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    base_currency = models.CharField(max_length=10, choices=CurrencyCode, default=CurrencyCode.USD)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    exchange_rate_date = models.DateField(null=True, blank=True)
    exchange_rate_source = models.CharField(max_length=30, choices=ExchangeRateSource, blank=True, default="")
    title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_accounting_review_items",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_accounting_review_items",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(max_length=30, choices=AccountingReviewDecision, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_accounting_review_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_FIN_REV"
        verbose_name = "Accounting Review Item"
        verbose_name_plural = "Accounting Review Items"
        ordering = ["status", "-created_at", "-id"]

    def __str__(self):
        return f"{self.get_source_type_display()} / {self.reason} / {self.status}"

    @property
    def is_unresolved(self):
        return self.status in [AccountingReviewStatus.PENDING_REVIEW, AccountingReviewStatus.RETURNED]


class CardTransactionMatchStatus(models.TextChoices):
    UNMATCHED = "UNMATCHED", "Unmatched"
    PARTIALLY_MATCHED = "PARTIALLY_MATCHED", "Partially Matched"
    MATCHED = "MATCHED", "Matched"
    REVIEWED = "REVIEWED", "Reviewed"


class CardTransaction(models.Model):
    statement_date = models.DateField()
    transaction_date = models.DateField()
    merchant_name = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, choices=CurrencyCode, default=CurrencyCode.USD)
    transaction_currency = models.CharField(max_length=10, choices=CurrencyCode, default=CurrencyCode.USD)
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    base_currency = models.CharField(max_length=10, choices=CurrencyCode, default=CurrencyCode.USD)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    exchange_rate_date = models.DateField(null=True, blank=True)
    exchange_rate_source = models.CharField(max_length=30, choices=ExchangeRateSource, blank=True, default="")
    exchange_rate_override_reason = models.TextField(blank=True, default="")
    cardholder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="card_transactions",
    )
    reference_no = models.CharField(max_length=100)
    match_status = models.CharField(
        max_length=30,
        choices=CardTransactionMatchStatus,
        default=CardTransactionMatchStatus.UNMATCHED,
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imported_card_transactions",
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_FIN_CARD_TXN"
        verbose_name = "Card Transaction"
        verbose_name_plural = "Card Transactions"
        ordering = ["-statement_date", "-transaction_date", "-id"]
        indexes = [
            models.Index(fields=["statement_date", "amount", "merchant_name", "reference_no"]),
        ]

    def __str__(self):
        return f"{self.transaction_date} / {self.merchant_name} / {self.amount}"

    def get_allocated_amount(self):
        total = self.allocations.aggregate(total=models.Sum("amount"))["total"]
        return total or Decimal("0.00")

    def get_unallocated_amount(self):
        return self.amount - self.get_allocated_amount()

    def refresh_match_status(self, commit=True):
        allocated = self.get_allocated_amount()
        if allocated <= 0:
            self.match_status = CardTransactionMatchStatus.UNMATCHED
        elif allocated < self.amount:
            self.match_status = CardTransactionMatchStatus.PARTIALLY_MATCHED
        else:
            self.match_status = CardTransactionMatchStatus.MATCHED
        if commit:
            self.save(update_fields=["match_status"])
        return self.match_status

    def has_possible_duplicate(self):
        return CardTransaction.objects.filter(
            statement_date=self.statement_date,
            transaction_date=self.transaction_date,
            amount=self.amount,
            merchant_name__iexact=self.merchant_name,
            reference_no=self.reference_no,
        ).exclude(pk=self.pk).exists()

    def save(self, *args, **kwargs):
        if not self.transaction_currency:
            self.transaction_currency = self.currency
        if self.transaction_amount in [None, Decimal("0.00")]:
            self.transaction_amount = self.amount
        if not self.base_currency:
            self.base_currency = CurrencyCode.USD
        if self.base_amount in [None, Decimal("0.00")]:
            self.base_amount = self.amount
        self.amount = self.base_amount
        self.currency = self.base_currency
        if not self.exchange_rate and self.transaction_amount:
            self.exchange_rate = (self.base_amount / self.transaction_amount).quantize(Decimal("0.00000001"))
        if not self.exchange_rate_date:
            self.exchange_rate_date = self.transaction_date
        if not self.exchange_rate_source:
            self.exchange_rate_source = ExchangeRateSource.CARD_STATEMENT
        super().save(*args, **kwargs)


class CardTransactionAllocation(models.Model):
    card_transaction = models.ForeignKey(
        CardTransaction,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    purchase_request = models.ForeignKey(
        "purchase.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="card_allocations",
    )
    travel_request = models.ForeignKey(
        "travel.TravelRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="card_allocations",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="card_allocations",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    policy = models.ForeignKey(
        OverBudgetPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="card_allocations",
    )
    direct_project_cost_policy = models.ForeignKey(
        DirectProjectCostPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="card_allocations",
    )
    direct_project_cost_action = models.CharField(max_length=40, choices=DirectProjectCostAction, blank=True, default="")
    project_owner_review_status = models.CharField(max_length=30, blank=True, default="")
    policy_action = models.CharField(max_length=30, choices=OverBudgetAction, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_card_allocations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_FIN_CARD_ALLOC"
        verbose_name = "Card Transaction Allocation"
        verbose_name_plural = "Card Transaction Allocations"
        ordering = ["card_transaction", "id"]

    def __str__(self):
        return f"{self.card_transaction_id} / {self.amount}"

    def clean(self):
        super().clean()
        linked_count = sum(
            1 for value in [self.purchase_request_id, self.travel_request_id, self.project_id] if value
        )
        if linked_count != 1:
            raise ValidationError("Allocation must link to exactly one purchase request, travel request, or project.")
        if self.amount <= 0:
            raise ValidationError("Allocation amount must be greater than 0.")

    @property
    def linked_request(self):
        return self.purchase_request or self.travel_request


class ActualExpenseAttachmentType(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    INVOICE = "INVOICE", "Invoice"
    QUOTE = "QUOTE", "Quote"
    OTHER = "OTHER", "Other"


class ActualExpenseAttachment(models.Model):
    purchase_actual_spend = models.ForeignKey(
        "purchase.PurchaseActualSpend",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="line_attachments",
    )
    travel_actual_expense = models.ForeignKey(
        "travel.TravelActualExpenseLine",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="line_attachments",
    )
    purchase_attachment = models.ForeignKey(
        "purchase.PurchaseRequestAttachment",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="actual_expense_links",
    )
    travel_attachment = models.ForeignKey(
        "travel.TravelRequestAttachment",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="actual_expense_links",
    )
    attachment_type = models.CharField(max_length=20, choices=ActualExpenseAttachmentType, default=ActualExpenseAttachmentType.RECEIPT)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="actual_expense_attachment_links",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_FIN_ACT_ATT"
        verbose_name = "Actual Expense Attachment"
        verbose_name_plural = "Actual Expense Attachments"

    def clean(self):
        super().clean()
        actual_count = sum(1 for value in [self.purchase_actual_spend_id, self.travel_actual_expense_id] if value)
        attachment_count = sum(1 for value in [self.purchase_attachment_id, self.travel_attachment_id] if value)
        if actual_count != 1:
            raise ValidationError("Link exactly one purchase or travel actual expense.")
        if attachment_count != 1:
            raise ValidationError("Link exactly one purchase or travel attachment.")


class CardAllocationAttachment(models.Model):
    card_transaction = models.ForeignKey(
        CardTransaction,
        on_delete=models.CASCADE,
        related_name="allocation_attachments",
    )
    allocation = models.ForeignKey(
        CardTransactionAllocation,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    attachment_type = models.CharField(max_length=20, choices=ActualExpenseAttachmentType, default=ActualExpenseAttachmentType.RECEIPT)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="card_allocation_attachment_links",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_FIN_CARD_ATT"
        verbose_name = "Card Allocation Attachment"
        verbose_name_plural = "Card Allocation Attachments"
