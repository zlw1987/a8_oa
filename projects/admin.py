from django.contrib import admin

from .models import Project, ProjectBudgetEntry


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