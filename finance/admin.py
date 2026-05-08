from django.contrib import admin

from .models import (
    AccountingReviewItem,
    CardTransaction,
    CardTransactionAllocation,
    OverBudgetPolicy,
    ReceiptPolicy,
)


@admin.register(OverBudgetPolicy)
class OverBudgetPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_code",
        "policy_name",
        "request_type",
        "department",
        "project_type",
        "payment_method",
        "currency",
        "action",
        "priority",
        "is_active",
    )
    list_filter = ("request_type", "payment_method", "action", "is_active", "department", "project_type")
    search_fields = ("policy_code", "policy_name")


@admin.register(AccountingReviewItem)
class AccountingReviewItemAdmin(admin.ModelAdmin):
    list_display = ("source_type", "reason", "status", "amount", "over_amount", "policy_action", "created_at")
    list_filter = ("source_type", "reason", "status", "policy_action")
    search_fields = ("title", "description", "comment")


@admin.register(ReceiptPolicy)
class ReceiptPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_code",
        "policy_name",
        "request_type",
        "department",
        "project_type",
        "expense_type",
        "payment_method",
        "requires_receipt",
        "requires_invoice",
        "priority",
        "is_active",
    )
    list_filter = ("request_type", "payment_method", "requires_receipt", "requires_invoice", "is_active")
    search_fields = ("policy_code", "policy_name", "expense_type")


class CardTransactionAllocationInline(admin.TabularInline):
    model = CardTransactionAllocation
    extra = 0


@admin.register(CardTransaction)
class CardTransactionAdmin(admin.ModelAdmin):
    list_display = ("statement_date", "transaction_date", "merchant_name", "amount", "currency", "cardholder", "match_status")
    list_filter = ("match_status", "currency", "statement_date")
    search_fields = ("merchant_name", "reference_no", "cardholder__username")
    inlines = [CardTransactionAllocationInline]


@admin.register(CardTransactionAllocation)
class CardTransactionAllocationAdmin(admin.ModelAdmin):
    list_display = ("card_transaction", "purchase_request", "travel_request", "project", "amount", "policy_action", "created_at")
    list_filter = ("policy_action",)
