from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from common.choices import ApproverType
from .models import ApprovalRule, ApprovalRuleStep


class ApprovalRuleForm(forms.ModelForm):
    class Meta:
        model = ApprovalRule
        fields = [
            "rule_code",
            "rule_name",
            "request_type",
            "department",
            "amount_from",
            "amount_to",
            "requester_level",
            "specific_requester",
            "is_general_fallback",
            "priority",
            "is_active",
        ]

    def clean(self):
        cleaned_data = super().clean()

        amount_from = cleaned_data.get("amount_from")
        amount_to = cleaned_data.get("amount_to")

        if amount_from is not None and amount_to is not None and amount_from > amount_to:
            raise ValidationError("Amount From cannot be greater than Amount To.")

        is_general_fallback = cleaned_data.get("is_general_fallback")
        if is_general_fallback:
            fallback_fields = {
                "department": "General fallback rule cannot be limited to a department.",
                "amount_from": "General fallback rule cannot have Amount From.",
                "amount_to": "General fallback rule cannot have Amount To.",
                "requester_level": "General fallback rule cannot be limited to requester level.",
                "specific_requester": "General fallback rule cannot be limited to a requester.",
            }
            for field_name, message in fallback_fields.items():
                value = cleaned_data.get(field_name)
                if value not in (None, ""):
                    self.add_error(field_name, message)

        return cleaned_data


class ApprovalRuleStepForm(forms.ModelForm):
    class Meta:
        model = ApprovalRuleStep
        fields = [
            "step_no",
            "step_name",
            "approver_type",
            "approver_user",
            "approver_department",
            "approver_level",
            "is_required",
            "allow_self_skip",
            "sla_days",
            "is_active",
        ]

    def clean(self):
        cleaned_data = super().clean()

        approver_type = cleaned_data.get("approver_type")
        approver_user = cleaned_data.get("approver_user")
        approver_department = cleaned_data.get("approver_department")

        if approver_type == ApproverType.SPECIFIC_USER and not approver_user:
            self.add_error("approver_user", "Specific User approver type requires Approver User.")

        if approver_type == ApproverType.DEPARTMENT_APPROVER and not approver_department:
            self.add_error(
                "approver_department",
                "Department Approver type requires Approver Department.",
            )

        if approver_type != ApproverType.SPECIFIC_USER:
            cleaned_data["approver_user"] = None

        if approver_type != ApproverType.DEPARTMENT_APPROVER:
            cleaned_data["approver_department"] = None

        return cleaned_data


class BaseApprovalRuleStepFormSet(BaseInlineFormSet):
    def clean(self):
        

        active_step_nos = []
        seen_step_nos = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            if not form.cleaned_data:
                continue

            step_no = form.cleaned_data.get("step_no")
            step_name = form.cleaned_data.get("step_name")
            is_active = form.cleaned_data.get("is_active")

            if step_no in seen_step_nos:
                raise ValidationError(f"Duplicate Step No found: {step_no}")
            seen_step_nos.add(step_no)

            if is_active:
                if not step_name:
                    raise ValidationError("Active step must have Step Name.")
                active_step_nos.append(step_no)

        if not active_step_nos:
            raise ValidationError("At least one active approval step is required.")

        sorted_step_nos = sorted(active_step_nos)
        expected_step_nos = list(range(1, len(sorted_step_nos) + 1))

        if sorted_step_nos != expected_step_nos:
            raise ValidationError(
                "Active Step No values must be continuous starting from 1."
            )

        super().clean()


ApprovalRuleStepFormSet = inlineformset_factory(
    ApprovalRule,
    ApprovalRuleStep,
    form=ApprovalRuleStepForm,
    formset=BaseApprovalRuleStepFormSet,
    extra=1,
    can_delete=True,
)
