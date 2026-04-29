from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum, Max, Q
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from common.choices import CurrencyCode, RequestType, BudgetEntryType
from common.approval_constants import POOL_APPROVER_TYPES

from approvals.models import ApprovalRule, ApprovalTask, ApprovalTaskStatus, ApprovalTaskCandidate
from projects.models import ProjectBudgetEntry

class TravelRequestNumberSequence(models.Model):
    sequence_date = models.DateField(unique=True)
    last_number = models.IntegerField(default=0)

    class Meta:
        db_table = "PS_A8_TR_SEQ"
        verbose_name = "Travel Request Number Sequence"
        verbose_name_plural = "Travel Request Number Sequences"

    def __str__(self):
        return f"{self.sequence_date} / {self.last_number}"


class TravelRequestStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    RETURNED = "RETURNED", "Returned"
    REJECTED = "REJECTED", "Rejected"
    IN_TRIP = "IN_TRIP", "In Trip"
    EXPENSE_PENDING = "EXPENSE_PENDING", "Expense Pending"
    EXPENSE_SUBMITTED = "EXPENSE_SUBMITTED", "Expense Submitted"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class TravelTransportType(models.TextChoices):
    AIR = "AIR", "Air"
    TRAIN = "TRAIN", "Train"
    TAXI = "TAXI", "Taxi"
    CAR_RENTAL = "CAR_RENTAL", "Car Rental"
    BUS = "BUS", "Bus"
    PRIVATE_CAR = "PRIVATE_CAR", "Private Car"
    CORPORATE_CAR = "CORPORATE_CAR","Corporate Car"
    OTHER = "OTHER", "Other"


class TravelExpenseType(models.TextChoices):
    AIRFARE = "AIRFARE", "Airfare"
    TRAIN = "TRAIN", "Train"
    TAXI = "TAXI", "Taxi"
    CAR_RENTAL = "CAR_RENTAL", "Car Rental"
    BUS = "BUS", "Bus"
    HOTEL = "HOTEL", "Hotel"
    MEAL = "MEAL", "Meal"
    PARKING = "PARKING", "Parking"
    TOLL = "TOLL", "Toll"
    VISA = "VISA", "Visa"
    REGISTRATION = "REGISTRATION", "Registration"
    MISC = "MISC", "Misc"

class TravelActualExpenseType(models.TextChoices):
    AIRFARE = "AIRFARE", "Airfare"
    TRAIN = "TRAIN", "Train"
    TAXI = "TAXI", "Taxi"
    CAR_RENTAL = "CAR_RENTAL", "Car Rental"
    BUS = "BUS", "Bus"
    HOTEL = "HOTEL", "Hotel"
    MEAL = "MEAL", "Meal"
    PARKING = "PARKING", "Parking"
    TOLL = "TOLL", "Toll"
    VISA = "VISA", "Visa"
    REGISTRATION = "REGISTRATION", "Registration"
    MISC = "MISC", "Misc"

class TravelLocationMode(models.TextChoices):
    TRANSIT = "TRANSIT", "Transit"
    STAY = "STAY", "Stay"
    LOCAL = "LOCAL", "Local"

TRAVEL_EXPENSE_LOCATION_MODE_MAP = {
    TravelExpenseType.AIRFARE: TravelLocationMode.TRANSIT,
    TravelExpenseType.TRAIN: TravelLocationMode.TRANSIT,
    TravelExpenseType.TAXI: TravelLocationMode.TRANSIT,
    TravelExpenseType.CAR_RENTAL: TravelLocationMode.TRANSIT,
    TravelExpenseType.BUS: TravelLocationMode.TRANSIT,

    TravelExpenseType.HOTEL: TravelLocationMode.STAY,

    TravelExpenseType.MEAL: TravelLocationMode.LOCAL,
    TravelExpenseType.PARKING: TravelLocationMode.LOCAL,
    TravelExpenseType.TOLL: TravelLocationMode.LOCAL,
    TravelExpenseType.VISA: TravelLocationMode.LOCAL,
    TravelExpenseType.REGISTRATION: TravelLocationMode.LOCAL,
    TravelExpenseType.MISC: TravelLocationMode.LOCAL,
}

def get_location_mode_for_expense_type(expense_type):
    return TRAVEL_EXPENSE_LOCATION_MODE_MAP.get(expense_type)

class TravelRequestContentAuditActionType(models.TextChoices):
    HEADER_CREATED = "HEADER_CREATED", "Header Created"
    HEADER_UPDATED = "HEADER_UPDATED", "Header Updated"
    ITINERARY_ADDED = "ITINERARY_ADDED", "Itinerary Added"
    ITINERARY_UPDATED = "ITINERARY_UPDATED", "Itinerary Updated"
    ITINERARY_DELETED = "ITINERARY_DELETED", "Itinerary Deleted"
    EXPENSE_ADDED = "EXPENSE_ADDED", "Expense Added"
    EXPENSE_UPDATED = "EXPENSE_UPDATED", "Expense Updated"
    EXPENSE_DELETED = "EXPENSE_DELETED", "Expense Deleted"


class TravelRequestHistoryActionType(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    CANCELLED = "CANCELLED", "Cancelled"
    TASK_APPROVED = "TASK_APPROVED", "Task Approved"
    RETURNED = "RETURNED", "Returned"
    REJECTED = "REJECTED", "Rejected"
    APPROVED = "APPROVED", "Approved"
    ACTUAL_EXPENSE_RECORDED = "ACTUAL_EXPENSE_RECORDED", "Actual Expense Recorded"
    CLOSED = "CLOSED", "Closed"


class TravelRequest(models.Model):
    travel_no = models.CharField(max_length=30, unique=True, blank=True)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="travel_requests",
    )
    request_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="travel_requests",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="travel_requests",
    )
    matched_rule = models.ForeignKey(
        "approvals.ApprovalRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_requests",
    )
    status = models.CharField(
        max_length=30,
        choices=TravelRequestStatus,
        default=TravelRequestStatus.DRAFT,
    )
    request_date = models.DateField(default=timezone.localdate)
    purpose = models.CharField(max_length=200)
    origin_city = models.CharField(max_length=100)
    destination_city = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(
        max_length=10,
        choices=CurrencyCode,
        default=CurrencyCode.USD,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "PS_A8_TR_HDR"
        verbose_name = "Travel Request"
        verbose_name_plural = "Travel Requests"
        ordering = ["-request_date", "travel_no"]

    def __str__(self):
        return f"{self.travel_no} - {self.purpose}"

    @classmethod
    def get_visible_queryset(cls, user):
        from .access import get_visible_travel_queryset_for_user
        return get_visible_travel_queryset_for_user(user)

    def can_user_view(self, user):
        from .access import user_can_view_travel
        return user_can_view_travel(user, self)

    def can_user_edit(self, user):
        from .access import user_can_edit_travel
        return user_can_edit_travel(user, self)

    def can_user_submit(self, user):
        from .access import user_can_submit_travel
        return user_can_submit_travel(user, self)

    def can_user_cancel(self, user):
        from .access import user_can_cancel_travel
        return user_can_cancel_travel(user, self)

    def can_user_close(self, user):
        from .access import user_can_close_travel
        return user_can_close_travel(user, self)

    def can_user_record_actual_expense(self, user):
        from .access import user_can_record_actual_expense_travel
        return user_can_record_actual_expense_travel(user, self)

    def can_user_manage_attachments(self, user):
        from .access import user_can_manage_travel_attachment
        return user_can_manage_travel_attachment(user, self)

    def resolve_fixed_step_assignee(self, step):
        # 1. If the rule step directly specifies a user, use that first.
        if getattr(step, "approver_user_id", None):
            return step.approver_user

        # 2. Department manager approval:
        #    First use the step's approver_department if configured;
        #    otherwise fall back to this request's department.
        department = getattr(step, "approver_department", None) or self.request_department
        if not department:
            return None

        # Replace the field name below if your Department model uses a different one.
        # Common names would be: manager / department_manager
        manager = getattr(department, "manager", None)
        if manager:
            return manager

        manager = getattr(department, "department_manager", None)
        if manager:
            return manager

        return None

    def _dedupe_users(self, users):
        unique_users = {}
        for user in users:
            if user and user.id not in unique_users:
                unique_users[user.id] = user
        return list(unique_users.values())

    def resolve_step_candidates(self, step):
        from accounts.models import UserDepartment
        from common.choices import ApproverType, DepartmentType

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

    @classmethod
    def generate_next_travel_no(cls, request_date=None):
        sequence_date = request_date or timezone.localdate()

        with transaction.atomic():
            sequence, _ = TravelRequestNumberSequence.objects.select_for_update().get_or_create(
                sequence_date=sequence_date,
                defaults={"last_number": 0},
            )
            sequence.last_number += 1
            sequence.save(update_fields=["last_number"])

            return f"TR{sequence_date.strftime('%Y%m%d')}-{sequence.last_number:04d}"

    def clean(self):
        errors = {}

        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be earlier than start date."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.travel_no:
            effective_date = self.request_date or timezone.localdate()
            self.travel_no = self.generate_next_travel_no(effective_date)

        self.full_clean()
        super().save(*args, **kwargs)

    def get_estimated_expense_total(self):
        total = self.estimated_expense_lines.aggregate(total=Sum("estimated_amount"))["total"]
        return total or Decimal("0.00")

    def refresh_estimated_total(self, commit=True):
        self.estimated_total = self.get_estimated_expense_total()
        if commit:
            self.save(update_fields=["estimated_total"])
        return self.estimated_total

    def get_actual_total(self):
        total = self.actual_expense_lines.aggregate(total=Sum("actual_amount"))["total"]
        return total or Decimal("0.00")

    def get_project_available_budget(self):
        if not self.project_id:
            return Decimal("0.00")
        return self.project.get_available_amount()

    def get_reserved_remaining_amount(self):
        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        return reserve_total - release_total

    def refresh_actual_total(self, commit=True):
        self.actual_total = self.get_actual_total()
        if commit:
            self.save(update_fields=["actual_total"])
        return self.actual_total

    def get_actual_expense_total(self):
        total = self.actual_expense_lines.aggregate(total=Sum("actual_amount"))["total"]
        return total or Decimal("0.00")



    @transaction.atomic
    def record_actual_expense(
            self,
            expense_type,
            expense_date,
            actual_amount,
            acting_user=None,
            estimated_expense_line=None,
            currency="",
            vendor_name="",
            reference_no="",
            expense_location="",
            notes="",
        ):
        allowed_statuses = [
            TravelRequestStatus.APPROVED,
            TravelRequestStatus.IN_TRIP,
            TravelRequestStatus.EXPENSE_PENDING,
            TravelRequestStatus.EXPENSE_SUBMITTED,
        ]

        if self.status not in allowed_statuses:
            raise ValidationError(
                "Actual expenses can only be recorded when the travel request is "
                "Approved, In Trip, Expense Pending, or Expense Submitted."
            )
        next_line_no = (
            self.actual_expense_lines.aggregate(max_line_no=Max("line_no"))["max_line_no"] or 0
        ) + 1

        actual_line = TravelActualExpenseLine.objects.create(
            travel_request=self,
            line_no=next_line_no,
            expense_type=expense_type,
            expense_date=expense_date,
            actual_amount=actual_amount,
            currency=currency or self.currency,
            vendor_name=vendor_name,
            reference_no=reference_no,
            expense_location=expense_location,
            notes=notes,
            estimated_expense_line=estimated_expense_line,
            created_by=acting_user,
        )

        reserved_remaining = self.get_reserved_remaining_amount()
        extra_needed = actual_amount - reserved_remaining if actual_amount > reserved_remaining else Decimal("0.00")

        if extra_needed > 0:
            available_budget = self.project.get_available_amount()
            if extra_needed > available_budget:
                raise ValidationError(
                    f"Insufficient project budget for overspend. Extra needed is {extra_needed}, "
                    f"but available budget is {available_budget}."
                )

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.TRAVEL,
            source_id=self.id,
            amount=actual_amount,
            notes=f"Budget consumed by actual expense of {self.travel_no}",
            created_by=acting_user,
        )

        amount_to_release = min(actual_amount, reserved_remaining)
        if amount_to_release > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                amount=amount_to_release,
                notes=f"Reserved budget converted to actual expense for {self.travel_no}",
                created_by=acting_user,
            )

        self.refresh_actual_total(commit=True)

        from_status = self.status

        self.refresh_actual_total(commit=False)

        if self.status == TravelRequestStatus.APPROVED:
            self.status = TravelRequestStatus.EXPENSE_PENDING

        self.save(update_fields=["actual_total", "status"])

        self._add_history(
            action_type=TravelRequestHistoryActionType.ACTUAL_EXPENSE_RECORDED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=(
                f"Actual expense recorded: {currency} {actual_amount}. "
                f"Expense type: {expense_type}."
            ),
        )

        if self.status in [TravelRequestStatus.APPROVED, TravelRequestStatus.IN_TRIP]:
            self.status = TravelRequestStatus.EXPENSE_PENDING
            self.save(update_fields=["status"])

        self._add_history(
            action_type=TravelRequestHistoryActionType.ACTUAL_EXPENSE_RECORDED,
            from_status=self.status,
            to_status=self.status,
            acting_user=acting_user,
            comment=(
                f"Actual expense recorded: {self.currency} {actual_amount}. "
                f"Estimated link: {estimated_expense_line.line_no if estimated_expense_line else '-'}. "
            ),
        )

        return actual_line

    def refresh_actual_total(self, commit=True):
        self.actual_total = self.get_actual_expense_total()
        if commit:
            self.save(update_fields=["actual_total"])
        return self.actual_total

    def _add_history(self, action_type, from_status="", to_status="", acting_user=None, comment=""):
        TravelRequestHistory.objects.create(
            travel_request=self,
            action_type=action_type,
            from_status=from_status or "",
            to_status=to_status or "",
            acting_user=acting_user,
            comment=comment or "",
        )

    def _add_content_audit(
        self,
        action_type,
        changed_by=None,
        section="",
        field_name="",
        line_no=None,
        old_value="",
        new_value="",
        notes="",
    ):
        TravelRequestContentAudit.objects.create(
            travel_request=self,
            action_type=action_type,
            section=section or "",
            field_name=field_name or "",
            line_no=line_no,
            old_value="" if old_value is None else str(old_value),
            new_value="" if new_value is None else str(new_value),
            notes=notes or "",
            changed_by=changed_by,
        )

    def get_approval_tasks_queryset(self):
        content_type = ContentType.objects.get_for_model(TravelRequest)
        return ApprovalTask.objects.filter(
            request_content_type=content_type,
            request_object_id=self.id,
        ).order_by("step_no", "id")

    def get_current_task(self):
        return self.get_approval_tasks_queryset().filter(
            status__in=[ApprovalTaskStatus.POOL, ApprovalTaskStatus.PENDING]
        ).order_by("step_no", "id").first()

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
        total_count = self.get_approval_tasks_queryset().count()
        approved_count = self.get_approval_tasks_queryset().filter(
            status=ApprovalTaskStatus.APPROVED
        ).count()
        return f"{approved_count} / {total_count}"

    @transaction.atomic
    def submit(self, acting_user):

        if self.project_id:
            if hasattr(self.project, "is_open") and not self.project.is_open():
                raise ValidationError("Only open projects can be linked to travel requests.")

        if self.status not in [TravelRequestStatus.DRAFT, TravelRequestStatus.RETURNED]:
            raise ValidationError("Only draft or returned travel requests can be submitted.")

        if not self.itineraries.exists():
            raise ValidationError("At least one itinerary line is required before submit.")

        if not self.estimated_expense_lines.exists():
            raise ValidationError("At least one estimated expense line is required before submit.")

        self.refresh_estimated_total(commit=True)

        available_budget = self.get_project_available_budget()
        if self.estimated_total > available_budget:
            raise ValidationError(
                f"Insufficient project budget. Available budget is {available_budget}, "
                f"but this travel request needs {self.estimated_total}."
            )

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.TRAVEL,
            source_id=self.id,
            amount=self.estimated_total,
            notes=f"Budget reserved by submitting {self.travel_no}",
            created_by=acting_user,
        )

        matched_rule = (
            ApprovalRule.objects.filter(
                is_active=True,
                request_type=RequestType.TRAVEL,
            )
            .filter(
                Q(department=self.request_department) | Q(department__isnull=True)
            )
            .order_by("priority", "rule_code", "id")
            .first()
        )

        if not matched_rule:
            raise ValidationError("No active approval rule found for this travel request.")

        self.get_approval_tasks_queryset().delete()

        content_type = ContentType.objects.get_for_model(type(self))
        steps = matched_rule.steps.filter(is_active=True).order_by("step_no", "id")

        if not steps.exists():
            raise ValidationError("The matched approval rule has no active steps.")

        created_count = 0
        first_task = None

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
                    request_content_type=content_type,
                    request_object_id=self.id,
                    rule=matched_rule,
                    step=step,
                    step_no=step.step_no,
                    step_name=step.step_name,
                    status=task_status,
                    assigned_user=None,
                )

                ApprovalTaskCandidate.objects.bulk_create(
                    [ApprovalTaskCandidate(task=task, user=user) for user in candidates]
                )

                if is_first_step:
                    first_task = task

            else:
                assigned_user = self.resolve_fixed_step_assignee(step) if is_first_step else None
                if is_first_step and not assigned_user:
                    raise ValidationError(
                        f"Unable to resolve approver for step {step.step_no} - {step.step_name}."
                    )

                task_status = ApprovalTaskStatus.PENDING if is_first_step else ApprovalTaskStatus.WAITING

                task = ApprovalTask.objects.create(
                    request_content_type=content_type,
                    request_object_id=self.id,
                    rule=matched_rule,
                    step=step,
                    step_no=step.step_no,
                    step_name=step.step_name,
                    assigned_user=assigned_user,
                    status=task_status,
                )

                if is_first_step:
                    first_task = task

            created_count += 1

        from_status = self.status
        self.status = TravelRequestStatus.PENDING_APPROVAL
        self.matched_rule = matched_rule
        self.save(update_fields=["status", "matched_rule", "estimated_total"])

        self._add_history(
            action_type=TravelRequestHistoryActionType.SUBMITTED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=f"{self.travel_no} submitted for approval.",
        )

        from travel.notifications import notify_tr_submitted
        from purchase.notifications import notify_current_task_activated

        transaction.on_commit(lambda: notify_tr_submitted(self))

        if first_task:
            transaction.on_commit(
                lambda task_id=first_task.id: notify_current_task_activated(
                    ApprovalTask.objects.get(pk=task_id)
                )
            )

    @transaction.atomic
    def mark_as_approved(self, acting_user=None, comment="", exclude_task_id=None):
        from_status = self.status
        self.status = TravelRequestStatus.APPROVED
        self.save(update_fields=["status"])

        self._add_history(
            action_type=TravelRequestHistoryActionType.APPROVED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.travel_no} fully approved.",
        )

        from travel.notifications import notify_tr_approved
        transaction.on_commit(lambda: notify_tr_approved(self))

    @transaction.atomic
    def mark_as_returned(self, acting_user=None, comment="", exclude_task_id=None):
        from_status = self.status
        self.status = TravelRequestStatus.RETURNED
        self.save(update_fields=["status"])

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                amount=reserved_remaining,
                notes=f"Budget released by returning {self.travel_no}",
                created_by=acting_user,
            )

        self._add_history(
            action_type=TravelRequestHistoryActionType.RETURNED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.travel_no} returned to requester.",
        )

        from travel.notifications import notify_tr_returned
        transaction.on_commit(lambda: notify_tr_returned(self, comment))

    @transaction.atomic
    def mark_as_rejected(self, acting_user=None, comment="", exclude_task_id=None):
        from_status = self.status
        self.status = TravelRequestStatus.REJECTED
        self.save(update_fields=["status"])

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                amount=reserved_remaining,
                notes=f"Budget released by rejecting {self.travel_no}",
                created_by=acting_user,
            )

        self._add_history(
            action_type=TravelRequestHistoryActionType.REJECTED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.travel_no} rejected.",
        )

        from travel.notifications import notify_tr_rejected
        transaction.on_commit(lambda: notify_tr_rejected(self, comment))

    @transaction.atomic
    def cancel(self, acting_user=None, comment=""):
        if self.status not in [TravelRequestStatus.PENDING_APPROVAL, TravelRequestStatus.APPROVED]:
            raise ValidationError("Only pending approval or approved travel requests can be cancelled.")

        from_status = self.status
        self.status = TravelRequestStatus.CANCELLED
        self.save(update_fields=["status"])

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                amount=reserved_remaining,
                notes=f"Budget released by cancelling {self.travel_no}",
                created_by=acting_user,
            )

        self._add_history(
            action_type=TravelRequestHistoryActionType.CANCELLED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.travel_no} cancelled.",
        )

    @transaction.atomic
    def close_request(self, acting_user=None, comment=""):
        if self.status not in [
            TravelRequestStatus.APPROVED,
            TravelRequestStatus.EXPENSE_PENDING,
            TravelRequestStatus.EXPENSE_SUBMITTED,
        ]:
            raise ValidationError("Only approved or expense-stage travel requests can be closed.")

        reserved_remaining = self.get_reserved_remaining_amount()
        if reserved_remaining > 0:
            ProjectBudgetEntry.objects.create(
                project=self.project,
                entry_type=BudgetEntryType.RELEASE,
                source_type=RequestType.TRAVEL,
                source_id=self.id,
                amount=reserved_remaining,
                notes=f"Unused reserved budget released by closing {self.travel_no}",
                created_by=acting_user,
            )

        from_status = self.status
        self.refresh_actual_total(commit=False)
        self.status = TravelRequestStatus.CLOSED
        self.save(update_fields=["actual_total", "status"])

        self._add_history(
            action_type=TravelRequestHistoryActionType.CLOSED,
            from_status=from_status,
            to_status=self.status,
            acting_user=acting_user,
            comment=comment or f"{self.travel_no} closed.",
        )

        from travel.notifications import notify_tr_closed
        transaction.on_commit(lambda: notify_tr_closed(self, comment))

    def get_actual_total(self):
        total = self.actual_expense_lines.aggregate(total=Sum("actual_amount"))["total"]
        return total or Decimal("0.00")

    def refresh_actual_total(self, commit=True):
        self.actual_total = self.get_actual_total()
        if commit:
            self.save(update_fields=["actual_total"])
        return self.actual_total

class TravelAttachmentType(models.TextChoices):
    ITINERARY = "ITINERARY", "Itinerary"
    BOOKING = "BOOKING", "Booking Confirmation"
    HOTEL = "HOTEL", "Hotel Document"
    INVITATION = "INVITATION", "Invitation"
    VISA = "VISA", "Visa Support"
    OTHER = "OTHER", "Other"

def travel_attachment_upload_to(instance, filename):
    travel_no = instance.travel_request.travel_no or f"travel_{instance.travel_request_id}"
    return f"travel_attachments/{travel_no}/{filename}"

class TravelRequestAttachment(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    document_type = models.CharField(
        max_length=20,
        choices=TravelAttachmentType,
        default=TravelAttachmentType.OTHER,
    )
    title = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to=travel_attachment_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_request_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_TR_ATT"
        verbose_name = "Travel Request Attachment"
        verbose_name_plural = "Travel Request Attachments"
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.travel_request.travel_no} / {self.title or self.filename}"

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

class TravelItinerary(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="itineraries",
    )
    line_no = models.PositiveIntegerField()
    trip_date = models.DateField()
    from_city = models.CharField(max_length=100)
    to_city = models.CharField(max_length=100)
    transport_type = models.CharField(
        max_length=30,
        choices=TravelTransportType,
        default=TravelTransportType.AIR,
    )
    departure_time = models.TimeField(null=True, blank=True)
    arrival_time = models.TimeField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "PS_A8_TR_ITN"
        verbose_name = "Travel Itinerary"
        verbose_name_plural = "Travel Itineraries"
        ordering = ["travel_request", "line_no"]
        unique_together = ("travel_request", "line_no")

    def __str__(self):
        return f"{self.travel_request.travel_no} / Itinerary {self.line_no}"

    def clean(self):
        errors = {}

        if (
            self.travel_request_id
            and self.trip_date
            and self.travel_request.start_date
            and self.travel_request.end_date
        ):
            if self.trip_date < self.travel_request.start_date or self.trip_date > self.travel_request.end_date:
                errors["trip_date"] = "Trip date must fall within the travel request date range."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TravelEstimatedExpenseLine(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="estimated_expense_lines",
    )
    line_no = models.PositiveIntegerField()
    expense_type = models.CharField(
        max_length=30,
        choices=TravelExpenseType,
    )
    location_mode = models.CharField(
        max_length=20,
        choices=TravelLocationMode,
    )
    expense_date = models.DateField()
    estimated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(
    max_length=10,
    choices=CurrencyCode,
    default=CurrencyCode.USD,
    )

    from_location = models.CharField(max_length=100, blank=True, default="")
    to_location = models.CharField(max_length=100, blank=True, default="")
    departure_dt = models.DateTimeField(null=True, blank=True)
    arrival_dt = models.DateTimeField(null=True, blank=True)

    expense_location = models.CharField(max_length=100, blank=True, default="")
    checkin_date = models.DateField(null=True, blank=True)
    checkout_date = models.DateField(null=True, blank=True)
    nights = models.PositiveIntegerField(default=0)

    policy_limit_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    over_limit_flag = models.BooleanField(default=False)
    receipt_required_flag = models.BooleanField(default=False)
    receipt_attached_flag = models.BooleanField(default=False)
    exception_reason = models.CharField(max_length=300, blank=True, default="")

    itinerary_line_no = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "PS_A8_TR_EST_LN"
        verbose_name = "Travel Estimated Expense Line"
        verbose_name_plural = "Travel Estimated Expense Lines"
        ordering = ["travel_request", "line_no"]
        unique_together = ("travel_request", "line_no")

    def __str__(self):
        return f"{self.travel_request.travel_no} / Expense {self.line_no}"

    def clean(self):
        errors = {}

        if self.estimated_amount is not None and self.estimated_amount <= 0:
            errors["estimated_amount"] = "Estimated amount must be greater than 0."

        if (
            self.travel_request_id
            and self.expense_date
            and self.travel_request.start_date
            and self.travel_request.end_date
        ):
            if self.expense_date < self.travel_request.start_date or self.expense_date > self.travel_request.end_date:
                errors["expense_date"] = "Expense date must fall within the travel request date range."

        derived_mode = get_location_mode_for_expense_type(self.expense_type)
        if not derived_mode:
            errors["expense_type"] = "Unsupported expense type."

        if derived_mode:
            self.location_mode = derived_mode

            if derived_mode == TravelLocationMode.TRANSIT:
                if not self.from_location:
                    errors["from_location"] = "From Location is required for transit expense."
                if not self.to_location:
                    errors["to_location"] = "To Location is required for transit expense."

            elif derived_mode == TravelLocationMode.STAY:
                if not self.expense_location:
                    errors["expense_location"] = "Expense Location is required for stay expense."
                if not self.checkin_date:
                    errors["checkin_date"] = "Check-in Date is required for stay expense."
                if not self.checkout_date:
                    errors["checkout_date"] = "Checkout Date is required for stay expense."
                elif self.checkout_date < self.checkin_date:
                    errors["checkout_date"] = "Checkout date cannot be earlier than check-in date."

            elif derived_mode == TravelLocationMode.LOCAL:
                if not self.expense_location:
                    errors["expense_location"] = "Expense Location is required for local expense."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        derived_mode = get_location_mode_for_expense_type(self.expense_type)
        if derived_mode:
            self.location_mode = derived_mode

        if self.location_mode == TravelLocationMode.TRANSIT:
            self.expense_location = ""
            self.checkin_date = None
            self.checkout_date = None
            self.nights = 0

        elif self.location_mode == TravelLocationMode.STAY:
            self.from_location = ""
            self.to_location = ""
            self.departure_dt = None
            self.arrival_dt = None

            if self.checkin_date and self.checkout_date and self.checkout_date >= self.checkin_date:
                self.nights = (self.checkout_date - self.checkin_date).days
            else:
                self.nights = 0

        elif self.location_mode == TravelLocationMode.LOCAL:
            self.from_location = ""
            self.to_location = ""
            self.departure_dt = None
            self.arrival_dt = None
            self.checkin_date = None
            self.checkout_date = None
            self.nights = 0

        self.full_clean()
        super().save(*args, **kwargs)

class TravelActualExpenseLine(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="actual_expense_lines",
    )
    line_no = models.PositiveIntegerField()
    expense_type = models.CharField(
        max_length=30,
        choices=TravelActualExpenseType,
    )
    expense_date = models.DateField()
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(
        max_length=10,
        choices=CurrencyCode,
        default=CurrencyCode.USD,
    )
    estimated_expense_line = models.ForeignKey(
        "travel.TravelEstimatedExpenseLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="actual_links",
    )
    purchase_request_line = models.ForeignKey(
        "purchase.PurchaseRequestLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_actual_links",
    )
    vendor_name = models.CharField(max_length=100, blank=True, default="")
    reference_no = models.CharField(max_length=100, blank=True, default="")
    expense_location = models.CharField(max_length=100, blank=True, default="")
    notes = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_actual_expense_lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_TR_ACT_LN"
        verbose_name = "Travel Actual Expense Line"
        verbose_name_plural = "Travel Actual Expense Lines"
        ordering = ["travel_request", "line_no"]
        unique_together = ("travel_request", "line_no")

    def __str__(self):
        return f"{self.travel_request.travel_no} / Actual {self.line_no}"

def clean(self):
    errors = {}

    if self.actual_amount is not None and self.actual_amount <= 0:
        errors["actual_amount"] = "Actual amount must be greater than 0."

    if self.travel_request_id and self.expense_date:
        if self.travel_request.start_date and self.expense_date < self.travel_request.start_date:
            errors["expense_date"] = "Expense date cannot be earlier than the travel start date."
        if self.travel_request.end_date and self.expense_date > self.travel_request.end_date:
            errors["expense_date"] = "Expense date cannot be later than the travel end date."

    if self.estimated_expense_line_id:
        if self.estimated_expense_line.travel_request_id != self.travel_request_id:
            errors["estimated_expense_line"] = (
                "Estimated expense line must belong to the same travel request."
            )

    if errors:
        raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class TravelRequestHistory(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    action_type = models.CharField(
        max_length=30,
        choices=TravelRequestHistoryActionType,
    )
    from_status = models.CharField(max_length=30, blank=True, default="")
    to_status = models.CharField(max_length=30, blank=True, default="")
    acting_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_request_history_entries",
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_TR_HIS"
        verbose_name = "Travel Request History"
        verbose_name_plural = "Travel Request Histories"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.travel_request.travel_no} / {self.action_type}"

class TravelRequestContentAudit(models.Model):
    travel_request = models.ForeignKey(
        TravelRequest,
        on_delete=models.CASCADE,
        related_name="content_audits",
    )
    action_type = models.CharField(
        max_length=30,
        choices=TravelRequestContentAuditActionType,
    )
    section = models.CharField(max_length=30, blank=True, default="")
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
        related_name="travel_request_content_audits",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PS_A8_TR_AUD"
        verbose_name = "Travel Request Content Audit"
        verbose_name_plural = "Travel Request Content Audits"
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.travel_request.travel_no} / {self.action_type} / {self.field_name or '-'}"