import os
from pathlib import Path
from decimal import Decimal

from django.db import models, transaction
from django.db.models import Sum, Q
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from common.choices import (
    RequestStatus,
    RequestType,
    BudgetEntryType,
    ApprovalTaskStatus,
    PurchaseRequestHistoryActionType,
    ApproverType,
    DepartmentType,
    UnitOfMeasure,
)
from common.approval_constants import POOL_APPROVER_TYPES
from projects.models import ProjectBudgetEntry
from approvals.models import (
    ApprovalRule,
    ApprovalTask,
    ApprovalTaskCandidate,
    ApprovalTaskActionType,
)
from accounts.models import UserDepartment

class PurchaseRequestNumberSequence(models.Model):
    sequence_date = models.DateField(unique=True)
    last_number = models.IntegerField(default=0)

    class Meta:
        db_table = "PS_A8_PR_SEQ"
        verbose_name = "Purchase Request Number Sequence"
        verbose_name_plural = "Purchase Request Number Sequences"

    def __str__(self):
        return f"{self.sequence_date} / {self.last_number}"

class PurchaseRequest(models.Model):

    pr_no = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )
    request_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )
    matched_rule = models.ForeignKey(
        "approvals.ApprovalRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=RequestStatus,
        default=RequestStatus.DRAFT,
    )
    request_date = models.DateField()
    needed_by_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    justification = models.TextField(blank=True, default="")
    vendor_suggestion = models.CharField(max_length=100, blank=True, default="")
    delivery_location = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_PR_HDR"
        verbose_name = "Purchase Request"
        verbose_name_plural = "Purchase Requests"
        ordering = ["-request_date", "pr_no"]

    @classmethod
    def generate_next_pr_no(cls, request_date=None):
        sequence_date = request_date or timezone.localdate()

        with transaction.atomic():
            sequence, _ = PurchaseRequestNumberSequence.objects.select_for_update().get_or_create(
                sequence_date=sequence_date,
                defaults={"last_number": 0},
            )

            sequence.last_number += 1
            sequence.save(update_fields=["last_number"])

            return f"PR{sequence_date.strftime('%Y%m%d')}-{sequence.last_number:04d}"

    def save(self, *args, **kwargs):
        if not self.pr_no:
            effective_date = self.request_date or timezone.localdate()
            self.pr_no = self.generate_next_pr_no(effective_date)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pr_no} - {self.title}"

    def _add_content_audit(
        self,
        action_type,
        changed_by=None,
        field_name="",
        line_no=None,
        old_value="",
        new_value="",
        notes="",
    ):
        PurchaseRequestContentAudit.objects.create(
            purchase_request=self,
            action_type=action_type,
            field_name=field_name or "",
            line_no=line_no,
            old_value="" if old_value is None else str(old_value),
            new_value="" if new_value is None else str(new_value),
            notes=notes or "",
            changed_by=changed_by,
        )
    
    @classmethod
    def get_visible_queryset(cls, user):
        if not getattr(user, "is_authenticated", False):
            return cls.objects.none()

        if getattr(user, "is_superuser", False):
            return cls.objects.all()

        return cls.objects.filter(
            Q(requester=user)
            | Q(approval_tasks__assigned_user=user)
            | Q(
                approval_tasks__candidates__user=user,
                approval_tasks__candidates__is_active=True,
            )
            | Q(approval_tasks__acted_by=user)
        ).distinct()

    def can_user_view(self, user):
        return self.__class__.get_visible_queryset(user).filter(pk=self.pk).exists()

    def can_user_edit(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return self.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]

        return (
            self.requester_id == user.id
            and self.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]
        )

    def can_user_submit(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return self.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]

        return (
            self.requester_id == user.id
            and self.status in [RequestStatus.DRAFT, RequestStatus.RETURNED]
        )

    def can_user_cancel(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return self.status in [
                RequestStatus.SUBMITTED,
                RequestStatus.PENDING,
                RequestStatus.APPROVED,
            ]

        return (
            self.requester_id == user.id
            and self.status in [
                RequestStatus.SUBMITTED,
                RequestStatus.PENDING,
                RequestStatus.APPROVED,
            ]
        )

    def get_current_task(self):
        return (
            self.approval_tasks.filter(
                status__in=[ApprovalTaskStatus.POOL, ApprovalTaskStatus.PENDING]
            )
            .order_by("step_no")
            .first()
        )

    def get_current_step_name(self):
        current_task = self.get_current_task()
        if current_task:
            return current_task.step_name
        return ""

    def get_current_approver(self):
        current_task = self.get_current_task()
        if not current_task:
            return ""

        if current_task.status == "POOL":
            candidate_count = current_task.candidates.filter(is_active=True).count()
            return f"Pool ({candidate_count} candidate(s))"

        if current_task.assigned_user:
            return str(current_task.assigned_user)

        return ""

    def get_approval_progress_text(self):
        total_steps = self.approval_tasks.count()
        if total_steps == 0:
            return "0 / 0"

        completed_steps = self.approval_tasks.filter(status=ApprovalTaskStatus.APPROVED).count()
        return f"{completed_steps} / {total_steps}"

    def _dedupe_users(self, users):
        unique_users = {}
        for user in users:
            if user and user.id not in unique_users:
                unique_users[user.id] = user
        return list(unique_users.values())

    def get_lines_total(self):
        total = self.lines.aggregate(total=Sum("line_amount"))["total"]
        return total or Decimal("0.00")

    def get_project_reserved_amount(self):
        if not self.project_id:
            return Decimal("0.00")
        return self.project.get_reserved_amount()

    def get_project_available_budget(self):
        if not self.project_id:
            return Decimal("0.00")
        return self.project.get_available_amount()    

    def _add_history(
        self,
        action_type,
        from_status=None,
        to_status=None,
        acting_user=None,
        comment="",
    ):
        PurchaseRequestHistory.objects.create(
            purchase_request=self,
            action_type=action_type,
            from_status=from_status,
            to_status=to_status,
            action_by=acting_user,
            comment=comment,
        )

    def resolve_approval_rule(self):
        lines_total = self.get_lines_total()

        rules = ApprovalRule.objects.filter(
            is_active=True,
            request_type=RequestType.PURCHASE,
        ).filter(
            Q(department=self.request_department) | Q(department__isnull=True)
        ).filter(
            Q(amount_from__isnull=True) | Q(amount_from__lte=lines_total)
        ).filter(
            Q(amount_to__isnull=True) | Q(amount_to__gte=lines_total)
        ).filter(
            Q(requester_level="") | Q(requester_level=self.requester.approval_level)
        ).filter(
            Q(specific_requester__isnull=True) | Q(specific_requester=self.requester)
        ).order_by("priority", "rule_code")

        return rules.first()

    def resolve_fixed_step_assignee(self, step):
        if step.approver_type == ApproverType.SPECIFIC_USER:
            return step.approver_user

        if step.approver_type == ApproverType.DEPARTMENT_MANAGER:
            return self.request_department.manager

        if step.approver_type == ApproverType.REQUESTER_MANAGER:
            if self.requester.primary_department_id:
                return self.requester.primary_department.manager
            return None

        return None

    def resolve_step_candidates(self, step):
        users = []

        if step.approver_type == ApproverType.GLOBAL_APPROVER:
            users = list(
                self.requester.__class__.objects.filter(
                    can_approve_all_departments=True,
                    is_active=True,
                ).order_by("id")
            )

        elif step.approver_type == ApproverType.DEPARTMENT_APPROVER:
            target_department = step.approver_department or self.request_department
            links = (
                UserDepartment.objects.filter(
                    department=target_department,
                    can_approve=True,
                    is_active=True,
                )
                .select_related("user")
                .order_by("user__id")
            )
            users = [link.user for link in links]

        elif step.approver_type == ApproverType.FINANCE:
            links = (
                UserDepartment.objects.filter(
                    department__dept_type=DepartmentType.FIN,
                    can_approve=True,
                    is_active=True,
                )
                .select_related("user")
                .order_by("user__id")
            )
            users = [link.user for link in links]

        elif step.approver_type == ApproverType.PURCHASING:
            links = (
                UserDepartment.objects.filter(
                    department__dept_type=DepartmentType.PUR,
                    can_approve=True,
                    is_active=True,
                )
                .select_related("user")
                .order_by("user__id")
            )
            users = [link.user for link in links]

        elif step.approver_type == ApproverType.HR:
            links = (
                UserDepartment.objects.filter(
                    department__dept_type=DepartmentType.HR,
                    can_approve=True,
                    is_active=True,
                )
                .select_related("user")
                .order_by("user__id")
            )
            users = [link.user for link in links]

        return self._dedupe_users(users)

    def create_approval_tasks(self):
        if not self.matched_rule_id:
            raise ValidationError("Cannot create approval tasks without a matched approval rule.")

        steps = self.matched_rule.steps.filter(is_active=True).order_by("step_no")
        if not steps.exists():
            raise ValidationError("The matched approval rule has no active steps.")

        self.approval_tasks.all().delete()

        created_count = 0
        for step in steps:
            is_first_step = created_count == 0

            if step.approver_type in POOL_APPROVER_TYPES:
                candidates = self.resolve_step_candidates(step)
                if not candidates:
                    raise ValidationError(
                        f"Unable to resolve any candidates for step {step.step_no} - {step.step_name}."
                    )

                task_status = ApprovalTaskStatus.POOL if is_first_step else ApprovalTaskStatus.WAITING

                task = ApprovalTask.objects.create(
                    purchase_request=self,
                    request_content_type=purchase_request_content_type,
                    request_object_id=self.id,
                    rule=matched_rule,
                    step=step,
                    step_no=step.step_no,
                    step_name=step.step_name,
                    status=task_status,
                    assigned_user=assigned_user,
                )

                ApprovalTaskCandidate.objects.bulk_create(
                    [
                        ApprovalTaskCandidate(task=task, user=user)
                        for user in candidates
                    ]
                )

                task._add_history(
                    action_type=ApprovalTaskActionType.CREATED,
                    action_by=None,
                    from_status=None,
                    to_status=task.status,
                    from_assignee=None,
                    to_assignee=None,
                    comment=f"Pool task created with {len(candidates)} candidate(s).",
                )

            else:
                assigned_user = self.resolve_fixed_step_assignee(step) if is_first_step else None
                if is_first_step and not assigned_user:
                    raise ValidationError(
                        f"Unable to resolve approver for step {step.step_no} - {step.step_name}."
                    )

                task_status = ApprovalTaskStatus.PENDING if is_first_step else ApprovalTaskStatus.WAITING

                task = ApprovalTask.objects.create(
                    purchase_request=self,
                    rule=self.matched_rule,
                    step=step,
                    step_no=step.step_no,
                    step_name=step.step_name,
                    assigned_user=assigned_user,
                    status=task_status,
                )

                task._add_history(
                    action_type=ApprovalTaskActionType.CREATED,
                    action_by=None,
                    from_status=None,
                    to_status=task.status,
                    from_assignee=None,
                    to_assignee=assigned_user,
                    comment=(
                        f"Task created and assigned to {assigned_user}."
                        if assigned_user
                        else "Waiting task created. Assignee will be resolved on activation."
                    ),
                )

            created_count += 1

    def validate_for_submit(self):
        errors = []

        if self.status not in [RequestStatus.DRAFT, RequestStatus.RETURNED]:
            errors.append("Only Draft or Returned requests can be submitted.")

        if not self.requester_id:
            errors.append("Requester is required.")

        if not self.request_department_id:
            errors.append("Request department is required.")

        if not self.project_id:
            errors.append("Project is required.")

        if not self.lines.exists():
            errors.append("At least one line item is required before submission.")

        lines_total = self.get_lines_total()
        if lines_total <= 0:
            errors.append("The total line amount must be greater than 0.")

        if self.project_id:
            available_budget = self.get_project_available_budget()
            if lines_total > available_budget:
                errors.append(
                    f"Insufficient project budget. Available budget is "
                    f"{available_budget}, but this request needs {lines_total}."
                )

        matched_rule = self.resolve_approval_rule()
        if not matched_rule:
            errors.append("No active approval rule matched this purchase request.")

        return errors

    @transaction.atomic
    def submit(self, acting_user=None):
        errors = self.validate_for_submit()
        if errors:
            raise ValidationError(errors)

        from_status = self.status
        lines_total = self.get_lines_total()
        matched_rule = self.resolve_approval_rule()

        self.estimated_total = lines_total
        self.status = RequestStatus.SUBMITTED
        self.matched_rule = matched_rule
        self.save(update_fields=["estimated_total", "status", "matched_rule"])

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=lines_total,
            notes=f"Budget reserved by submitting {self.pr_no}",
            created_by=acting_user,
        )

        purchase_request_content_type = ContentType.objects.get_for_model(PurchaseRequest)

        self.create_approval_tasks()

        from .notifications import notify_pr_submitted, notify_current_task_activated

        current_task = self.get_current_task()

        transaction.on_commit(lambda: notify_pr_submitted(self))

        if current_task:
            transaction.on_commit(lambda: notify_current_task_activated(current_task))

        self._add_history(
            action_type=PurchaseRequestHistoryActionType.SUBMITTED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=f"{self.pr_no} submitted. Matched rule: {matched_rule.rule_code}.",
        )

    @transaction.atomic
    def mark_as_approved(self, acting_user=None, comment=""):
        from_status = self.status
        self.status = RequestStatus.APPROVED
        self.save(update_fields=["status"])

        self._add_history(
            action_type=PurchaseRequestHistoryActionType.APPROVED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.pr_no} approved.",
        )
        from .notifications import notify_pr_approved

        transaction.on_commit(lambda: notify_pr_approved(self))

    @transaction.atomic
    def mark_as_returned(self, acting_user=None, comment="", exclude_task_id=None):
        from_status = self.status
        self.status = RequestStatus.RETURNED
        self.save(update_fields=["status"])

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RELEASE,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=self.estimated_total,
            notes=f"Budget released by returning {self.pr_no}",
            created_by=acting_user,
        )

        for task in self.approval_tasks.exclude(id=exclude_task_id).filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ):
            task.cancel_by_system(comment=f"Source purchase request {self.pr_no} returned.")

        self._add_history(
            action_type=PurchaseRequestHistoryActionType.RETURNED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.pr_no} returned to requester.",
        )

        from .notifications import notify_pr_returned

        transaction.on_commit(lambda: notify_pr_returned(self, comment))

    @transaction.atomic
    def mark_as_rejected(self, acting_user=None, comment="", exclude_task_id=None):
        from_status = self.status
        self.status = RequestStatus.REJECTED
        self.save(update_fields=["status"])

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RELEASE,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=self.estimated_total,
            notes=f"Budget released by rejecting {self.pr_no}",
            created_by=acting_user,
        )

        for task in self.approval_tasks.exclude(id=exclude_task_id).filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ):
            task.cancel_by_system(comment=f"Source purchase request {self.pr_no} rejected.")

        self._add_history(
            action_type=PurchaseRequestHistoryActionType.REJECTED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.pr_no} rejected.",
        )

        from .notifications import notify_pr_rejected

        transaction.on_commit(lambda: notify_pr_rejected(self, comment))

    def validate_for_cancel(self):
        errors = []

        if self.status not in [
            RequestStatus.SUBMITTED,
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
        ]:
            errors.append("Only Submitted, Pending Approval, or Approved requests can be cancelled.")

        return errors

    @transaction.atomic
    def cancel(self, acting_user=None):
        errors = self.validate_for_cancel()
        if errors:
            raise ValidationError(errors)

        from_status = self.status

        self.status = RequestStatus.CANCELLED
        self.save(update_fields=["status"])

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RELEASE,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=self.estimated_total,
            notes=f"Budget released by cancelling {self.pr_no}",
            created_by=acting_user,
        )

        for task in self.approval_tasks.filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ):
            task.cancel_by_system(comment=f"Source purchase request {self.pr_no} cancelled.")

        self._add_history(
            action_type=PurchaseRequestHistoryActionType.CANCELLED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=f"{self.pr_no} cancelled.",
        )

def purchase_attachment_upload_to(instance, filename):
    pr_no = instance.purchase_request.pr_no or f"pr_{instance.purchase_request_id}"
    return f"purchase_attachments/{pr_no}/{filename}"


class PurchaseRequestAttachmentType(models.TextChoices):
    QUOTE = "QUOTE", "Vendor Quote"
    SUPPORT = "SUPPORT", "Supporting Document"
    OTHER = "OTHER", "Other"


class PurchaseRequestAttachment(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    document_type = models.CharField(
        max_length=20,
        choices=PurchaseRequestAttachmentType,
        default=PurchaseRequestAttachmentType.OTHER,
    )
    title = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to=purchase_attachment_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_request_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_PR_ATT"
        verbose_name = "Purchase Request Attachment"
        verbose_name_plural = "Purchase Request Attachments"
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.purchase_request.pr_no} / {self.title or self.filename}"

    @property
    def filename(self):
        return Path(self.file.name).name if self.file else ""

    def save(self, *args, **kwargs):
        if not self.title and self.file:
            self.title = Path(self.file.name).name
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        storage = self.file.storage if self.file else None
        file_name = self.file.name if self.file else None
        super().delete(*args, **kwargs)
        if storage and file_name:
            storage.delete(file_name)

class PurchaseRequestContentAuditActionType(models.TextChoices):
    HEADER_CREATED = "HEADER_CREATED", "Header Created"
    HEADER_UPDATED = "HEADER_UPDATED", "Header Updated"
    LINE_ADDED = "LINE_ADDED", "Line Added"
    LINE_UPDATED = "LINE_UPDATED", "Line Updated"
    LINE_DELETED = "LINE_DELETED", "Line Deleted"

class PurchaseRequestContentAudit(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="content_audits",
    )
    action_type = models.CharField(
        max_length=30,
        choices=PurchaseRequestContentAuditActionType,
    )
    field_name = models.CharField(max_length=100, blank=True, default="")
    line_no = models.IntegerField(null=True, blank=True)
    old_value = models.TextField(blank=True, default="")
    new_value = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_request_content_audits",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_PR_AUD"
        verbose_name = "Purchase Request Content Audit"
        verbose_name_plural = "Purchase Request Content Audits"
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.purchase_request.pr_no} / {self.action_type} / {self.field_name or '-'}"

class PurchaseRequestLine(models.Model):
    request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_no = models.PositiveIntegerField()
    item_name = models.CharField(max_length=200)
    item_description = models.TextField(blank=True, default="")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    uom = models.CharField(
        max_length=20,
        choices=UnitOfMeasure,
        default=UnitOfMeasure.EA,
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "PS_A8_PR_LN"
        verbose_name = "Purchase Request Line"
        verbose_name_plural = "Purchase Request Lines"
        ordering = ["request", "line_no"]
        unique_together = ("request", "line_no")

    def __str__(self):
        return f"{self.request.pr_no} / Line {self.line_no}"

    def save(self, *args, **kwargs):
        self.line_amount = (self.quantity or Decimal("0.00")) * (self.unit_price or Decimal("0.00"))
        super().save(*args, **kwargs)


class PurchaseRequestHistory(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    action_type = models.CharField(max_length=30, choices=PurchaseRequestHistoryActionType)
    from_status = models.CharField(max_length=20, choices=RequestStatus, null=True, blank=True)
    to_status = models.CharField(max_length=20, choices=RequestStatus, null=True, blank=True)
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_request_history_actions",
    )
    action_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_PR_HIST"
        verbose_name = "Purchase Request History"
        verbose_name_plural = "Purchase Request Histories"
        ordering = ["-action_at", "-id"]

    def __str__(self):
        return f"{self.purchase_request.pr_no} / {self.action_type} / {self.action_at}"