from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q

from projects.access import get_usable_projects_queryset_for_user, user_can_use_project_for_request
from projects.models import Project
from .models import (
    TravelRequest,
    TravelItinerary,
    TravelEstimatedExpenseLine,
    TravelLocationMode,
    get_location_mode_for_expense_type,
    TravelRequestAttachment,
    TravelActualExpenseLine,
    TravelActualReviewStatus,
)
from common.choices import CurrencyCode

class TravelRequestForm(forms.ModelForm):
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
            raise forms.ValidationError("Only open projects can be linked to travel requests.")

        if not user_can_use_project_for_request(self.user, project):
            raise forms.ValidationError("You are not a member of this project.")

        return project

    class Meta:
        model = TravelRequest
        fields = [
            "purpose",
            "requester",
            "request_department",
            "project",
            "request_date",
            "start_date",
            "end_date",
            "origin_city",
            "destination_city",
            "currency",
            "notes",
        ]
        widgets = {
            "request_date": forms.DateInput(attrs={"type": "date"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

class TravelItineraryForm(forms.ModelForm):
    class Meta:
        model = TravelItinerary
        fields = [
            "line_no",
            "trip_date",
            "from_city",
            "to_city",
            "transport_type",
            "departure_time",
            "arrival_time",
            "notes",
        ]
        widgets = {
            "trip_date": forms.DateInput(attrs={"type": "date"}),
            "departure_time": forms.TimeInput(attrs={"type": "time"}),
            "arrival_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["line_no"].required = False
        self.fields["line_no"].widget.attrs["readonly"] = "readonly"

        for field_name in [
            "trip_date",
            "from_city",
            "to_city",
            "transport_type",
            "departure_time",
            "arrival_time",
            "notes",
        ]:
            self.fields[field_name].required = False

        if not self.instance.pk and not self.is_bound:
            self.initial["line_no"] = ""

    def has_meaningful_content(self):
        if not hasattr(self, "cleaned_data"):
            return False

        return any(
            [
                self.cleaned_data.get("trip_date"),
                self.cleaned_data.get("from_city"),
                self.cleaned_data.get("to_city"),
                self.cleaned_data.get("transport_type"),
                self.cleaned_data.get("departure_time"),
                self.cleaned_data.get("arrival_time"),
                self.cleaned_data.get("notes"),
            ]
        )


class BaseTravelItineraryFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        next_line_no = 1

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            has_content = form.has_meaningful_content()

            if form.instance.pk and not has_content:
                form.add_error(None, "Use Delete Row to remove an existing itinerary line.")
                continue

            if not form.instance.pk and not has_content:
                continue

            if not form.cleaned_data.get("trip_date"):
                form.add_error("trip_date", "Trip Date is required.")

            if not form.cleaned_data.get("from_city"):
                form.add_error("from_city", "From City is required.")

            if not form.cleaned_data.get("to_city"):
                form.add_error("to_city", "To City is required.")

            if not form.cleaned_data.get("transport_type"):
                form.add_error("transport_type", "Transport Type is required.")

            form.cleaned_data["line_no"] = next_line_no
            next_line_no += 1

    def save(self, commit=True):
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

            if not form.has_meaningful_content():
                continue

            obj = form.save(commit=False)
            obj.travel_request = self.instance
            obj.line_no = next_line_no
            next_line_no += 1

            if commit:
                obj.save()

            saved_objects.append(obj)

        return saved_objects


class TravelEstimatedExpenseLineForm(forms.ModelForm):
    class Meta:
        model = TravelEstimatedExpenseLine
        fields = [
            "line_no",
            "expense_type",
            "expense_date",
            "estimated_amount",
            "currency",
            "from_location",
            "to_location",
            "departure_dt",
            "arrival_dt",
            "expense_location",
            "checkin_date",
            "checkout_date",
            "itinerary_line_no",
            "exception_reason",
            "notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "departure_dt": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "arrival_dt": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "checkin_date": forms.DateInput(attrs={"type": "date"}),
            "checkout_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["line_no"].required = False
        self.fields["line_no"].widget.attrs["readonly"] = "readonly"

        for field_name in [
            "expense_type",
            "expense_date",
            "estimated_amount",
            "currency",
            "from_location",
            "to_location",
            "departure_dt",
            "arrival_dt",
            "expense_location",
            "checkin_date",
            "checkout_date",
            "itinerary_line_no",
            "exception_reason",
            "notes",
        ]:
            self.fields[field_name].required = False

        if not self.instance.pk and not self.is_bound:
            self.initial["line_no"] = ""
            self.initial["estimated_amount"] = ""
            self.initial["currency"] = ""

    def has_meaningful_content(self):
        if not hasattr(self, "cleaned_data"):
            return False

        return any(
            [
                self.cleaned_data.get("expense_type"),
                self.cleaned_data.get("expense_date"),
                self.cleaned_data.get("estimated_amount") not in [None, ""],
                self.cleaned_data.get("currency"),
                self.cleaned_data.get("from_location"),
                self.cleaned_data.get("to_location"),
                self.cleaned_data.get("departure_dt"),
                self.cleaned_data.get("arrival_dt"),
                self.cleaned_data.get("expense_location"),
                self.cleaned_data.get("checkin_date"),
                self.cleaned_data.get("checkout_date"),
                self.cleaned_data.get("itinerary_line_no"),
                self.cleaned_data.get("exception_reason"),
                self.cleaned_data.get("notes"),
            ]
        )

class BaseTravelEstimatedExpenseFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        next_line_no = 1

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            has_content = form.has_meaningful_content()

            if form.instance.pk and not has_content:
                form.add_error(None, "Use Delete Row to remove an existing expense line.")
                continue

            if not form.instance.pk and not has_content:
                continue

            if not form.cleaned_data.get("expense_type"):
                form.add_error("expense_type", "Expense Type is required.")

            if not form.cleaned_data.get("expense_date"):
                form.add_error("expense_date", "Expense Date is required.")

            if form.cleaned_data.get("estimated_amount") in [None, ""]:
                form.add_error("estimated_amount", "Estimated Amount is required.")

            expense_type = form.cleaned_data.get("expense_type")
            derived_mode = get_location_mode_for_expense_type(expense_type)

            if not derived_mode:
                form.add_error("expense_type", "Unsupported expense type.")
            else:
                if derived_mode == TravelLocationMode.TRANSIT:
                    if not form.cleaned_data.get("from_location"):
                        form.add_error("from_location", "From Location is required for transit expense.")
                    if not form.cleaned_data.get("to_location"):
                        form.add_error("to_location", "To Location is required for transit expense.")

                elif derived_mode == TravelLocationMode.STAY:
                    if not form.cleaned_data.get("expense_location"):
                        form.add_error("expense_location", "Expense Location is required for stay expense.")
                    if not form.cleaned_data.get("checkin_date"):
                        form.add_error("checkin_date", "Check-in Date is required for stay expense.")
                    if not form.cleaned_data.get("checkout_date"):
                        form.add_error("checkout_date", "Checkout Date is required for stay expense.")

                elif derived_mode == TravelLocationMode.LOCAL:
                    if not form.cleaned_data.get("expense_location"):
                        form.add_error("expense_location", "Expense Location is required for local expense.")

            form.cleaned_data["line_no"] = next_line_no
            next_line_no += 1

    def save(self, commit=True):
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

            if not form.has_meaningful_content():
                continue

            obj = form.save(commit=False)
            obj.travel_request = self.instance
            obj.line_no = next_line_no
            next_line_no += 1

            if not obj.currency:
                obj.currency = self.instance.currency

            if commit:
                obj.save()

            saved_objects.append(obj)

        return saved_objects


TravelItineraryCreateFormSet = inlineformset_factory(
    TravelRequest,
    TravelItinerary,
    form=TravelItineraryForm,
    formset=BaseTravelItineraryFormSet,
    fields=[
        "line_no",
        "trip_date",
        "from_city",
        "to_city",
        "transport_type",
        "departure_time",
        "arrival_time",
        "notes",
    ],
    extra=1,
    can_delete=True,
)

TravelItineraryEditFormSet = inlineformset_factory(
    TravelRequest,
    TravelItinerary,
    form=TravelItineraryForm,
    formset=BaseTravelItineraryFormSet,
    fields=[
        "line_no",
        "trip_date",
        "from_city",
        "to_city",
        "transport_type",
        "departure_time",
        "arrival_time",
        "notes",
    ],
    extra=0,
    can_delete=True,
)

TravelEstimatedExpenseCreateFormSet = inlineformset_factory(
    TravelRequest,
    TravelEstimatedExpenseLine,
    form=TravelEstimatedExpenseLineForm,
    formset=BaseTravelEstimatedExpenseFormSet,
    fields=[
        "line_no",
        "expense_type",
        "expense_date",
        "estimated_amount",
        "currency",
        "from_location",
        "to_location",
        "departure_dt",
        "arrival_dt",
        "expense_location",
        "checkin_date",
        "checkout_date",
        "itinerary_line_no",
        "exception_reason",
        "notes",
    ],
    extra=1,
    can_delete=True,
)

TravelEstimatedExpenseEditFormSet = inlineformset_factory(
    TravelRequest,
    TravelEstimatedExpenseLine,
    form=TravelEstimatedExpenseLineForm,
    formset=BaseTravelEstimatedExpenseFormSet,
    fields=[
        "line_no",
        "expense_type",
        "expense_date",
        "estimated_amount",
        "currency",
        "from_location",
        "to_location",
        "departure_dt",
        "arrival_dt",
        "expense_location",
        "checkin_date",
        "checkout_date",
        "itinerary_line_no",
        "exception_reason",
        "notes",
    ],
    extra=0,
    can_delete=True,
)

class TravelRequestAttachmentForm(forms.ModelForm):
    class Meta:
        model = TravelRequestAttachment
        fields = [
            "document_type",
            "title",
            "file",
        ]

class TravelActualExpenseForm(forms.ModelForm):
    class Meta:
        model = TravelActualExpenseLine
        fields = [
            "expense_type",
            "expense_date",
            "actual_amount",
            "currency",
            "estimated_expense_line",
            "vendor_name",
            "reference_no",
            "expense_location",
            "notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, travel_request=None, **kwargs):
        self.travel_request = travel_request
        super().__init__(*args, **kwargs)

        self.fields["estimated_expense_line"].required = False

        if travel_request:
            self.fields["estimated_expense_line"].queryset = (
                TravelEstimatedExpenseLine.objects.filter(
                    travel_request_id=travel_request.id
                ).order_by("line_no")
            )
            self.fields["currency"].initial = travel_request.currency
        else:
            self.fields["estimated_expense_line"].queryset = (
                self.fields["estimated_expense_line"].queryset.none()
            )

    def clean(self):
        cleaned_data = super().clean()

        estimated_expense_line = cleaned_data.get("estimated_expense_line")
        actual_amount = cleaned_data.get("actual_amount")
        currency = cleaned_data.get("currency")

        if actual_amount is not None and actual_amount <= 0:
            self.add_error("actual_amount", "Actual amount must be greater than 0.")

        if estimated_expense_line and self.travel_request:
            if estimated_expense_line.travel_request_id != self.travel_request.id:
                self.add_error(
                    "estimated_expense_line",
                    "Estimated expense line must belong to the same travel request.",
                )

        if not currency and self.travel_request:
            cleaned_data["currency"] = self.travel_request.currency

        return cleaned_data

class TravelActualReviewForm(forms.Form):
    review_status = forms.ChoiceField(
        choices=[
            (TravelActualReviewStatus.APPROVED_TO_PROCEED, "Approved to Proceed"),
            (TravelActualReviewStatus.REJECTED, "Rejected"),
        ]
    )
    review_comment = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Review Comment",
    )

class TravelActualReviewAttachmentForm(forms.ModelForm):
    class Meta:
        model = TravelRequestAttachment
        fields = [
            "title",
            "file",
        ]