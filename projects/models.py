from django.db import models
from django.conf import settings
from common.choices import BudgetEntryType, RequestType

from decimal import Decimal
from django.db.models import Sum



class Project(models.Model):
    project_code = models.CharField(max_length=30, unique=True)
    project_name = models.CharField(max_length=150)
    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_projects",
    )
    owning_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="USD")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_PROJ"
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["project_code"]

    def __str__(self):
        return f"{self.project_code} - {self.project_name}"

    def get_reserved_amount(self):
        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        adjust_total = (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.ADJUST,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        return reserve_total - release_total + adjust_total

    def get_consumed_amount(self):
        return (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.CONSUME,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    def get_available_amount(self):
        return self.budget_amount - self.get_reserved_amount() - self.get_consumed_amount()

class ProjectBudgetEntry(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="budget_entries",
    )
    entry_type = models.CharField(max_length=20, choices=BudgetEntryType)
    source_type = models.CharField(max_length=20, choices=RequestType)
    source_id = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_budget_entries",
    )

    class Meta:
        db_table = "PS_A8_PROJ_BUD"
        verbose_name = "Project Budget Entry"
        verbose_name_plural = "Project Budget Entries"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.project.project_code} / {self.entry_type} / {self.amount}"