from django.db.models import Q
from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from projects.access import get_usable_projects_queryset_for_user, user_can_use_project_for_request
from projects.models import Project

from .models import (
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseRequestAttachment,
    PurchaseActualSpend,
    PurchaseActualReviewStatus, 
    PurchaseRequestAttachment,
)
class PurchaseRequestForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated and not user.is_superuser:
            self.fields["requester"].queryset = self.fields["requester"].queryset.filter(pk=user.pk)
            self.fields["requester"].initial = user
            self.fields["requester"].disabled = True

            department_ids = user.department_links.filter(is_active=True).values_list("department_id", flat=True)
            self.fields["request_department"].queryset = self.fields["request_department"].queryset.filter(
                id__in=department_ids
            )

            if user.primary_department_id and not self.instance.pk:
                self.fields["request_department"].initial = user.primary_department

        usable_projects = get_usable_projects_queryset_for_user(user) if user else Project.objects.none()
        usable_project_ids = usable_projects.values_list("pk", flat=True)

        if self.instance.pk and self.instance.project_id:
            self.fields["project"].queryset = Project.objects.filter(
                Q(pk__in=usable_project_ids) | Q(pk=self.instance.project_id)
            ).distinct()
        else:
            self.fields["project"].queryset = Project.objects.filter(
                pk__in=usable_project_ids
            )

    def clean_project(self):
        project = self.cleaned_data.get("project")

        if not project:
            return project

        if not self.user or not self.user.is_authenticated:
            raise forms.ValidationError("You must be logged in to use a project.")

        if not project.is_open():
            raise forms.ValidationError("Only open projects can be linked to purchase requests.")

        if not user_can_use_project_for_request(self.user, project):
            raise forms.ValidationError("You are not a member of this project.")

        return project

    class Meta:
        model = PurchaseRequest
        fields = [
            "title",
            "requester",
            "request_department",
            "project",
            "request_date",
            "needed_by_date",
            "currency",
            "justification",
            "vendor_suggestion",
            "delivery_location",
            "notes",
        ]
        widgets = {
            "request_date": forms.DateInput(attrs={"type": "date"}),
            "needed_by_date": forms.DateInput(attrs={"type": "date"}),
        }

class PurchaseRequestLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequestLine
        fields = [
            "line_no",
            "item_name",
            "item_description",
            "quantity",
            "uom",
            "unit_price",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # line_no is system-controlled. User can see it, but should not edit it.
        self.fields["line_no"].required = False
        self.fields["line_no"].widget.attrs["readonly"] = "readonly"

        # Let blank extra rows stay truly blank, so they won't block save.
        self.fields["item_name"].required = False
        self.fields["item_description"].required = False
        self.fields["quantity"].required = False
        self.fields["uom"].required = False
        self.fields["unit_price"].required = False
        self.fields["notes"].required = False

        if not self.instance.pk and not self.is_bound:
            self.initial["line_no"] = ""
            self.initial["quantity"] = ""
            self.initial["uom"] = ""
            self.initial["unit_price"] = ""

    def has_meaningful_content(self):
        if not hasattr(self, "cleaned_data"):
            return False

        return any(
            [
                self.cleaned_data.get("item_name"),
                self.cleaned_data.get("item_description"),
                self.cleaned_data.get("quantity") not in [None, ""],
                self.cleaned_data.get("uom"),
                self.cleaned_data.get("unit_price") not in [None, ""],
                self.cleaned_data.get("notes"),
            ]
        )


class BasePurchaseRequestLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        next_line_no = 1

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            has_content = form.has_meaningful_content()

            # Existing line cleared out without using Delete button
            if form.instance.pk and not has_content:
                form.add_error(None, "Use Delete Row to remove an existing line.")
                continue

            # Extra blank row should be ignored
            if not form.instance.pk and not has_content:
                continue

            if not form.cleaned_data.get("item_name"):
                form.add_error("item_name", "Item Name is required.")

            if form.cleaned_data.get("quantity") in [None, ""]:
                form.add_error("quantity", "Quantity is required.")

            if not form.cleaned_data.get("uom"):
                form.add_error("uom", "UOM is required.")

            if form.cleaned_data.get("unit_price") in [None, ""]:
                form.add_error("unit_price", "Unit Price is required.")

            form.cleaned_data["line_no"] = next_line_no
            next_line_no += 1

    def save(self, commit=True):
        # Delete selected existing rows first, so resequencing will not hit unique conflicts.
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE") and form.instance.pk:
                form.instance.delete()

        saved_objects = []
        next_line_no = 1

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            has_content = form.has_meaningful_content()
            if not has_content:
                continue

            obj = form.save(commit=False)
            obj.request = self.instance
            obj.line_no = next_line_no
            next_line_no += 1

            if commit:
                obj.save()

            saved_objects.append(obj)

        return saved_objects


PurchaseRequestLineCreateFormSet = inlineformset_factory(
    PurchaseRequest,
    PurchaseRequestLine,
    form=PurchaseRequestLineForm,
    formset=BasePurchaseRequestLineFormSet,
    fields=[
        "line_no",
        "item_name",
        "item_description",
        "quantity",
        "uom",
        "unit_price",
        "notes",
    ],
    extra=3,
    can_delete=True,
)


PurchaseRequestLineEditFormSet = inlineformset_factory(
    PurchaseRequest,
    PurchaseRequestLine,
    form=PurchaseRequestLineForm,
    formset=BasePurchaseRequestLineFormSet,
    fields=[
        "line_no",
        "item_name",
        "item_description",
        "quantity",
        "uom",
        "unit_price",
        "notes",
    ],
    extra=0,
    can_delete=True,
)

class PurchaseRequestAttachmentForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequestAttachment
        fields = [
            "document_type",
            "title",
            "file",
        ]

class PurchaseActualSpendForm(forms.ModelForm):
    class Meta:
        model = PurchaseActualSpend
        fields = [
            "spend_date",
            "amount",
            "vendor_name",
            "reference_no",
            "notes",
        ]
        widgets = {
            "spend_date": forms.DateInput(attrs={"type": "date"}),
        }

class PurchaseActualReviewForm(forms.Form):
    review_status = forms.ChoiceField(
        choices=[
            (PurchaseActualReviewStatus.APPROVED_TO_PROCEED, "Approved to Proceed"),
            (PurchaseActualReviewStatus.REJECTED, "Rejected"),
        ]
    )
    review_comment = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Review Comment",
    )

class PurchaseActualReviewAttachmentForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequestAttachment
        fields = [
            "title",
            "file",
        ]