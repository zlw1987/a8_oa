from django.contrib import admin

from .models import BudgetAdjustmentRequest, DepartmentGeneralProject, Project, ProjectBudgetEntry


class ProjectBudgetEntryInline(admin.TabularInline):
    model = ProjectBudgetEntry
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_code",
        "project_name",
        "project_manager",
        "owning_department",
        "project_type",
        "budget_approval_status",
        "budget_amount",
        "currency",
        "is_active",
    )
    search_fields = (
        "project_code",
        "project_name",
        "project_manager__username",
        "project_manager__display_name",
        "owning_department__dept_code",
        "owning_department__dept_name",
    )
    list_filter = (
        "is_active",
        "project_type",
        "budget_approval_status",
        "currency",
        "owning_department",
    )
    inlines = [ProjectBudgetEntryInline]


@admin.register(ProjectBudgetEntry)
class ProjectBudgetEntryAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "entry_type",
        "source_type",
        "source_id",
        "amount",
        "created_by",
        "created_at",
    )
    search_fields = (
        "project__project_code",
        "project__project_name",
        "notes",
    )
    list_filter = (
        "entry_type",
        "source_type",
        "project",
    )


@admin.register(BudgetAdjustmentRequest)
class BudgetAdjustmentRequestAdmin(admin.ModelAdmin):
    list_display = ("project", "amount", "currency", "status", "requested_by", "submitted_at", "approved_by")
    search_fields = ("project__project_code", "project__project_name", "reason")
    list_filter = ("status", "currency", "project")


@admin.register(DepartmentGeneralProject)
class DepartmentGeneralProjectAdmin(admin.ModelAdmin):
    list_display = ("department", "fiscal_year", "project", "budget_amount", "is_active")
    search_fields = ("department__dept_code", "department__dept_name", "project__project_code", "project__project_name")
    list_filter = ("fiscal_year", "is_active", "department")
