from django.db import models
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from common.choices import BudgetEntryType, RequestType, CurrencyCode

from decimal import Decimal

class ProjectStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"

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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_projects",
    )

    status = models.CharField(
        max_length=20,
        choices=ProjectStatus,
        default=ProjectStatus.OPEN,
    )

    budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(
        max_length=10,
        choices=CurrencyCode.choices,
        default=CurrencyCode.USD,
    )
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

    def is_open(self):
        return self.status == ProjectStatus.OPEN and self.is_active

    def can_user_manage_members(self, user):
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if self.created_by_id == user.id:
            return True

        if self.project_manager_id == user.id:
            return True

        if getattr(self.owning_department, "manager_id", None) == user.id:
            return True

        return False

    def can_user_use_for_request(self, user):
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not self.is_open():
            return False

        return self.members.filter(user=user, is_active=True).exists()

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

        return reserve_total - release_total

    def get_adjustment_amount(self):
        return (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.ADJUST,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    def get_effective_budget_amount(self):
        return self.budget_amount + self.get_adjustment_amount()

    def get_consumed_amount(self):
        return (
            ProjectBudgetEntry.objects.filter(
                project=self,
                entry_type=BudgetEntryType.CONSUME,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    def get_available_amount(self):
        return self.get_effective_budget_amount() - self.get_reserved_amount() - self.get_consumed_amount()

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

class ProjectMember(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_members_added",
    )

    class Meta:
        db_table = "PS_A8_PROJ_MBR"
        verbose_name = "Project Member"
        verbose_name_plural = "Project Members"
        unique_together = [("project", "user")]
        ordering = ["project", "user"]

    def __str__(self):
        return f"{self.project.project_code} / {self.user}"