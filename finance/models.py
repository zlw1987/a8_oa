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


class OverBudgetAction(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    WARNING = "WARNING", "Warning"
    REVIEW = "REVIEW", "Review"
    AMENDMENT_REQUIRED = "AMENDMENT_REQUIRED", "Amendment Required"
    BLOCK = "BLOCK", "Block"


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
    MISSING_RECEIPT = "MISSING_RECEIPT", "Missing Receipt"
    UNMATCHED_CARD = "UNMATCHED_CARD", "Unmatched Card Transaction"
    DUPLICATE_CARD = "DUPLICATE_CARD", "Duplicate Card Transaction"
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
    policy_action = models.CharField(max_length=30, choices=OverBudgetAction, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    over_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    over_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
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
