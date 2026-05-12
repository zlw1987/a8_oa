from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import ApproverType, RequestType, DepartmentType, BudgetEntryType
from projects.models import (
    BudgetAdjustmentRequest,
    BudgetAdjustmentRequestStatus,
    DepartmentGeneralProject,
    Project,
    ProjectBudgetEntry,
    ProjectMember,
    ProjectStatus,
    ProjectType,
)
from purchase.models import PurchaseRequest, PurchaseRequestLine
from travel.models import TravelRequest, TravelItinerary, TravelEstimatedExpenseLine




User = get_user_model()


class DepartmentGeneralProjectSetupTest(TestCase):
    def setUp(self):
        self.finance_admin = User.objects.create_user(
            username="dept_gen_fin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.requester = User.objects.create_user(username="dept_gen_req", password="testpass123")
        self.department = Department.objects.create(
            dept_code="D-GEN",
            dept_name="General Budget Dept",
            dept_type=DepartmentType.GENERAL,
        )
        self.other_department = Department.objects.create(
            dept_code="D-OTHER",
            dept_name="Other Dept",
            dept_type=DepartmentType.GENERAL,
        )
        UserDepartment.objects.create(user=self.requester, department=self.department, is_active=True)
        self.general_project = Project.objects.create(
            project_code="D-GEN-GENERAL-2026",
            project_name="General Budget 2026",
            owning_department=self.department,
            project_type=ProjectType.DEPARTMENT_GENERAL,
            budget_amount=Decimal("10000.00"),
            is_active=True,
        )

    def test_department_general_project_list_page_loads(self):
        self.client.force_login(self.finance_admin)
        response = self.client.get(reverse("projects:department_general_project_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Department General Budget Setup")

    def test_department_general_project_setup_can_be_created(self):
        self.client.force_login(self.finance_admin)
        response = self.client.post(
            reverse("projects:department_general_project_create"),
            {
                "department": self.department.id,
                "fiscal_year": "2026",
                "project": self.general_project.id,
                "budget_amount": "10000.00",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            DepartmentGeneralProject.objects.filter(
                department=self.department,
                fiscal_year=2026,
                project=self.general_project,
                is_active=True,
            ).exists()
        )

    def test_department_general_project_must_belong_to_department(self):
        other_project = Project.objects.create(
            project_code="D-OTHER-GENERAL-2026",
            project_name="Other General Budget 2026",
            owning_department=self.other_department,
            project_type=ProjectType.DEPARTMENT_GENERAL,
            budget_amount=Decimal("10000.00"),
            is_active=True,
        )

        setup = DepartmentGeneralProject(
            department=self.department,
            fiscal_year=2026,
            project=other_project,
            budget_amount=Decimal("10000.00"),
        )

        with self.assertRaisesMessage(ValidationError, "General project must belong to the selected department."):
            setup.full_clean()


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
        self.finance_admin = User.objects.create_user(
            username="finance_project_budget",
            password="testpass123",
            email="finance_project_budget@example.com",
            is_superuser=True,
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
        ProjectMember.objects.create(
            project=self.project,
            user=self.requester,
            is_active=True,
            added_by=self.manager,
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

    def test_project_list_shows_visible_project_for_requester(self):
        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.project_code)
        self.assertContains(response, self.project.project_name)
        self.assertContains(response, reverse("projects:project_detail", args=[self.project.id]))
        self.assertContains(response, reverse("projects:project_budget_ledger", args=[self.project.id]))

    def test_project_list_hides_project_from_unrelated_user(self):
        self.client.login(username="outsider_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.project.project_code)

    def test_project_detail_loads_for_related_requester(self):
        pr = self._create_purchase_with_budget_entries()
        tr = self._create_travel_with_budget_entries()

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_detail", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.project_code)
        self.assertContains(response, self.project.project_name)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, reverse("projects:project_budget_ledger", args=[self.project.id]))

    def test_project_detail_blocks_unrelated_user(self):
        self.client.login(username="outsider_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_detail", args=[self.project.id]))

        self.assertEqual(response.status_code, 404)

    def test_project_manager_can_submit_positive_budget_adjustment_request(self):
        self.project.project_manager = self.manager
        self.project.save(update_fields=["project_manager"])

        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_add_budget_adjustment", args=[self.project.id]),
            data={
                "amount": "1000.00",
                "reason": "Budget increase requested",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()

        self.assertEqual(self.project.get_adjustment_amount(), Decimal("0.00"))
        adjustment = BudgetAdjustmentRequest.objects.get(project=self.project)
        self.assertEqual(adjustment.status, BudgetAdjustmentRequestStatus.SUBMITTED)
        self.assertEqual(adjustment.amount, Decimal("1000.00"))
        self.assertFalse(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                entry_type=BudgetEntryType.ADJUST,
            ).exists()
        )

        self.client.login(username="finance_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_approve_budget_adjustment", args=[self.project.id, adjustment.id]),
            data={"comment": "Approved"},
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, BudgetAdjustmentRequestStatus.POSTED)
        self.assertEqual(self.project.get_adjustment_amount(), Decimal("1000.00"))
        self.assertEqual(self.project.get_effective_budget_amount(), Decimal("11000.00"))

    def test_project_manager_can_submit_negative_budget_adjustment_request(self):
        self.project.project_manager = self.manager
        self.project.save(update_fields=["project_manager"])

        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_add_budget_adjustment", args=[self.project.id]),
            data={
                "amount": "-500.00",
                "reason": "Budget reduction requested",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()

        self.assertEqual(self.project.get_adjustment_amount(), Decimal("0.00"))
        adjustment = BudgetAdjustmentRequest.objects.get(project=self.project)
        self.assertEqual(adjustment.amount, Decimal("-500.00"))

    def test_visible_but_unauthorized_user_cannot_add_budget_adjustment(self):
        self._create_purchase_with_budget_entries()

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_add_budget_adjustment", args=[self.project.id]),
            data={
                "amount": "300.00",
                "notes": "Unauthorized adjustment attempt",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                entry_type=BudgetEntryType.ADJUST,
                source_type=RequestType.PROJECT,
                source_id=self.project.id,
            ).count(),
            0,
        )

    def test_project_manager_can_create_project(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_create"),
            data={
                "project_code": "PJT-NEW-01",
                "project_name": "New Managed Project",
                "project_manager": self.manager.id,
                "owning_department": self.department.id,
                "budget_amount": "5000.00",
                "currency": "USD",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=90),
                "is_active": "on",
                "notes": "Created in regression test",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(project_code="PJT-NEW-01").exists())

    def test_project_manager_can_create_project(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_create"),
            data={
                "project_code": "PJT-NEW-01",
                "project_name": "New Managed Project",
                "project_manager": self.manager.id,
                "owning_department": self.department.id,
                "budget_amount": "5000.00",
                "currency": "USD",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=90),
                "status": "OPEN",
                "is_active": "on",
                "notes": "Created in regression test",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(project_code="PJT-NEW-01").exists())

    def test_non_manager_cannot_create_project(self):
        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_create"),
            data={
                "project_code": "PJT-NOPE-01",
                "project_name": "Unauthorized Project",
                "project_manager": self.requester.id,
                "owning_department": self.department.id,
                "budget_amount": "3000.00",
                "currency": "USD",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=60),
                "status": "OPEN",
                "is_active": "on",
                "notes": "Should not be created",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(project_code="PJT-NOPE-01").exists())

    def test_project_list_shows_create_link_for_manager(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("projects:project_create"))

    def test_project_list_hides_create_link_for_non_manager(self):
        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("projects:project_create"))

    def test_project_create_auto_adds_creator_and_project_manager_as_members(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_create"),
            data={
                "project_code": "PJT-MBR-01",
                "project_name": "Membership Auto Add Project",
                "project_manager": self.requester.id,
                "owning_department": self.department.id,
                "budget_amount": "5000.00",
                "currency": "USD",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=90),
                "status": "OPEN",
                "is_active": "on",
                "notes": "Membership auto add regression",
            },
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(project_code="PJT-MBR-01")
        self.assertEqual(project.created_by, self.manager)
        self.assertEqual(project.project_manager, self.requester)

        self.assertTrue(
            ProjectMember.objects.filter(
                project=project,
                user=self.manager,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            ProjectMember.objects.filter(
                project=project,
                user=self.requester,
                is_active=True,
            ).exists()
        )

    def test_project_create_auto_adds_creator_and_project_manager_as_members(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_create"),
            data={
                "project_code": "PJT-MBR-01",
                "project_name": "Membership Auto Add Project",
                "project_manager": self.requester.id,
                "owning_department": self.department.id,
                "budget_amount": "5000.00",
                "currency": "USD",
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=90),
                "status": "OPEN",
                "is_active": "on",
                "notes": "Membership auto add regression",
            },
        )

        self.assertEqual(response.status_code, 302)

        project = Project.objects.get(project_code="PJT-MBR-01")
        self.assertEqual(project.created_by, self.manager)
        self.assertEqual(project.project_manager, self.requester)

        self.assertTrue(
            ProjectMember.objects.filter(
                project=project,
                user=self.manager,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            ProjectMember.objects.filter(
                project=project,
                user=self.requester,
                is_active=True,
            ).exists()
        )

    def test_project_manager_can_add_and_remove_member(self):
        self.project.created_by = self.manager
        self.project.project_manager = self.manager
        self.project.status = ProjectStatus.OPEN
        self.project.save(update_fields=["created_by", "project_manager", "status"])

        ProjectMember.objects.get_or_create(
            project=self.project,
            user=self.manager,
            defaults={"is_active": True, "added_by": self.manager},
        )

        self.client.login(username="mgr_project_budget", password="testpass123")

        add_response = self.client.post(
            reverse("projects:project_add_member", args=[self.project.id]),
            data={"user": self.requester.id},
        )
        self.assertEqual(add_response.status_code, 302)
        self.assertTrue(
            ProjectMember.objects.filter(
                project=self.project,
                user=self.requester,
                is_active=True,
            ).exists()
        )

        membership = ProjectMember.objects.get(project=self.project, user=self.requester)

        remove_response = self.client.post(
            reverse("projects:project_remove_member", args=[self.project.id, membership.id]),
        )
        self.assertEqual(remove_response.status_code, 302)

        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_non_manager_member_cannot_add_project_member(self):
        self.project.created_by = self.manager
        self.project.project_manager = self.manager
        self.project.status = ProjectStatus.OPEN
        self.project.save(update_fields=["created_by", "project_manager", "status"])

        ProjectMember.objects.get_or_create(
            project=self.project,
            user=self.manager,
            defaults={"is_active": True, "added_by": self.manager},
        )
        ProjectMember.objects.get_or_create(
            project=self.project,
            user=self.requester,
            defaults={"is_active": True, "added_by": self.manager},
        )

        self.client.login(username="req_project_budget", password="testpass123")
        response = self.client.post(
            reverse("projects:project_add_member", args=[self.project.id]),
            data={"user": self.outsider.id},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProjectMember.objects.filter(
                project=self.project,
                user=self.outsider,
                is_active=True,
            ).exists()
        )

    def test_project_members_page_loads_for_manager(self):
        self.project.created_by = self.manager
        self.project.project_manager = self.manager
        self.project.save(update_fields=["created_by", "project_manager"])

        ProjectMember.objects.get_or_create(
            project=self.project,
            user=self.manager,
            defaults={"is_active": True, "added_by": self.manager},
        )

        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_members", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.project_code)
        self.assertContains(response, "Add User to Project")

    def test_project_budget_ledger_shows_source_and_meaning_columns(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_budget_ledger", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source")
        self.assertContains(response, "Meaning")

    def test_project_budget_ledger_shows_source_and_meaning_columns(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_budget_ledger", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source")
        self.assertContains(response, "Meaning")

    def test_project_budget_ledger_shows_project_adjust_row(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_budget_ledger", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budget Summary by Source Type")
        self.assertContains(response, "Adjusted")
        self.assertContains(response, "<td>Project</td>", html=True)

    def test_project_create_uses_currency_dropdown(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="currency"', html=False)
        self.assertContains(response, "<select", html=False)

    def test_project_budget_ledger_source_column_shows_summary_when_available(self):
        pr = PurchaseRequest.objects.create(
            title="Ledger Source Summary Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Ledger source summary test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Ledger Source Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

        pr.submit(acting_user=self.requester)

        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_budget_ledger", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, pr.title)

    def test_project_detail_shows_budget_meaning_section(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_detail", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budget Meaning")
        self.assertContains(response, "Effective Budget")
        self.assertContains(response, "Available Amount")

    def test_project_detail_recent_budget_entries_show_meaning_column(self):
        self.client.login(username="mgr_project_budget", password="testpass123")
        response = self.client.get(reverse("projects:project_detail", args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent Budget Entries")
        self.assertContains(response, "Meaning")
