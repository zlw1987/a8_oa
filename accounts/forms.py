from django import forms

from .models import Department, UserDepartment


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = [
            "dept_code",
            "dept_name",
            "dept_type",
            "cost_center",
            "manager",
            "parent_department",
            "is_active",
            "sort_order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["parent_department"].queryset = Department.objects.order_by(
            "sort_order",
            "dept_code",
        )

        if self.instance and self.instance.pk:
            self.fields["parent_department"].queryset = (
                Department.objects.exclude(pk=self.instance.pk).order_by("sort_order", "dept_code")
            )

    def clean_dept_code(self):
        value = (self.cleaned_data.get("dept_code") or "").strip().upper()
        if not value:
            raise forms.ValidationError("Department Code is required.")
        return value

    def clean_dept_name(self):
        value = (self.cleaned_data.get("dept_name") or "").strip()
        if not value:
            raise forms.ValidationError("Department Name is required.")
        return value

    def clean(self):
        cleaned_data = super().clean()

        parent_department = cleaned_data.get("parent_department")
        instance = self.instance

        if instance and instance.pk and parent_department and parent_department.pk == instance.pk:
            self.add_error("parent_department", "Department cannot be its own parent.")

        while instance and instance.pk and parent_department:
            if parent_department.parent_department_id == instance.pk:
                self.add_error(
                    "parent_department",
                    "Department cannot use one of its child departments as parent.",
                )
                break
            parent_department = parent_department.parent_department

        return cleaned_data


class UserDepartmentForm(forms.ModelForm):
    class Meta:
        model = UserDepartment
        fields = [
            "user",
            "dept_job_title",
            "can_approve",
            "is_active",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, department=None, **kwargs):
        self.department = department
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["user"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End Date cannot be earlier than Start Date.")

        user = cleaned_data.get("user")
        if self.department is not None and user and not (self.instance and self.instance.pk):
            if UserDepartment.objects.filter(user=user, department=self.department).exists():
                self.add_error("user", "This user is already linked to this department.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.department is not None:
            instance.department = self.department
        if commit:
            instance.save()
        return instance
