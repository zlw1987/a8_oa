from django import forms

from projects.models import Project
from purchase.models import PurchaseRequest
from travel.models import TravelRequest

from .models import (
    AccountingPeriod,
    AccountingReviewDecision,
    AccountingReviewItem,
    DirectProjectCostPolicy,
    CardTransaction,
    CardTransactionAllocation,
    OverBudgetAction,
    OverBudgetPolicy,
    ReceiptPolicy,
)


class AccountingPeriodForm(forms.ModelForm):
    class Meta:
        model = AccountingPeriod
        fields = ["period_code", "start_date", "end_date", "status", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "period_code": "Use a stable code such as 2026-05.",
            "status": "OPEN allows normal financial activity. CLOSED blocks direct changes.",
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error("end_date", "End date must be on or after start date.")
        return cleaned_data


class AccountingPeriodCloseForm(forms.Form):
    notes = forms.CharField(
        required=True,
        label="Close Notes",
        help_text="Explain the month-end close decision or outstanding exceptions.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AccountingPeriodReopenForm(forms.Form):
    reason = forms.CharField(
        required=True,
        label="Reopen Reason",
        help_text="A reason is required because reopening a period can change financial reporting.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class OverBudgetPolicyForm(forms.ModelForm):
    class Meta:
        model = OverBudgetPolicy
        fields = [
            "policy_code",
            "policy_name",
            "request_type",
            "department",
            "project_type",
            "payment_method",
            "currency",
            "over_amount_from",
            "over_amount_to",
            "over_percent_from",
            "over_percent_to",
            "action",
            "requires_comment",
            "requires_attachment",
            "requires_manager_review",
            "requires_finance_review",
            "priority",
            "is_active",
        ]
        help_texts = {
            "priority": "Lower number matches first.",
            "currency": "Leave blank for a general fallback. Finance reports and budget controls use base currency.",
            "action": "WARNING allows posting with audit note. REVIEW creates accounting review. AMENDMENT_REQUIRED blocks closeout until resolved. BLOCK prevents posting.",
            "requires_comment": "Requires accounting/reviewer comment when this policy is applied.",
            "requires_finance_review": "Creates or routes review work for finance when applicable.",
            "over_percent_from": "Use decimal form, for example 0.0500 for 5%.",
            "over_percent_to": "Use decimal form, for example 0.1500 for 15%.",
        }


class ReceiptPolicyForm(forms.ModelForm):
    class Meta:
        model = ReceiptPolicy
        fields = [
            "policy_code",
            "policy_name",
            "request_type",
            "department",
            "project_type",
            "expense_type",
            "payment_method",
            "currency",
            "amount_from",
            "amount_to",
            "requires_receipt",
            "requires_invoice",
            "allows_exception",
            "priority",
            "is_active",
        ]
        help_texts = {
            "priority": "Lower number matches first.",
            "requires_receipt": "When enabled, missing receipt support creates an accounting review item.",
            "requires_invoice": "Use for higher-value or AP invoice requirements.",
            "allows_exception": "If enabled, accounting can approve an exception instead of blocking forever.",
            "currency": "Leave blank for a general fallback. Amount thresholds compare against base amount unless transaction-specific handling is added.",
            "amount_from": "Minimum amount where this receipt rule applies.",
            "amount_to": "Maximum amount where this receipt rule applies.",
        }


class DirectProjectCostPolicyForm(forms.ModelForm):
    class Meta:
        model = DirectProjectCostPolicy
        fields = [
            "policy_code",
            "policy_name",
            "department",
            "project",
            "project_type",
            "payment_method",
            "amount_from",
            "amount_to",
            "currency",
            "action",
            "requires_receipt",
            "requires_project_owner_review",
            "priority",
            "is_active",
        ]
        help_texts = {
            "priority": "Lower number matches first.",
            "action": "ALLOW posts directly. REVIEW creates accounting review. REQUIRE_PROJECT_OWNER_APPROVAL marks owner review required. BLOCK prevents allocation.",
            "requires_receipt": "Direct project cost normally requires receipt support unless an exception is approved.",
            "requires_project_owner_review": "When enabled, project owner review is required even if the action is REVIEW.",
            "currency": "Leave blank for a general fallback. Amount thresholds compare against base currency amount.",
        }

    def clean(self):
        cleaned_data = super().clean()
        amount_from = cleaned_data.get("amount_from")
        amount_to = cleaned_data.get("amount_to")
        if amount_from is not None and amount_to is not None and amount_from > amount_to:
            self.add_error("amount_to", "Amount to must be greater than or equal to amount from.")
        return cleaned_data


class CardTransactionForm(forms.ModelForm):
    class Meta:
        model = CardTransaction
        fields = [
            "statement_date",
            "transaction_date",
            "merchant_name",
            "amount",
            "currency",
            "cardholder",
            "reference_no",
            "notes",
        ]
        widgets = {
            "statement_date": forms.DateInput(attrs={"type": "date"}),
            "transaction_date": forms.DateInput(attrs={"type": "date"}),
        }


class CardTransactionAllocationForm(forms.ModelForm):
    target_type = forms.ChoiceField(
        choices=[
            ("PURCHASE", "Purchase Request"),
            ("TRAVEL", "Travel Request"),
            ("PROJECT", "Project Direct Cost"),
        ]
    )
    purchase_request = forms.ModelChoiceField(
        queryset=PurchaseRequest.objects.all().order_by("-request_date", "-id"),
        required=False,
    )
    travel_request = forms.ModelChoiceField(
        queryset=TravelRequest.objects.all().order_by("-request_date", "-id"),
        required=False,
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.filter(is_active=True).order_by("project_code"),
        required=False,
    )

    class Meta:
        model = CardTransactionAllocation
        fields = ["target_type", "purchase_request", "travel_request", "project", "amount", "notes"]

    def clean(self):
        cleaned_data = super().clean()
        target_type = cleaned_data.get("target_type")
        purchase_request = cleaned_data.get("purchase_request")
        travel_request = cleaned_data.get("travel_request")
        project = cleaned_data.get("project")

        if target_type == "PURCHASE" and not purchase_request:
            self.add_error("purchase_request", "Purchase request is required.")
        if target_type == "TRAVEL" and not travel_request:
            self.add_error("travel_request", "Travel request is required.")
        if target_type == "PROJECT" and not project:
            self.add_error("project", "Project is required.")

        if target_type != "PURCHASE":
            cleaned_data["purchase_request"] = None
        if target_type != "TRAVEL":
            cleaned_data["travel_request"] = None
        if target_type != "PROJECT":
            cleaned_data["project"] = None

        return cleaned_data


class AccountingReviewDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            (AccountingReviewDecision.APPROVE_EXCEPTION, "Approve Exception"),
            (AccountingReviewDecision.RETURN, "Return"),
            (AccountingReviewDecision.REJECT, "Reject"),
            (AccountingReviewDecision.RESOLVE, "Resolve"),
        ]
    )
    comment = forms.CharField(required=False, widget=forms.Textarea)


class AccountingReviewFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Keyword",
        widget=forms.TextInput(attrs={"placeholder": "Search keyword...", "aria-label": "Keyword search"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses")] + list(AccountingReviewItem._meta.get_field("status").choices),
        widget=forms.Select(attrs={"aria-label": "Status"}),
    )
    reason = forms.ChoiceField(
        required=False,
        choices=[("", "All Reasons")] + list(AccountingReviewItem._meta.get_field("reason").choices),
        widget=forms.Select(attrs={"aria-label": "Reason"}),
    )
    source_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Sources")] + list(AccountingReviewItem._meta.get_field("source_type").choices),
        widget=forms.Select(attrs={"aria-label": "Source type"}),
    )
    policy_action = forms.ChoiceField(
        required=False,
        choices=[("", "All Policy Actions")] + list(OverBudgetAction.choices),
        widget=forms.Select(attrs={"aria-label": "Policy action"}),
    )
    requester = forms.CharField(
        required=False,
        label="Requester",
        widget=forms.TextInput(attrs={"placeholder": "Requester username or name...", "aria-label": "Requester"}),
    )
    department = forms.CharField(
        required=False,
        label="Department",
        widget=forms.TextInput(attrs={"placeholder": "Department...", "aria-label": "Department"}),
    )
    project = forms.CharField(
        required=False,
        label="Project",
        widget=forms.TextInput(attrs={"placeholder": "Project...", "aria-label": "Project"}),
    )
    min_age_days = forms.IntegerField(
        required=False,
        min_value=0,
        label="Minimum Aging Days",
        widget=forms.NumberInput(attrs={"placeholder": "Min aging days...", "aria-label": "Minimum aging days"}),
    )
