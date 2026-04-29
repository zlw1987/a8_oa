from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from accounts.models import Department
from .models import Project
from common.choices import CurrencyCode

User = get_user_model()


class ProjectCreateForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "project_code",
            "project_name",
            "project_manager",
            "owning_department",
            "budget_amount",
            "currency",
            "start_date",
            "end_date",
            "status",
            "is_active",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["currency"].choices = CurrencyCode.choices
        self.fields["currency"].widget = forms.Select(choices=CurrencyCode.choices)

        self.fields["project_manager"].required = False
        self.fields["project_manager"].queryset = User.objects.filter(is_active=True).order_by("username", "id")

        if user and not user.is_superuser:
            self.fields["owning_department"].queryset = Department.objects.filter(
                manager=user
            ).order_by("dept_code", "id")
        else:
            self.fields["owning_department"].queryset = Department.objects.all().order_by("dept_code", "id")

    def clean_budget_amount(self):
        amount = self.cleaned_data["budget_amount"]
        if amount < Decimal("0.00"):
            raise forms.ValidationError("Budget amount cannot be negative.")
        return amount

    def clean_owning_department(self):
        department = self.cleaned_data["owning_department"]

        if self.user and not self.user.is_superuser:
            if department.manager_id != self.user.id:
                raise forms.ValidationError("You can only create projects for departments you manage.")

        return department


class ProjectMemberAddForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none())

    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

        existing_ids = []
        if project:
            existing_ids = project.members.filter(is_active=True).values_list("user_id", flat=True)

        self.fields["user"].queryset = User.objects.filter(is_active=True).exclude(
            id__in=existing_ids
        ).order_by("username", "id")


class ProjectBudgetAdjustmentForm(forms.Form):
    amount = forms.DecimalField(max_digits=14, decimal_places=2)
    notes = forms.CharField(max_length=200)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == Decimal("0.00"):
            raise forms.ValidationError("Adjustment amount cannot be 0.")
        return amount