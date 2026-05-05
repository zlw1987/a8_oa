from django import forms
from django.contrib.auth import get_user_model

from accounts.models import Department
from projects.models import Project
from travel.models import TravelRequestStatus


User = get_user_model()


class TravelRequestListFilterForm(forms.Form):
    keyword = forms.CharField(required=False, label="Keyword")
    status = forms.ChoiceField(required=False, label="Status")
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        label="Department",
    )
    requester = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Requester",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        label="Project",
    )
    request_date_from = forms.DateField(
        required=False,
        label="Request Date From",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    request_date_to = forms.DateField(
        required=False,
        label="Request Date To",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, visible_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        status_choices = [("", "All")] + list(TravelRequestStatus.choices)
        self.fields["status"].choices = status_choices

        if visible_queryset is not None:
            department_ids = (
                visible_queryset.exclude(request_department__isnull=True)
                .values_list("request_department_id", flat=True)
                .distinct()
            )
            requester_ids = (
                visible_queryset.exclude(requester__isnull=True)
                .values_list("requester_id", flat=True)
                .distinct()
            )
            project_ids = (
                visible_queryset.exclude(project__isnull=True)
                .values_list("project_id", flat=True)
                .distinct()
            )

            self.fields["department"].queryset = Department.objects.filter(
                id__in=department_ids
            ).order_by("dept_code", "id")
            self.fields["requester"].queryset = User.objects.filter(
                id__in=requester_ids
            ).order_by("username", "id")
            self.fields["project"].queryset = Project.objects.filter(
                id__in=project_ids
            ).order_by("project_code", "id")
        else:
            self.fields["department"].queryset = Department.objects.none()
            self.fields["requester"].queryset = User.objects.none()
            self.fields["project"].queryset = Project.objects.none()