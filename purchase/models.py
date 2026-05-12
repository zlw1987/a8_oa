import os
from pathlib import Path
from decimal import Decimal
from datetime import date

from django.db import models, transaction
from django.db.models import Sum
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from common.choices import (
    RequestStatus,
    RequestType,
    BudgetEntryType,
    ApprovalTaskStatus,
    PurchaseRequestHistoryActionType,
    ApproverType,
    DepartmentType,
    UnitOfMeasure,
    CurrencyCode,
    ActualExpenseEntryType,
)
from projects.models import ProjectBudgetEntry
from accounts.models import UserDepartment
from common.currency import COMPANY_BASE_CURRENCY

class PurchaseRequestNumberSequence(models.Model):
    sequence_date = models.DateField(unique=True)
    last_number = models.IntegerField(default=0)

    class Meta:
        db_table = "PS_A8_PR_SEQ"
        verbose_name = "Purchase Request Number Sequence"
        verbose_name_plural = "Purchase Request Number Sequences"

    def __str__(self):
        return f"{self.sequence_date} / {self.last_number}"

class PurchaseFulfillmentStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    PARTIAL = "PARTIAL", "Partially Spent"
    COMPLETED = "COMPLETED", "Completed"

class PurchaseActualReviewStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not Required"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
    APPROVED_TO_PROCEED = "APPROVED_TO_PROCEED", "Approved to Proceed"
    REJECTED = "REJECTED", "Rejected"

class PurchaseActualReviewStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not Required"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
    APPROVED_TO_PROCEED = "APPROVED_TO_PROCEED", "Approved to Proceed"
    REJECTED = "REJECTED", "Rejected"

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
    parent_request = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplemental_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=RequestStatus,
        default=RequestStatus.DRAFT,
    )

    fulfillment_status = models.CharField(
        max_length=20,
        choices=PurchaseFulfillmentStatus,
        default=PurchaseFulfillmentStatus.NOT_STARTED,
    )

    request_date = models.DateField()
    needed_by_date = models.DateField(null=True, blank=True)
    currency = models.CharField(
    max_length=10,
    choices=CurrencyCode,
    default=COMPANY_BASE_CURRENCY,
    )
    transaction_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    base_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    exchange_rate_date = models.DateField(null=True, blank=True)
    exchange_rate_source = models.CharField(max_length=30, blank=True, default="")
    exchange_rate_override_reason = models.TextField(blank=True, default="")
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    justification = models.TextField(blank=True, default="")
    vendor_suggestion = models.CharField(max_length=100, blank=True, default="")
    delivery_location = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    supplemental_reason = models.TextField(blank=True, default="")
    is_over_estimate = models.BooleanField(default=False)
    actual_review_status = models.CharField(
        max_length=30,
        choices=PurchaseActualReviewStatus,
        default=PurchaseActualReviewStatus.NOT_REQUIRED,
    )
    actual_review_comment = models.TextField(blank=True, default="")
    actual_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_actual_reviews",
    )
    actual_reviewed_at = models.DateTimeField(null=True, blank=True)
    pending_overage_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_overage_note = models.TextField(blank=True, default="")
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reopened_purchase_requests",
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.TextField(blank=True, default="")
    reclosed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reclosed_purchase_requests",
    )
    reclosed_at = models.DateTimeField(null=True, blank=True)
    correction_reference = models.CharField(max_length=80, blank=True, default="")
    correction_status = models.CharField(max_length=30, blank=True, default="")


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
        from .access import get_visible_purchase_queryset_for_user
        return get_visible_purchase_queryset_for_user(user)

    def can_user_view(self, user):
        from .access import user_can_view_purchase
        return user_can_view_purchase(user, self)

    def can_user_edit(self, user):
        from .access import user_can_edit_purchase
        return user_can_edit_purchase(user, self)

    def can_user_submit(self, user):
        from .access import user_can_submit_purchase
        return user_can_submit_purchase(user, self)

    def can_user_record_actual_spend(self, user):
        from .access import user_can_record_actual_spend
        return user_can_record_actual_spend(user, self)

    def can_user_cancel(self, user):
        from .access import user_can_cancel_purchase
        return user_can_cancel_purchase(user, self)

    def can_user_close_purchase(self, user):
        from .access import user_can_close_purchase
        return user_can_close_purchase(user, self)

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
        from approvals.services import resolve_approval_rule_for_request

        return resolve_approval_rule_for_request(self)

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
        from approvals.services import create_approval_tasks_for_request

        return create_approval_tasks_for_request(self, self.matched_rule)

    def validate_for_submit(self):
        errors = []

        if self.status not in [RequestStatus.DRAFT, RequestStatus.RETURNED]:
            errors.append("Only Draft or Returned requests can be submitted.")

        if not self.requester_id:
            errors.append("Requester is required.")

        if not self.request_department_id:
            errors.append("Request department is required.")

        if self.project_id:
            if hasattr(self.project, "is_open") and not self.project.is_open():
                errors.append("Only open projects can be linked to purchase requests.")

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

    @property
    def is_amendment(self):
        return self.parent_request_id is not None

    def get_amendment_delta_amount(self):
        if not self.is_amendment:
            return Decimal("0.00")
        return self.get_lines_total()

    def get_original_approved_amount(self):
        if not self.parent_request_id:
            return self.estimated_total
        return self.parent_request.estimated_total

    def get_revised_amount(self):
        if not self.parent_request_id:
            return self.estimated_total
        return self.parent_request.estimated_total + self.get_amendment_delta_amount()

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

        if not self.is_amendment:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RESERVE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=lines_total,
                notes=f"Budget reserved by submitting {self.pr_no}",
                created_by=acting_user,
            )

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
        if self.is_amendment:
            amendment_delta = self.get_amendment_delta_amount()
            available_budget = self.get_project_available_budget()
            if amendment_delta > available_budget:
                raise ValidationError(
                    f"Insufficient project budget for amendment. Available budget is "
                    f"{available_budget}, but this amendment needs {amendment_delta}."
                )

        self.status = RequestStatus.APPROVED
        self.save(update_fields=["status"])

        if self.is_amendment:
            amendment_delta = self.get_amendment_delta_amount()
            if amendment_delta > 0:
                ProjectBudgetEntry.objects.create(
                    project=self.project,
                    entry_type=BudgetEntryType.RESERVE,
                    source_type=RequestType.PURCHASE,
                    source_id=self.id,
                    amount=amendment_delta,
                    notes=(
                        f"Additional budget reserved by approved amendment {self.pr_no} "
                        f"for {self.parent_request.pr_no}"
                    ),
                    created_by=acting_user,
                )

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

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=reserved_remaining,
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

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=reserved_remaining,
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

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=reserved_remaining,
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

    def get_actual_spent_total(self):
        total = self.actual_spend_entries.aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")

    def get_reserved_remaining_amount(self):
        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        return reserve_total - release_total

    def refresh_actual_review_state(self, commit=True):
        over_estimate = self.get_actual_spent_total() > self.estimated_total
        self.is_over_estimate = over_estimate

        if over_estimate:
            if self.actual_review_status not in [
                PurchaseActualReviewStatus.APPROVED_TO_PROCEED,
                PurchaseActualReviewStatus.REJECTED,
            ]:
                self.actual_review_status = PurchaseActualReviewStatus.PENDING_REVIEW
                self.actual_review_comment = ""
                self.actual_reviewed_by = None
                self.actual_reviewed_at = None
        else:
            self.actual_review_status = PurchaseActualReviewStatus.NOT_REQUIRED
            self.actual_review_comment = ""
            self.actual_reviewed_by = None
            self.actual_reviewed_at = None
            self.pending_overage_amount = Decimal("0.00")
            self.pending_overage_note = ""

        if commit:
            self.save(
                update_fields=[
                    "is_over_estimate",
                    "actual_review_status",
                    "actual_review_comment",
                    "actual_reviewed_by",
                    "actual_reviewed_at",
                    "pending_overage_amount",
                    "pending_overage_note",
                ]
            )

    @transaction.atomic
    def review_actual_variance(self, *, review_status, comment="", acting_user=None):
        if not self.is_over_estimate:
            raise ValidationError("Actual review is not required for this request.")
        if acting_user and self.requester_id == acting_user.id:
            raise ValidationError("Requester cannot mark their own actual spending as accounting-reviewed.")

        allowed = {
            PurchaseActualReviewStatus.APPROVED_TO_PROCEED,
            PurchaseActualReviewStatus.REJECTED,
        }
        if review_status not in allowed:
            raise ValidationError("Invalid actual review status.")

        self.actual_review_status = review_status
        self.actual_review_comment = comment or ""
        self.actual_reviewed_by = acting_user
        self.actual_reviewed_at = timezone.now()
        self.save(
            update_fields=[
                "actual_review_status",
                "actual_review_comment",
                "actual_reviewed_by",
                "actual_reviewed_at",
            ]
        )
        from finance.models import AccountingReviewDecision
        from finance.services import resolve_accounting_review_items_for_request

        decision = (
            AccountingReviewDecision.APPROVE_EXCEPTION
            if review_status == PurchaseActualReviewStatus.APPROVED_TO_PROCEED
            else AccountingReviewDecision.REJECT
        )
        resolve_accounting_review_items_for_request(
            self,
            decision=decision,
            comment=comment,
            acting_user=acting_user,
        )

    @transaction.atomic
    def record_actual_spend(
        self,
        spend_date,
        amount,
        acting_user=None,
        vendor_name="",
        reference_no="",
        notes="",
        transaction_currency="",
        transaction_amount=None,
        base_amount=None,
        exchange_rate=None,
        exchange_rate_date=None,
        exchange_rate_source="",
        exchange_rate_override_reason="",
        skip_finance_policy=False,
        payment_method=None,
        card_transaction=None,
        card_allocation=None,
    ):
        if self.status != RequestStatus.APPROVED:
            raise ValidationError("Actual spend can only be recorded after the purchase request is fully approved.")

        if amount <= 0:
            raise ValidationError("Actual spend amount must be greater than 0.")

        from finance.services import build_money_snapshot
        from finance.services import enforce_accounting_period_open

        enforce_accounting_period_open(spend_date, action_label="record actual spend", user=acting_user)

        snapshot = build_money_snapshot(
            transaction_amount=transaction_amount if transaction_amount is not None else amount,
            transaction_currency=transaction_currency or self.currency,
            base_amount=base_amount,
            base_currency=COMPANY_BASE_CURRENCY,
            exchange_rate=exchange_rate,
            exchange_rate_date=exchange_rate_date or spend_date,
            exchange_rate_source=exchange_rate_source,
            override_reason=exchange_rate_override_reason,
        )
        base_actual_amount = snapshot["base_amount"]
        policy_result = None
        from finance.models import PaymentMethod

        effective_payment_method = payment_method or PaymentMethod.REIMBURSEMENT
        if not skip_finance_policy:
            from finance.services import (
                apply_actual_expense_policy_result,
                evaluate_actual_expense_policy,
            )

            policy_result = evaluate_actual_expense_policy(
                self,
                current_actual_amount=base_actual_amount,
                current_transaction_amount=snapshot["transaction_amount"],
                transaction_currency=snapshot["transaction_currency"],
                base_amount=snapshot["base_amount"],
                base_currency=snapshot["base_currency"],
                exchange_rate=snapshot["exchange_rate"],
                exchange_rate_date=snapshot["exchange_rate_date"],
                exchange_rate_source=snapshot["exchange_rate_source"],
                exchange_rate_override_reason=snapshot["exchange_rate_override_reason"],
                payment_method=effective_payment_method,
                currency=snapshot["base_currency"],
            )
            if not policy_result.allows_recording:
                apply_actual_expense_policy_result(policy_result, acting_user=acting_user)

        reserved_remaining = self.get_reserved_remaining_amount()
        extra_needed = base_actual_amount - reserved_remaining if base_actual_amount > reserved_remaining else Decimal("0.00")

        if extra_needed > 0:
            available_budget = self.project.get_available_amount()
            if extra_needed > available_budget:
                raise ValidationError(
                    f"Insufficient project budget for overspend. Extra needed is {extra_needed}, "
                    f"but available budget is {available_budget}."
                )

        actual_spend = PurchaseActualSpend.objects.create(
            purchase_request=self,
            spend_date=spend_date,
            amount=base_actual_amount,
            currency=snapshot["base_currency"],
            transaction_currency=snapshot["transaction_currency"],
            transaction_amount=snapshot["transaction_amount"],
            base_currency=snapshot["base_currency"],
            base_amount=snapshot["base_amount"],
            exchange_rate=snapshot["exchange_rate"],
            exchange_rate_date=snapshot["exchange_rate_date"],
            exchange_rate_source=snapshot["exchange_rate_source"],
            exchange_rate_override_reason=snapshot["exchange_rate_override_reason"],
            variance_type=getattr(policy_result, "variance_type", "") if policy_result else "",
            vendor_name=vendor_name,
            reference_no=reference_no,
            notes=notes,
            created_by=acting_user,
        )

        if policy_result is not None:
            from finance.services import apply_actual_expense_policy_result

            apply_actual_expense_policy_result(
                policy_result,
                actual_expense=actual_spend,
                card_transaction=card_transaction,
                card_allocation=card_allocation,
                acting_user=acting_user,
            )

        from finance.services import apply_receipt_policy_for_actual
        from finance.services import create_duplicate_actual_expense_review_item

        apply_receipt_policy_for_actual(
            self,
            actual_expense=actual_spend,
            amount=base_actual_amount,
            payment_method=effective_payment_method,
            currency=snapshot["base_currency"],
            card_transaction=card_transaction,
            card_allocation=card_allocation,
            acting_user=acting_user,
        )
        create_duplicate_actual_expense_review_item(actual_spend, created_by=acting_user)

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=base_actual_amount,
            currency=snapshot["base_currency"],
            source_transaction_currency=snapshot["transaction_currency"],
            source_transaction_amount=snapshot["transaction_amount"],
            source_exchange_rate=snapshot["exchange_rate"],
            source_exchange_rate_source=snapshot["exchange_rate_source"],
            notes=f"Budget consumed by actual spend of {self.pr_no}",
            created_by=acting_user,
        )

        amount_to_release = min(base_actual_amount, reserved_remaining)
        if amount_to_release > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=amount_to_release,
                currency=snapshot["base_currency"],
                source_transaction_currency=snapshot["transaction_currency"],
                source_transaction_amount=snapshot["transaction_amount"],
                source_exchange_rate=snapshot["exchange_rate"],
                source_exchange_rate_source=snapshot["exchange_rate_source"],
                notes=f"Reserved budget converted to actual spend for {self.pr_no}",
                created_by=acting_user,
            )

        self.fulfillment_status = PurchaseFulfillmentStatus.PARTIAL
        self.pending_overage_amount = Decimal("0.00")
        self.pending_overage_note = ""
        self.refresh_actual_review_state(commit=False)
        self.save(
            update_fields=[
                "fulfillment_status",
                "is_over_estimate",
                "actual_review_status",
                "actual_review_comment",
                "actual_reviewed_by",
                "actual_reviewed_at",
                "pending_overage_amount",
                "pending_overage_note",
            ]
        )

        self._add_history(
            action_type=PurchaseRequestActionType.SPEND_RECORDED,
            from_status=self.status,
            to_status=self.status,
            acting_user=acting_user,
            comment=(
                f"Actual spend recorded: {self.currency} {amount}. "
                f"Base amount: {snapshot['base_currency']} {base_actual_amount}. "
                f"Vendor: {vendor_name or '-'}; Reference: {reference_no or '-'}."
            ),
        )

        return actual_spend

    @transaction.atomic
    def record_refund(
        self,
        *,
        original_actual_spend=None,
        refund_date,
        amount,
        acting_user=None,
        vendor_name="",
        reference_no="",
        notes="",
        entry_type=ActualExpenseEntryType.REFUND,
    ):
        from common.permissions import can_perform_accounting_work
        from finance.services import enforce_accounting_period_open

        if not can_perform_accounting_work(acting_user):
            raise ValidationError("Only accounting or finance users can record refunds or credits.")
        if amount <= 0:
            raise ValidationError("Refund amount must be greater than 0.")
        enforce_accounting_period_open(refund_date, action_label="record refund or credit", user=acting_user)

        negative_amount = Decimal("0.00") - amount
        refund = PurchaseActualSpend.objects.create(
            purchase_request=self,
            spend_date=refund_date,
            amount=negative_amount,
            currency=COMPANY_BASE_CURRENCY,
            transaction_currency=COMPANY_BASE_CURRENCY,
            transaction_amount=negative_amount,
            base_currency=COMPANY_BASE_CURRENCY,
            base_amount=negative_amount,
            entry_type=entry_type,
            original_actual_spend=original_actual_spend,
            vendor_name=vendor_name,
            reference_no=reference_no,
            notes=notes or "Refund / credit recorded.",
            created_by=acting_user,
        )
        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.PURCHASE,
            source_id=self.id,
            amount=negative_amount,
            currency=COMPANY_BASE_CURRENCY,
            notes=f"Budget consumption reduced by refund/credit for {self.pr_no}",
            created_by=acting_user,
        )
        self._add_history(
            action_type=PurchaseRequestActionType.SPEND_RECORDED,
            from_status=self.status,
            to_status=self.status,
            acting_user=acting_user,
            comment=f"Refund/credit recorded: {COMPANY_BASE_CURRENCY} {negative_amount}.",
        )
        return refund

    @transaction.atomic
    def close_purchase(self, acting_user=None, comment=""):
        if self.status != RequestStatus.APPROVED:
            raise ValidationError("Only approved purchase requests can be closed.")
        if self.actual_review_status == PurchaseActualReviewStatus.PENDING_REVIEW:
            raise ValidationError("Cannot close purchase request while actual spending review is pending.")
        from finance.services import validate_request_can_close

        validate_request_can_close(self)

        reserved_remaining = self.get_reserved_remaining_amount()
        actual_spent_total = self.get_actual_spent_total()
        from_status = self.status

        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.PURCHASE,
                source_id=self.id,
                amount=reserved_remaining,
                notes=f"Unused reserved budget released by closing {self.pr_no}",
                created_by=acting_user,
            )

        self.status = RequestStatus.CLOSED
        self.fulfillment_status = PurchaseFulfillmentStatus.COMPLETED
        update_fields = ["status", "fulfillment_status"]
        if self.reopened_at:
            self.reclosed_by = acting_user
            self.reclosed_at = timezone.now()
            self.correction_status = "RECLOSED"
            update_fields += ["reclosed_by", "reclosed_at", "correction_status"]
        self.save(update_fields=update_fields)

        self._add_history(
            action_type=PurchaseRequestActionType.CLOSED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=(
                comment
                or f"{self.pr_no} closed. Actual spent total: {self.currency} {actual_spent_total}. "
                   f"Unused reserve released: {self.currency} {reserved_remaining}."
            ),
        )

    @transaction.atomic
    def reopen_for_correction(self, *, acting_user=None, reason="", correction_reference=""):
        from common.permissions import can_manage_finance_setup
        from finance.services import enforce_accounting_period_open

        if self.status != RequestStatus.CLOSED:
            raise ValidationError("Only closed purchase requests can be reopened for correction.")
        if not can_manage_finance_setup(acting_user):
            raise ValidationError("Only finance/admin users can reopen closed purchase requests.")
        if not reason:
            raise ValidationError("Reopen reason is required.")
        enforce_accounting_period_open(self.request_date, action_label="reopen closed request", user=acting_user)

        from_status = self.status
        self.status = RequestStatus.APPROVED
        self.reopened_by = acting_user
        self.reopened_at = timezone.now()
        self.reopen_reason = reason
        self.correction_reference = correction_reference or ""
        self.correction_status = "OPEN"
        self.save(
            update_fields=[
                "status",
                "reopened_by",
                "reopened_at",
                "reopen_reason",
                "correction_reference",
                "correction_status",
            ]
        )
        self._add_history(
            action_type=PurchaseRequestActionType.REOPENED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=f"Reopened for correction: {reason}",
        )

def purchase_attachment_upload_to(instance, filename):
    pr_no = instance.purchase_request.pr_no or f"pr_{instance.purchase_request_id}"
    return f"purchase_attachments/{pr_no}/{filename}"


class PurchaseRequestAttachmentType(models.TextChoices):
    QUOTE = "QUOTE", "Vendor Quote"
    SUPPORT = "SUPPORT", "Supporting Document"
    OTHER = "OTHER", "Other"
    ACCOUNTING_APPROVAL = "ACCOUNTING_APPROVAL", "Accounting Approval Document"


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
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_purchase_request_attachments",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    delete_reason = models.TextField(blank=True, default="")

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
        if kwargs.pop("hard", False):
            storage = self.file.storage if self.file else None
            file_name = self.file.name if self.file else None
            super().delete(*args, **kwargs)
            if storage and file_name:
                storage.delete(file_name)
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def soft_delete(self, *, user=None, reason=""):
        self.is_deleted = True
        self.deleted_by = user
        self.deleted_at = timezone.now()
        self.delete_reason = reason or ""
        self.save(update_fields=["is_deleted", "deleted_by", "deleted_at", "delete_reason"])

    def hard_delete_file(self):
        storage = self.file.storage if self.file else None
        file_name = self.file.name if self.file else None
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
    estimate_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    estimate_transaction_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    estimated_base_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    estimated_base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    exchange_rate_date = models.DateField(null=True, blank=True)
    exchange_rate_source = models.CharField(max_length=30, blank=True, default="")
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

class PurchaseActualSpend(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="actual_spend_entries",
    )
    spend_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(
    max_length=10,
    choices=CurrencyCode,
    default=COMPANY_BASE_CURRENCY,
    )
    transaction_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    base_currency = models.CharField(max_length=10, choices=CurrencyCode, default=COMPANY_BASE_CURRENCY)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    exchange_rate_date = models.DateField(null=True, blank=True)
    exchange_rate_source = models.CharField(max_length=30, blank=True, default="")
    exchange_rate_override_reason = models.TextField(blank=True, default="")
    variance_type = models.CharField(max_length=30, blank=True, default="")
    entry_type = models.CharField(
        max_length=30,
        choices=ActualExpenseEntryType,
        default=ActualExpenseEntryType.ACTUAL_SPEND,
    )
    original_actual_spend = models.ForeignKey(
        "purchase.PurchaseActualSpend",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="refund_entries",
    )
    vendor_name = models.CharField(max_length=100, blank=True, default="")
    reference_no = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_actual_spend_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_PR_ACT"
        verbose_name = "Purchase Actual Spend"
        verbose_name_plural = "Purchase Actual Spend Entries"
        ordering = ["-spend_date", "-id"]

    def __str__(self):
        return f"{self.purchase_request.pr_no} / {self.spend_date} / {self.amount}"

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

class PurchaseRequestActionType(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    CANCELLED = "CANCELLED", "Cancelled"
    SPEND_RECORDED = "SPEND_RECORDED", "Actual Spend Recorded"
    REOPENED = "REOPENED", "Reopened For Correction"
    CLOSED = "CLOSED", "Closed"
