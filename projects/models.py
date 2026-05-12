from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone

from common.choices import BudgetEntryType, RequestType, CurrencyCode, ApproverType, DepartmentType, ApprovalTaskStatus
from common.currency import COMPANY_BASE_CURRENCY

from decimal import Decimal

class ProjectStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"

class ProjectType(models.TextChoices):
    INTERNAL = "INTERNAL", "Internal Project"
    TRADE_SHOW = "TRADE_SHOW", "Trade Show"
    DEPARTMENT_GENERAL = "DEPARTMENT_GENERAL", "Department General Budget"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE", "Customer Service"
    SALES_ORDER = "SALES_ORDER", "Sales Order"

class ProjectBudgetApprovalStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    NOT_REQUIRED = "NOT_REQUIRED", "Not Required"


class BudgetAdjustmentRequestStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    POSTED = "POSTED", "Posted"
    CANCELLED = "CANCELLED", "Cancelled"

class ProjectExternalOrderType(models.TextChoices):
    NONE = "", "-"
    SALES_ORDER = "SALES_ORDER", "Sales Order"
    SERVICE_ORDER = "SERVICE_ORDER", "Service Order"
    CUSTOMER_VISIT = "CUSTOMER_VISIT", "Customer Visit"

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
    project_type = models.CharField(
        max_length=30,
        choices=ProjectType,
        default=ProjectType.INTERNAL,
    )
    budget_approval_status = models.CharField(
        max_length=30,
        choices=ProjectBudgetApprovalStatus,
        default=ProjectBudgetApprovalStatus.APPROVED,
    )
    matched_rule = models.ForeignKey(
        "approvals.ApprovalRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_requests",
    )
    approval_tasks = GenericRelation(
        "approvals.ApprovalTask",
        content_type_field="request_content_type",
        object_id_field="request_object_id",
        related_query_name="project_request",
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
    budget_period_start = models.DateField(null=True, blank=True)
    budget_period_end = models.DateField(null=True, blank=True)
    external_order_type = models.CharField(
        max_length=30,
        choices=ProjectExternalOrderType,
        blank=True,
        default="",
    )
    external_order_no = models.CharField(max_length=50, blank=True, default="")
    customer_name = models.CharField(max_length=150, blank=True, default="")
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
        return (
            self.status == ProjectStatus.OPEN
            and self.is_active
            and self.budget_approval_status in [
                ProjectBudgetApprovalStatus.APPROVED,
                ProjectBudgetApprovalStatus.NOT_REQUIRED,
            ]
        )

    @property
    def requester(self):
        return self.created_by or self.project_manager

    @property
    def request_department(self):
        return self.owning_department

    @property
    def estimated_total(self):
        return self.budget_amount

    def get_current_task(self):
        return (
            self.approval_tasks.filter(
                status__in=[ApprovalTaskStatus.POOL, ApprovalTaskStatus.PENDING]
            )
            .order_by("step_no", "id")
            .first()
        )

    def get_current_step_name(self):
        current_task = self.get_current_task()
        return current_task.step_name if current_task else "-"

    def get_current_approver(self):
        current_task = self.get_current_task()
        if not current_task:
            return "-"
        if current_task.status == ApprovalTaskStatus.POOL:
            return "Approval Pool"
        if current_task.assigned_user:
            return str(current_task.assigned_user)
        return "-"

    def get_approval_progress_text(self):
        total_steps = self.approval_tasks.count()
        if total_steps == 0:
            return "0 / 0"
        completed_steps = self.approval_tasks.filter(status=ApprovalTaskStatus.APPROVED).count()
        return f"{completed_steps} / {total_steps}"

    def resolve_fixed_step_assignee(self, step):
        if step.approver_type == ApproverType.SPECIFIC_USER:
            return step.approver_user
        if step.approver_type == ApproverType.DEPARTMENT_MANAGER:
            return self.owning_department.manager
        if step.approver_type == ApproverType.REQUESTER_MANAGER:
            requester = self.requester
            if requester and requester.primary_department_id:
                return requester.primary_department.manager
        return None

    def _dedupe_users(self, users):
        unique_users = {}
        for user in users:
            if user and user.id not in unique_users:
                unique_users[user.id] = user
        return list(unique_users.values())

    def resolve_step_candidates(self, step):
        from accounts.models import UserDepartment

        users = []
        if step.approver_type == ApproverType.GLOBAL_APPROVER:
            from django.contrib.auth import get_user_model
            users = list(get_user_model().objects.filter(can_approve_all_departments=True, is_active=True).order_by("id"))
        elif step.approver_type == ApproverType.DEPARTMENT_APPROVER:
            target_department = step.approver_department or self.owning_department
            links = UserDepartment.objects.filter(
                department=target_department,
                can_approve=True,
                is_active=True,
            ).select_related("user").order_by("user__id")
            users = [link.user for link in links]
        elif step.approver_type in [ApproverType.FINANCE, ApproverType.PURCHASING, ApproverType.HR]:
            dept_type_map = {
                ApproverType.FINANCE: DepartmentType.FIN,
                ApproverType.PURCHASING: DepartmentType.PUR,
                ApproverType.HR: DepartmentType.HR,
            }
            links = UserDepartment.objects.filter(
                department__dept_type=dept_type_map[step.approver_type],
                can_approve=True,
                is_active=True,
            ).select_related("user").order_by("user__id")
            users = [link.user for link in links]
        return self._dedupe_users(users)

    @transaction.atomic
    def submit_budget_for_approval(self, acting_user=None):
        if self.budget_approval_status not in [
            ProjectBudgetApprovalStatus.DRAFT,
            ProjectBudgetApprovalStatus.RETURNED,
            ProjectBudgetApprovalStatus.REJECTED,
        ]:
            raise ValidationError("Only Draft, Returned, or Rejected project budgets can be submitted.")
        if self.budget_amount <= 0:
            raise ValidationError("Project budget must be greater than 0 before approval.")

        from approvals.services import create_approval_tasks_for_request, resolve_approval_rule_for_request

        matched_rule = resolve_approval_rule_for_request(self)
        if not matched_rule:
            raise ValidationError("No active project approval rule matched this project.")

        self.matched_rule = matched_rule
        self.budget_approval_status = ProjectBudgetApprovalStatus.PENDING_APPROVAL
        self.status = ProjectStatus.OPEN
        self.save(update_fields=["matched_rule", "budget_approval_status", "status"])
        create_approval_tasks_for_request(self, matched_rule)

    @transaction.atomic
    def mark_as_approved(self, acting_user=None, comment=""):
        self.budget_approval_status = ProjectBudgetApprovalStatus.APPROVED
        self.status = ProjectStatus.OPEN
        self.save(update_fields=["budget_approval_status", "status"])

    @transaction.atomic
    def mark_as_rejected(self, acting_user=None, comment="", exclude_task_id=None):
        self.budget_approval_status = ProjectBudgetApprovalStatus.REJECTED
        self.save(update_fields=["budget_approval_status"])
        self._cancel_open_approval_tasks(exclude_task_id, "Project budget rejected.")

    @transaction.atomic
    def mark_as_returned(self, acting_user=None, comment="", exclude_task_id=None):
        self.budget_approval_status = ProjectBudgetApprovalStatus.RETURNED
        self.save(update_fields=["budget_approval_status"])
        self._cancel_open_approval_tasks(exclude_task_id, "Project budget returned.")

    def _cancel_open_approval_tasks(self, exclude_task_id=None, comment=""):
        for task in self.approval_tasks.exclude(id=exclude_task_id).filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ):
            task.cancel_by_system(comment=comment)

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


class DepartmentGeneralProject(models.Model):
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.CASCADE,
        related_name="general_project_setups",
    )
    fiscal_year = models.PositiveIntegerField()
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="department_general_setups",
    )
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_department_general_project_setups",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "PS_A8_DEPT_GEN_PROJ"
        verbose_name = "Department General Project"
        verbose_name_plural = "Department General Projects"
        ordering = ["-fiscal_year", "department__dept_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "fiscal_year"],
                condition=models.Q(is_active=True),
                name="uq_active_dept_general_project_year",
            ),
        ]

    def __str__(self):
        return f"{self.department} / {self.fiscal_year} / {self.project}"

    def clean(self):
        super().clean()
        if self.project_id and self.department_id:
            if self.project.owning_department_id != self.department_id:
                raise ValidationError("General project must belong to the selected department.")
            if self.project.project_type != ProjectType.DEPARTMENT_GENERAL:
                raise ValidationError("General project must use Department General Budget project type.")
        if self.budget_amount < Decimal("0.00"):
            raise ValidationError("Budget amount cannot be negative.")

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
    currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    source_transaction_currency = models.CharField(max_length=10, choices=CurrencyCode, blank=True, default="")
    source_transaction_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source_exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    source_exchange_rate_source = models.CharField(max_length=30, blank=True, default="")
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


class BudgetAdjustmentRequest(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="budget_adjustment_requests",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    reason = models.TextField()
    status = models.CharField(
        max_length=30,
        choices=BudgetAdjustmentRequestStatus,
        default=BudgetAdjustmentRequestStatus.SUBMITTED,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_budget_adjustments",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_budget_adjustments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rejected_budget_adjustments",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True, default="")
    posted_entry = models.OneToOneField(
        ProjectBudgetEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjustment_request",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "PS_A8_PROJ_BUD_ADJ_REQ"
        verbose_name = "Budget Adjustment Request"
        verbose_name_plural = "Budget Adjustment Requests"
        ordering = ["-submitted_at", "-id"]

    def __str__(self):
        return f"{self.project.project_code} / {self.amount} / {self.status}"

    def clean(self):
        super().clean()
        if self.amount == Decimal("0.00"):
            raise ValidationError("Adjustment amount cannot be 0.")
        if not self.reason:
            raise ValidationError("Adjustment reason is required.")

    @transaction.atomic
    def approve_and_post(self, *, acting_user, comment=""):
        from common.permissions import can_manage_finance_setup

        if not can_manage_finance_setup(acting_user):
            raise ValidationError("Only finance admins can approve budget adjustments.")
        if self.status not in [
            BudgetAdjustmentRequestStatus.SUBMITTED,
            BudgetAdjustmentRequestStatus.APPROVED,
        ]:
            raise ValidationError("Only submitted budget adjustments can be approved.")
        if self.posted_entry_id:
            raise ValidationError("This budget adjustment has already been posted.")

        entry = ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.ADJUST,
            source_type=RequestType.PROJECT,
            source_id=self.project_id,
            amount=self.amount,
            currency=self.currency,
            notes=f"Approved budget adjustment request #{self.id}: {self.reason[:120]}",
            created_by=acting_user,
        )
        self.status = BudgetAdjustmentRequestStatus.POSTED
        self.approved_by = acting_user
        self.approved_at = timezone.now()
        self.decision_comment = comment or ""
        self.posted_entry = entry
        self.posted_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "approved_by",
                "approved_at",
                "decision_comment",
                "posted_entry",
                "posted_at",
            ]
        )
        entry.source_id = self.id
        entry.save(update_fields=["source_id"])
        return entry

    def reject(self, *, acting_user, comment=""):
        from common.permissions import can_manage_finance_setup

        if not can_manage_finance_setup(acting_user):
            raise ValidationError("Only finance admins can reject budget adjustments.")
        if self.status != BudgetAdjustmentRequestStatus.SUBMITTED:
            raise ValidationError("Only submitted budget adjustments can be rejected.")
        if not comment:
            raise ValidationError("Reject comment is required.")
        self.status = BudgetAdjustmentRequestStatus.REJECTED
        self.rejected_by = acting_user
        self.rejected_at = timezone.now()
        self.decision_comment = comment
        self.save(update_fields=["status", "rejected_by", "rejected_at", "decision_comment"])

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
