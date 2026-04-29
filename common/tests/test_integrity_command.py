from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Department, UserDepartment
from common.choices import DepartmentType
from projects.models import Project, ProjectMember
from purchase.models import PurchaseRequest, PurchaseRequestLine
from travel.models import TravelRequest, TravelEstimatedExpenseLine


User = get_user_model()


class IntegrityCommandTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="integrity_manager",
            password="testpass123",
            email="integrity_manager@example.com",
        )
        self.requester = User.objects.create_user(
            username="integrity_requester",
            password="testpass123",
            email="integrity_requester@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-INTEGRITY",
            dept_name="Integrity Dept",
            dept_type=DepartmentType.GENERAL,
            manager=self.manager,
        )

        UserDepartment.objects.create(
            user=self.requester,
            department=self.department,
            is_active=True,
            can_approve=False,
        )

        self.requester.primary_department = self.department
        self.requester.save(update_fields=["primary_department"])

        self.project = Project.objects.create(
            project_code="PJT-INTEGRITY-01",
            project_name="Integrity Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            currency="USD",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            status="OPEN",
            is_active=True,
            created_by=self.manager,
            project_manager=self.manager,
        )

        ProjectMember.objects.create(
            project=self.project,
            user=self.requester,
            is_active=True,
            added_by=self.manager,
        )

    def test_integrity_command_passes_on_clean_data(self):
        out = StringIO()
        call_command("check_request_integrity", stdout=out)

        output = out.getvalue()
        self.assertIn("OK: no integrity issues found.", output)

    def test_integrity_command_fails_on_purchase_estimated_total_mismatch(self):
        pr = PurchaseRequest.objects.create(
            title="Broken Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Broken purchase total",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Broken Item",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00"),
        )

        pr.estimated_total = Decimal("999.00")
        pr.save(update_fields=["estimated_total"])

        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command("check_request_integrity", stdout=out)

        output = out.getvalue()
        self.assertIn(pr.pr_no, output)
        self.assertIn("estimated_total mismatch", output)
        self.assertIn("Integrity check failed", str(ctx.exception))

    def test_integrity_command_fails_on_travel_estimated_total_mismatch(self):
        tr = TravelRequest.objects.create(
            purpose="Broken Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
        )

        TravelEstimatedExpenseLine.objects.create(
            travel_request=tr,
            line_no=1,
            expense_type="HOTEL",
            expense_date=tr.start_date,
            estimated_amount=Decimal("500.00"),
            currency="USD",
            expense_location="Seattle",
            checkin_date=tr.start_date,
            checkout_date=tr.end_date,
        )

        tr.estimated_total = Decimal("1.00")
        tr.save(update_fields=["estimated_total"])

        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command("check_request_integrity", stdout=out)

        output = out.getvalue()
        self.assertIn(tr.travel_no, output)
        self.assertIn("estimated_total mismatch", output)
        self.assertIn("Integrity check failed", str(ctx.exception))