from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.utils import timezone

from common.choices import (
    ApprovalLevel,
    RequestType,
    ApprovalTaskStatus,
    RequestStatus,
    BudgetEntryType,
    PurchaseRequestHistoryActionType,
    ApproverType,
)


class ApprovalRule(models.Model):
    rule_code = models.CharField(max_length=30, unique=True)
    rule_name = models.CharField(max_length=100)
    request_type = models.CharField(max_length=20, choices=RequestType)
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_rules",
    )
    amount_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requester_level = models.CharField(
        max_length=20,
        choices=ApprovalLevel,
        blank=True,
        default="",
    )
    specific_requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="specific_approval_rules",
    )
    is_general_fallback = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "PS_A8_AP_RULE"
        verbose_name = "Approval Rule"
        verbose_name_plural = "Approval Rules"
        ordering = ["priority", "rule_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["request_type"],
                condition=models.Q(is_active=True, is_general_fallback=True),
                name="uq_active_general_fallback_per_request_type",
            ),
        ]

    def __str__(self):
        return f"{self.rule_code} - {self.rule_name}"

    def clean(self):
        super().clean()

        if not self.is_general_fallback:
            return

        errors = {}
        if self.department_id:
            errors["department"] = "General fallback rule must not be limited to a department."
        if self.amount_from is not None:
            errors["amount_from"] = "General fallback rule must not have Amount From."
        if self.amount_to is not None:
            errors["amount_to"] = "General fallback rule must not have Amount To."
        if self.requester_level:
            errors["requester_level"] = "General fallback rule must not be limited to requester level."
        if self.specific_requester_id:
            errors["specific_requester"] = "General fallback rule must not be limited to a requester."

        if errors:
            raise ValidationError(errors)


class ApprovalRuleStep(models.Model):

    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    step_no = models.PositiveIntegerField()
    step_name = models.CharField(max_length=100)
    approver_type = models.CharField(max_length=30, choices=ApproverType)
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_rule_steps_as_user",
    )
    approver_department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_rule_steps_as_department",
    )
    approver_level = models.CharField(
        max_length=20,
        choices=ApprovalLevel,
        blank=True,
        default="",
    )
    is_required = models.BooleanField(default=True)
    allow_self_skip = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sla_days = models.PositiveIntegerField(default=2)
    class Meta:
        db_table = "PS_A8_AP_STEP"
        verbose_name = "Approval Rule Step"
        verbose_name_plural = "Approval Rule Steps"
        ordering = ["rule", "step_no"]
        unique_together = ("rule", "step_no")

    def __str__(self):
        return f"{self.rule.rule_code} / Step {self.step_no} - {self.step_name}"


class ApprovalTaskActionType(models.TextChoices):
    CREATED = "CREATED", "Created"
    ACTIVATED = "ACTIVATED", "Activated"
    CLAIMED = "CLAIMED", "Claimed"
    RELEASED_TO_POOL = "RELEASED_TO_POOL", "Released to Pool"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    CANCELLED = "CANCELLED", "Cancelled"
    REASSIGNED = "REASSIGNED", "Reassigned"
    DELEGATED = "DELEGATED", "Delegated"


class ApprovalDelegation(models.Model):
    original_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_delegations_from",
    )
    delegate_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_delegations_to",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    department = models.ForeignKey(
        "accounts.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_delegations",
    )
    request_type = models.CharField(max_length=20, choices=RequestType, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_approval_delegations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_AP_DELEG"
        verbose_name = "Approval Delegation"
        verbose_name_plural = "Approval Delegations"
        ordering = ["-start_date", "original_approver"]

    def clean(self):
        super().clean()
        if self.original_approver_id and self.delegate_user_id and self.original_approver_id == self.delegate_user_id:
            raise ValidationError("Delegate user must be different from original approver.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Delegation start date cannot be after end date.")


class ApprovalEscalationPolicy(models.Model):
    request_type = models.CharField(max_length=20, choices=RequestType, blank=True, default="")
    step_type = models.CharField(max_length=30, choices=ApproverType, blank=True, default="")
    overdue_days = models.PositiveIntegerField(default=2)
    escalate_to_role = models.CharField(max_length=80, blank=True, default="")
    escalate_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_escalation_targets",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "PS_A8_AP_ESC_POL"
        verbose_name = "Approval Escalation Policy"
        verbose_name_plural = "Approval Escalation Policies"


class ApprovalTask(models.Model):
    purchase_request = models.ForeignKey(
        "purchase.PurchaseRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_tasks",
    )

    request_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_tasks",
    )

    request_object_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    request_object = GenericForeignKey("request_content_type", "request_object_id")

    rule = models.ForeignKey(
        ApprovalRule,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    step = models.ForeignKey(
        ApprovalRuleStep,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    step_no = models.PositiveIntegerField()
    step_name = models.CharField(max_length=100)
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_tasks",
    )
    status = models.CharField(
        max_length=20,
        choices=ApprovalTaskStatus,
        default=ApprovalTaskStatus.WAITING,
    )
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acted_approval_tasks",
    )
    acted_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    last_escalation_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.PositiveIntegerField(default=0)
    escalation_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "PS_A8_AP_TASK"
        verbose_name = "Approval Task"
        verbose_name_plural = "Approval Tasks"
        ordering = ["purchase_request", "step_no"]
        unique_together = ("purchase_request", "step_no")
        constraints = [
            models.UniqueConstraint(
                fields=["request_content_type", "request_object_id", "step_no"],
                condition=models.Q(
                    request_content_type__isnull=False,
                    request_object_id__isnull=False,
                ),
                name="uq_generic_request_step",
            ),
        ]

    def __str__(self):
        return f"{self.request_no or '-'} / Step {self.step_no} / {self.status}"


    @property
    def is_open_task(self):
        return self.status in [
            ApprovalTaskStatus.WAITING,
            ApprovalTaskStatus.POOL,
            ApprovalTaskStatus.PENDING,
        ]


    @property
    def is_overdue(self):
        return bool(
            self.due_at
            and self.is_open_task
            and timezone.now() > self.due_at
        )


    @property
    def due_status_label(self):
        if not self.due_at:
            return "-"

        if self.completed_at:
            return "Completed"

        if self.is_overdue:
            delta = timezone.now() - self.due_at
            days = max(1, delta.days)
            return f"Overdue by {days} day(s)"

        return "On Time"

    def can_send_reminder(self, now=None, cooldown_hours=24):
        now = now or timezone.now()

        if self.status not in [ApprovalTaskStatus.PENDING, ApprovalTaskStatus.POOL]:
            return False
        if self.completed_at is not None:
            return False
        if not self.is_overdue:
            return False
        if self.last_reminder_sent_at is None:
            return True

        return now - self.last_reminder_sent_at >= timedelta(hours=cooldown_hours)


    def can_send_escalation(self, now=None, cooldown_hours=48, min_overdue_days=2):
        now = now or timezone.now()

        if self.status not in [ApprovalTaskStatus.PENDING, ApprovalTaskStatus.POOL]:
            return False
        if self.completed_at is not None:
            return False
        if not self.due_at or now <= self.due_at:
            return False

        overdue_days = (now - self.due_at).days
        if overdue_days < min_overdue_days:
            return False

        if self.last_escalation_sent_at is None:
            return True

        return now - self.last_escalation_sent_at >= timedelta(hours=cooldown_hours)

    def _add_history(
        self,
        action_type,
        action_by=None,
        from_status=None,
        to_status=None,
        from_assignee=None,
        to_assignee=None,
        comment="",
    ):
        ApprovalTaskHistory.objects.create(
            task=self,
            action_type=action_type,
            action_by=action_by,
            from_status=from_status,
            to_status=to_status,
            from_assignee=from_assignee,
            to_assignee=to_assignee,
            comment=comment,
        )

    def can_user_claim(self, user):
        if self.candidates.filter(user=user, is_active=True).exists():
            return True
        today = timezone.localdate()
        return ApprovalDelegation.objects.filter(
            original_approver__in=self.candidates.filter(is_active=True).values_list("user", flat=True),
            delegate_user=user,
            start_date__lte=today,
            end_date__gte=today,
            is_active=True,
        ).exists()

    @transaction.atomic
    def claim(self, user):
        if self.status != ApprovalTaskStatus.POOL:
            raise ValidationError("Only pool tasks can be claimed.")

        if not self.can_user_claim(user):
            raise ValidationError("You are not a candidate for this task.")
        requester = self.request_requester
        if requester and requester.id == user.id:
            raise ValidationError("Requester self-approval is not allowed.")

        from_status = self.status
        from_assignee = self.assigned_user

        self.assigned_user = user
        self.status = ApprovalTaskStatus.PENDING
        self.save(update_fields=["assigned_user", "status"])

        self._add_history(
            action_type=ApprovalTaskActionType.CLAIMED,
            action_by=user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=from_assignee,
            to_assignee=user,
            comment=f"Task claimed by {user}.",
        )
        self._add_request_history_if_supported(
            action_key="task_claimed",
            acting_user=user,
            comment=f"Task '{self.step_name}' claimed by {user}.",
        )

    @transaction.atomic
    def release_to_pool(self, user):
        if self.status != ApprovalTaskStatus.PENDING:
            raise ValidationError("Only pending tasks can be released back to pool.")

        if self.assigned_user_id != user.id:
            raise ValidationError("Only the current assignee can release this task back to pool.")

        if not self.candidates.exists():
            raise ValidationError("This task is not a pool task and cannot be released to pool.")

        from_status = self.status
        from_assignee = self.assigned_user

        self.assigned_user = None
        self.status = ApprovalTaskStatus.POOL
        self.save(update_fields=["assigned_user", "status"])

        self._add_history(
            action_type=ApprovalTaskActionType.RELEASED_TO_POOL,
            action_by=user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=from_assignee,
            to_assignee=None,
            comment=f"Task released back to pool by {user}.",
        )
        self._add_request_history_if_supported(
            action_key="task_released_to_pool",
            acting_user=user,
            comment=f"Task '{self.step_name}' released back to pool by {user}.",
        )

    def get_request_object(self):
        return self.request_object or self.purchase_request

    @property
    def request_no(self):
        request_obj = self.get_request_object()
        return (
            getattr(request_obj, "pr_no", "")
            or getattr(request_obj, "travel_no", "")
            or getattr(request_obj, "project_code", "")
            or ""
        )

    @property
    def request_title(self):
        request_obj = self.get_request_object()
        return (
            getattr(request_obj, "title", "")
            or getattr(request_obj, "purpose", "")
            or getattr(request_obj, "project_name", "")
            or ""
        )

    def get_request_tasks_queryset(self):
        if self.request_content_type_id and self.request_object_id:
            return ApprovalTask.objects.filter(
                request_content_type=self.request_content_type,
                request_object_id=self.request_object_id,
            ).order_by("step_no", "id")

        if self.purchase_request_id:
            return ApprovalTask.objects.filter(
                purchase_request=self.purchase_request,
            ).order_by("step_no", "id")

        return ApprovalTask.objects.none()

    @property
    def request_requester(self):
        request_obj = self.get_request_object()
        return getattr(request_obj, "requester", None)

    def _resolve_assignee_from_request(self):
        request_obj = self.get_request_object()
        if not request_obj:
            return None

        resolver = getattr(request_obj, "resolve_fixed_step_assignee", None)
        if callable(resolver):
            return resolver(self.step)

        return None

    def _add_request_history_if_supported(self, action_key, acting_user=None, comment=""):
        request_obj = self.get_request_object()
        if not request_obj:
            return

        history_writer = getattr(request_obj, "_add_history", None)
        if not callable(history_writer):
            return

        app_label = ""
        if self.request_content_type_id:
            app_label = self.request_content_type.app_label
        elif self.purchase_request_id:
            app_label = "purchase"

        if app_label != "purchase":
            return

        action_map = {
            "task_claimed": PurchaseRequestHistoryActionType.TASK_CLAIMED,
            "task_released_to_pool": PurchaseRequestHistoryActionType.TASK_RELEASED_TO_POOL,
            "task_approved": PurchaseRequestHistoryActionType.TASK_APPROVED,
            "task_rejected": PurchaseRequestHistoryActionType.TASK_REJECTED,
            "task_returned": PurchaseRequestHistoryActionType.TASK_RETURNED,
        }

        action_type = action_map.get(action_key)
        if not action_type:
            return

        history_writer(
            action_type=action_type,
            acting_user=acting_user,
            comment=comment,
        )

    @transaction.atomic
    def activate(self):
        if self.status != ApprovalTaskStatus.WAITING:
            raise ValidationError("Only waiting tasks can be activated.")

        from_status = self.status
        from_assignee = self.assigned_user

        due_at = timezone.now() + timedelta(days=self.step.sla_days or 0)

        if self.candidates.exists():
            self.assigned_user = None
            self.status = ApprovalTaskStatus.POOL
            self.due_at = due_at
            self.completed_at = None
            self.save(update_fields=["assigned_user", "status", "due_at", "completed_at"])

            self._add_history(
                action_type=ApprovalTaskActionType.ACTIVATED,
                action_by=None,
                from_status=from_status,
                to_status=self.status,
                from_assignee=from_assignee,
                to_assignee=None,
                comment="Pool task activated.",
            )
            return

        assigned_user = self._resolve_assignee_from_request()
        if not assigned_user:
            raise ValidationError(
                f"Unable to resolve approver for step {self.step_no} - {self.step_name}."
            )
        today = timezone.localdate()
        delegation = ApprovalDelegation.objects.filter(
            original_approver=assigned_user,
            start_date__lte=today,
            end_date__gte=today,
            is_active=True,
        ).first()
        if delegation:
            assigned_user = delegation.delegate_user

        self.assigned_user = assigned_user
        self.status = ApprovalTaskStatus.PENDING
        self.due_at = due_at
        self.completed_at = None
        self.save(update_fields=["assigned_user", "status", "due_at", "completed_at"])

        self._add_history(
            action_type=ApprovalTaskActionType.ACTIVATED,
            action_by=None,
            from_status=from_status,
            to_status=self.status,
            from_assignee=from_assignee,
            to_assignee=assigned_user,
            comment=f"Task activated and assigned to {assigned_user}.",
        )

    @transaction.atomic
    def reassign(self, *, acting_user, new_assignee, reason):
        from common.permissions import can_manage_finance_setup

        if not can_manage_finance_setup(acting_user):
            raise ValidationError("Only admin/finance users can reassign approval tasks.")
        if not reason:
            raise ValidationError("Reassignment reason is required.")
        requester = self.request_requester
        if requester and requester.id == new_assignee.id:
            raise ValidationError("Requester self-approval is not allowed.")
        if self.status not in [ApprovalTaskStatus.PENDING, ApprovalTaskStatus.POOL]:
            raise ValidationError("Only open approval tasks can be reassigned.")

        from_status = self.status
        from_assignee = self.assigned_user
        self.assigned_user = new_assignee
        self.status = ApprovalTaskStatus.PENDING
        self.save(update_fields=["assigned_user", "status"])
        self._add_history(
            action_type=ApprovalTaskActionType.REASSIGNED,
            action_by=acting_user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=from_assignee,
            to_assignee=new_assignee,
            comment=reason,
        )

    def _get_next_task(self):
        return (
            self.get_request_tasks_queryset()
            .filter(step_no__gt=self.step_no)
            .order_by("step_no", "id")
            .first()
        )

    @transaction.atomic
    def approve(self, user, comment=""):
        if self.status != ApprovalTaskStatus.PENDING:
            raise ValidationError("Only pending tasks can be approved.")

        if self.assigned_user_id != user.id:
            raise ValidationError("Only the current assignee can approve this task.")

        from_status = self.status
        current_assignee = self.assigned_user

        self.status = ApprovalTaskStatus.APPROVED
        self.acted_by = user
        self.acted_at = timezone.now()
        self.completed_at = self.acted_at
        self.comment = comment
        self.save(update_fields=["status", "acted_by", "acted_at", "completed_at", "comment"])

        self._add_history(
            action_type=ApprovalTaskActionType.APPROVED,
            action_by=user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=current_assignee,
            to_assignee=current_assignee,
            comment=comment or f"Task approved by {user}.",
        )
        request_obj = self.get_request_object()
        self._add_request_history_if_supported(
            action_key="task_approved",
            acting_user=user,
            comment=comment or f"Task '{self.step_name}' approved by {user}.",
        )

        next_task = self._get_next_task()
        if next_task:
            next_task.activate()

            from purchase.notifications import notify_current_task_activated

            transaction.on_commit(
                lambda task_id=next_task.id: notify_current_task_activated(
                    ApprovalTask.objects.get(pk=task_id)
                )
            )
            return

        request_obj.mark_as_approved(
            acting_user=user,
            comment=f"All approval tasks completed for {self.request_no}.",
        )

    @transaction.atomic
    def reject(self, user, comment=""):
        if self.status != ApprovalTaskStatus.PENDING:
            raise ValidationError("Only pending tasks can be rejected.")

        if self.assigned_user_id != user.id:
            raise ValidationError("Only the current assignee can reject this task.")

        from_status = self.status
        current_assignee = self.assigned_user

        self.status = ApprovalTaskStatus.REJECTED
        self.acted_by = user
        self.acted_at = timezone.now()
        self.completed_at = self.acted_at
        self.comment = comment
        self.save(update_fields=["status", "acted_by", "acted_at", "completed_at", "comment"])

        self._add_history(
            action_type=ApprovalTaskActionType.REJECTED,
            action_by=user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=current_assignee,
            to_assignee=current_assignee,
            comment=comment or f"Task rejected by {user}.",
        )

        request_obj = self.get_request_object()

        self._add_request_history_if_supported(
            action_key="task_rejected",
            acting_user=user,
            comment=comment or f"Task '{self.step_name}' rejected by {user}.",
        )

        request_obj.mark_as_rejected(
            acting_user=user,
            comment=comment or f"Rejected at step {self.step_no} - {self.step_name}.",
            exclude_task_id=self.id,
        )

    @transaction.atomic
    def return_to_requester(self, user, comment=""):
        if self.status != ApprovalTaskStatus.PENDING:
            raise ValidationError("Only pending tasks can be returned to requester.")

        if self.assigned_user_id != user.id:
            raise ValidationError("Only the current assignee can return this task to requester.")

        from_status = self.status
        current_assignee = self.assigned_user

        self.status = ApprovalTaskStatus.RETURNED
        self.acted_by = user
        self.acted_at = timezone.now()
        self.completed_at = self.acted_at
        self.comment = comment
        self.save(update_fields=["status", "acted_by", "acted_at", "completed_at", "comment"])

        self._add_history(
            action_type=ApprovalTaskActionType.RETURNED,
            action_by=user,
            from_status=from_status,
            to_status=self.status,
            from_assignee=current_assignee,
            to_assignee=current_assignee,
            comment=comment or f"Task returned to requester by {user}.",
        )

        request_obj = self.get_request_object()

        self._add_request_history_if_supported(
            action_key="task_returned",
            acting_user=user,
            comment=comment or f"Task '{self.step_name}' returned to requester by {user}.",
        )

        request_obj.mark_as_returned(
            acting_user=user,
            comment=comment or f"Returned at step {self.step_no} - {self.step_name}.",
            exclude_task_id=self.id,
        )
    @transaction.atomic
    def cancel_by_system(self, comment=""):
        if self.status not in [
            ApprovalTaskStatus.WAITING,
            ApprovalTaskStatus.POOL,
            ApprovalTaskStatus.PENDING,
        ]:
            return

        from_status = self.status
        from_assignee = self.assigned_user

        self.status = ApprovalTaskStatus.CANCELLED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

        self._add_history(
            action_type=ApprovalTaskActionType.CANCELLED,
            action_by=None,
            from_status=from_status,
            to_status=self.status,
            from_assignee=from_assignee,
            to_assignee=from_assignee,
            comment=comment or "Task cancelled by system.",
        )


class ApprovalTaskCandidate(models.Model):
    task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_task_candidates",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "PS_A8_AP_TSK_CAND"
        verbose_name = "Approval Task Candidate"
        verbose_name_plural = "Approval Task Candidates"
        unique_together = ("task", "user")
        ordering = ["task", "user"]

    def __str__(self):
        return f"{self.task} / Candidate: {self.user}"


class ApprovalTaskHistory(models.Model):
    task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    action_type = models.CharField(max_length=30, choices=ApprovalTaskActionType)
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_task_history_actions",
    )
    from_status = models.CharField(
        max_length=20,
        choices=ApprovalTaskStatus,
        null=True,
        blank=True,
    )
    to_status = models.CharField(
        max_length=20,
        choices=ApprovalTaskStatus,
        null=True,
        blank=True,
    )
    from_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_task_history_from_assignee",
    )
    to_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_task_history_to_assignee",
    )
    action_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_AP_TSK_HIST"
        verbose_name = "Approval Task History"
        verbose_name_plural = "Approval Task Histories"
        ordering = ["-action_at", "-id"]

    def __str__(self):
        return f"{self.task} / {self.action_type} / {self.action_at}"

class ApprovalNotificationType(models.TextChoices):
    REMINDER = "REMINDER", "Reminder"
    ESCALATION = "ESCALATION", "Escalation"


class ApprovalNotificationStatus(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    DRY_RUN = "DRY_RUN", "Dry Run"

class ApprovalNotificationLog(models.Model):
    task = models.ForeignKey(
        "approvals.ApprovalTask",
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    notification_type = models.CharField(
        max_length=20,
        choices=ApprovalNotificationType,
    )
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body_preview = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=ApprovalNotificationStatus,
    )
    error_message = models.TextField(blank=True, default="")
    triggered_by_command = models.CharField(max_length=100, blank=True, default="")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_APR_NOTIFY_LOG"
        ordering = ["-sent_at", "-id"]

    def __str__(self):
        return f"{self.notification_type} / {self.recipient_email} / {self.sent_at}"
