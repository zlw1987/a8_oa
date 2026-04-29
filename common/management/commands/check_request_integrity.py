from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from common.choices import ApprovalTaskStatus, RequestStatus
from projects.models import Project
from purchase.models import PurchaseRequest
from travel.models import TravelRequest, TravelRequestStatus


ACTIVE_TASK_STATUSES = [
    ApprovalTaskStatus.WAITING,
    ApprovalTaskStatus.POOL,
    ApprovalTaskStatus.PENDING,
]


PURCHASE_TERMINAL_STATUSES = {
    RequestStatus.DRAFT,
    RequestStatus.RETURNED,
    RequestStatus.CANCELLED,
    RequestStatus.REJECTED,
    RequestStatus.CLOSED,
}

PURCHASE_SHOULD_HAVE_TASK_STATUSES = {
    RequestStatus.SUBMITTED,
    RequestStatus.PENDING,
    RequestStatus.APPROVED,
}


TRAVEL_TERMINAL_STATUSES = {
    TravelRequestStatus.DRAFT,
    TravelRequestStatus.RETURNED,
    TravelRequestStatus.CANCELLED,
    TravelRequestStatus.REJECTED,
    TravelRequestStatus.CLOSED,
}

TRAVEL_SHOULD_HAVE_TASK_STATUSES = {
    TravelRequestStatus.PENDING_APPROVAL,
    TravelRequestStatus.APPROVED,
    TravelRequestStatus.IN_TRIP,
    TravelRequestStatus.EXPENSE_PENDING,
    TravelRequestStatus.EXPENSE_SUBMITTED,
}


def _fmt_decimal(value):
    if value is None:
        return "0.00"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def check_purchase_request(pr):
    issues = []

    try:
        lines_total = pr.get_lines_total()
        if pr.estimated_total != lines_total:
            issues.append(
                f"ERROR Purchase {pr.pr_no}: estimated_total mismatch. "
                f"header={_fmt_decimal(pr.estimated_total)}, lines={_fmt_decimal(lines_total)}"
            )

        actual_total = (
            pr.actual_spend_entries.aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        method_actual_total = pr.get_actual_spent_total()
        if method_actual_total != actual_total:
            issues.append(
                f"ERROR Purchase {pr.pr_no}: actual_spent_total mismatch. "
                f"method={_fmt_decimal(method_actual_total)}, entries={_fmt_decimal(actual_total)}"
            )

        active_task_count = pr.approval_tasks.filter(
            status__in=ACTIVE_TASK_STATUSES
        ).count()

        if pr.status in PURCHASE_TERMINAL_STATUSES and active_task_count > 0:
            issues.append(
                f"ERROR Purchase {pr.pr_no}: terminal status {pr.status} but still has "
                f"{active_task_count} active approval task(s)"
            )

        if pr.status in PURCHASE_SHOULD_HAVE_TASK_STATUSES and pr.approval_tasks.count() == 0:
            issues.append(
                f"ERROR Purchase {pr.pr_no}: status {pr.status} but has no approval tasks"
            )

        reserved_remaining = pr.get_reserved_remaining_amount()
        if reserved_remaining < Decimal("0.00"):
            issues.append(
                f"ERROR Purchase {pr.pr_no}: reserved remaining is negative: "
                f"{_fmt_decimal(reserved_remaining)}"
            )

    except Exception as exc:
        issues.append(f"ERROR Purchase {pr.pr_no}: integrity check crashed: {exc}")

    return issues


def check_travel_request(tr):
    issues = []

    try:
        estimated_total = tr.get_estimated_expense_total()
        if tr.estimated_total != estimated_total:
            issues.append(
                f"ERROR Travel {tr.travel_no}: estimated_total mismatch. "
                f"header={_fmt_decimal(tr.estimated_total)}, lines={_fmt_decimal(estimated_total)}"
            )

        actual_total = (
            tr.actual_expense_lines.aggregate(total=Sum("actual_amount"))["total"]
            or Decimal("0.00")
        )
        method_actual_total = tr.get_actual_total()
        if method_actual_total != actual_total:
            issues.append(
                f"ERROR Travel {tr.travel_no}: actual_total mismatch. "
                f"header={_fmt_decimal(method_actual_total)}, lines={_fmt_decimal(actual_total)}"
            )

        active_task_count = tr.get_approval_tasks_queryset().filter(
            status__in=ACTIVE_TASK_STATUSES
        ).count()

        if tr.status in TRAVEL_TERMINAL_STATUSES and active_task_count > 0:
            issues.append(
                f"ERROR Travel {tr.travel_no}: terminal status {tr.status} but still has "
                f"{active_task_count} active approval task(s)"
            )

        if tr.status in TRAVEL_SHOULD_HAVE_TASK_STATUSES and tr.get_approval_tasks_queryset().count() == 0:
            issues.append(
                f"ERROR Travel {tr.travel_no}: status {tr.status} but has no approval tasks"
            )

        reserved_remaining = tr.get_reserved_remaining_amount()
        if reserved_remaining < Decimal("0.00"):
            issues.append(
                f"ERROR Travel {tr.travel_no}: reserved remaining is negative: "
                f"{_fmt_decimal(reserved_remaining)}"
            )

    except Exception as exc:
        issues.append(f"ERROR Travel {tr.travel_no}: integrity check crashed: {exc}")

    return issues


def check_project(project):
    issues = []

    try:
        available_amount = project.get_available_amount()
        if available_amount < Decimal("0.00"):
            issues.append(
                f"ERROR Project {project.project_code}: available amount is negative: "
                f"{_fmt_decimal(available_amount)}"
            )
    except Exception as exc:
        issues.append(
            f"ERROR Project {project.project_code}: integrity check crashed: {exc}"
        )

    return issues


class Command(BaseCommand):
    help = "Check Purchase / Travel / Project integrity and fail on dirty data."

    def handle(self, *args, **options):
        issues = []

        purchase_requests = list(PurchaseRequest.objects.all().order_by("id"))
        travel_requests = list(TravelRequest.objects.all().order_by("id"))
        projects = list(Project.objects.all().order_by("id"))

        for pr in purchase_requests:
            issues.extend(check_purchase_request(pr))

        for tr in travel_requests:
            issues.extend(check_travel_request(tr))

        for project in projects:
            issues.extend(check_project(project))

        for issue in issues:
            self.stdout.write(issue)

        self.stdout.write(
            f"Checked {len(purchase_requests)} purchase requests, "
            f"{len(travel_requests)} travel requests, "
            f"{len(projects)} projects"
        )

        if issues:
            self.stdout.write(f"Found {len(issues)} integrity issue(s)")
            raise CommandError("Integrity check failed.")

        self.stdout.write("OK: no integrity issues found.")