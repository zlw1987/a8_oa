from django import forms

from .models import Department


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
