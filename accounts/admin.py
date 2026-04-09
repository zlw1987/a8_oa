from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Department, UserDepartment


@admin.register(User)
class A8UserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Organization and Approval",
            {
                "fields": (
                    "employee_id",
                    "display_name",
                    "job_title",
                    "phone",
                    "approval_level",
                    "primary_department",
                    "can_approve_all_departments",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Organization and Approval",
            {
                "fields": (
                    "employee_id",
                    "display_name",
                    "job_title",
                    "phone",
                    "approval_level",
                    "primary_department",
                    "can_approve_all_departments",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "display_name",
        "job_title",
        "approval_level",
        "primary_department",
        "can_approve_all_departments",
        "is_staff",
        "is_active",
    )

    search_fields = (
        "username",
        "email",
        "display_name",
        "employee_id",
        "job_title",
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "dept_code",
        "dept_name",
        "dept_type",
        "cost_center",
        "manager",
        "parent_department",
        "sort_order",
        "is_active",
    )
    search_fields = (
        "dept_code",
        "dept_name",
        "cost_center",
        "manager__username",
        "manager__display_name",
    )
    list_filter = ("dept_type", "is_active", "parent_department")
    ordering = ("sort_order", "dept_code")


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "department",
        "dept_job_title",
        "can_approve",
        "is_active",
        "start_date",
        "end_date",
    )
    search_fields = (
        "user__username",
        "user__display_name",
        "department__dept_code",
        "department__dept_name",
        "dept_job_title",
    )
    list_filter = ("can_approve", "is_active", "department")