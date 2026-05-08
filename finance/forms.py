from django import forms

from projects.models import Project
from purchase.models import PurchaseRequest
from travel.models import TravelRequest

from .models import (
    AccountingReviewDecision,
    AccountingReviewItem,
    CardTransaction,
    CardTransactionAllocation,
    OverBudgetPolicy,
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
    q = forms.CharField(required=False, label="Keyword")
    status = forms.ChoiceField(required=False, choices=[("", "All Statuses")] + list(AccountingReviewItem._meta.get_field("status").choices))
    reason = forms.ChoiceField(required=False, choices=[("", "All Reasons")] + list(AccountingReviewItem._meta.get_field("reason").choices))
