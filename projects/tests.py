from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import ApproverType, RequestType, DepartmentType, BudgetEntryType
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseRequest, PurchaseRequestLine
from travel.models import TravelRequest, TravelItinerary, TravelEstimatedExpenseLine


User = get_user_model()


class ProjectBudgetLedgerRegressionTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_project_budget",
            password="testpass123",
            email="req_project_budget@example.com",
        )
        self.manager = User.objects.create_user(
            username="mgr_project_budget",
            password="testpass123",
            email="mgr_project_budget@example.com",
        )
        self.outsider = User.objects.create_user(
            username="outsider_project_budget",
            password="testpass123",
            email="outsider_project_budget@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-PROJ-01",
            dept_name="Project Dept",
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
            project_code="PJT-LEDGER-01",
            project_name="Ledger Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),
            is_active=True,
        )

        self.purchase_rule = ApprovalRule.objects.create(
            rule_code="PUR-LEDGER",
            rule_name="Purchase Ledger Rule",
            request_type=RequestType.PURCHASE,
            department=self.department,
            is_active=True,
            priority=1,
        )
        ApprovalRuleStep.objects.create(
            rule=self.purchase_rule,
            step_no=1,
            step_name="Department Manager Approval",
            approver_type=ApproverType.DEPARTMENT_MANAGER,
            is_active=True,
        )

        self.travel_rule = ApprovalRule.objects.create(
            rule_code="TRV-LEDGER",
            rule_name="Travel Ledger Rule",
            request_type=RequestType.TRAVEL,
            department=self.department,
            is_active=True,
            priority=1,
        )
        ApprovalRuleStep.objects.create(
            rule=self.travel_rule,
            step_no=1,
            step_name="Department Manager Approval",
            approver_type=ApproverType.DEPARTMENT_MANAGER,
            is_active=True,
        )

    def _create_purchase_with_budget_entries(self):
        pr = PurchaseRequest.objects.create(
            title="Ledger Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Ledger purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Monitor",
            quantity=Decimal("1"),
            unit_price=Decimal("600.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        task.approve(self.manager, comment="Approve purchase for ledger test")
        pr.refresh_from_db()

        pr.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("550.00"),
            acting_user=self.requester,
            vendor_name="Ledger Vendor",
            reference_no="LED-PR-001",
            notes="Ledger purchase spend",
        )
        pr.refresh_from_db()

        return pr

    def _create_travel_with_budget_entries(self):
        tr = TravelRequest.objects.create(
            purpose="Ledger Travel",
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

        TravelItinerary.objects.create(
            travel_request=tr,
            line_no=1,
            trip_date=tr.start_date,
            from_city="San Jose",
            to_city="Seattle",
            transport_type="AIR",
        )

        estimated_line = TravelEstimatedExpenseLine.objects.create(
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

        tr.submit(acting_user=self.requester)
        task = tr.get_current_task()
        task.approve(self.manager, comment="Approve travel for ledger test")
        tr.refresh_from_db()

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("450.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Ledger Travel Vendor",
            reference_no="LED-TR-001",
            expense_location="Seattle",
            notes="Ledger travel spend",
        )
        tr.refresh_from_db()

        return tr

    def test_project_budget_ledger_page_loads_for_related_requester(self):
        self._create_purchase_with_budget_entries()
        self._create_travel_with_budget_entries()

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(
            reverse("projects:project_budget_ledger", args=[self.project.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Budget Ledger")
        self.assertContains(response, self.project.project_code)
        self.assertContains(response, "Budget Ledger")

    def test_project_budget_ledger_shows_purchase_and_travel_entries_with_links(self):
        pr = self._create_purchase_with_budget_entries()
        tr = self._create_travel_with_budget_entries()

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(
            reverse("projects:project_budget_ledger", args=[self.project.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase")
        self.assertContains(response, "Travel")
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, reverse("purchase:pr_detail", args=[pr.id]))
        self.assertContains(response, reverse("travel:tr_detail", args=[tr.id]))

    def test_project_budget_ledger_blocks_unrelated_user(self):
        self._create_purchase_with_budget_entries()

        self.client.login(username="outsider_project_budget", password="testpass123")
        response = self.client.get(
            reverse("projects:project_budget_ledger", args=[self.project.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_project_budget_ledger_summary_matches_project_helpers(self):
        self._create_purchase_with_budget_entries()
        self._create_travel_with_budget_entries()

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(
            reverse("projects:project_budget_ledger", args=[self.project.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.project.budget_amount))
        self.assertContains(response, str(self.project.get_reserved_amount()))
        self.assertContains(response, str(self.project.get_consumed_amount()))
        self.assertContains(response, str(self.project.get_available_amount()))

        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                entry_type=BudgetEntryType.RESERVE,
                source_type=RequestType.PURCHASE,
            ).exists()
        )
        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                entry_type=BudgetEntryType.RESERVE,
                source_type=RequestType.TRAVEL,
            ).exists()
        )