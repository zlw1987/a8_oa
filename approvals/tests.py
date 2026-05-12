from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core import mail
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from approvals.models import ApprovalDelegation, ApprovalTask,ApprovalNotificationLog, ApprovalNotificationType, ApprovalNotificationStatus
from approvals.dashboard import get_approval_summary_for_user
from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import (
    ApprovalTaskStatus,
    ApproverType,
    RequestType,
    DepartmentType,
    RequestStatus,
)
from projects.models import Project,ProjectBudgetEntry,BudgetEntryType
from purchase.models import PurchaseRequest, PurchaseRequestLine,PurchaseActualReviewStatus,PurchaseActualSpend
from travel.models import TravelRequest, TravelItinerary, TravelEstimatedExpenseLine, TravelRequestStatus,TravelActualReviewStatus


User = get_user_model()


class ApprovalDelegationWorkflowTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(username="deleg_req", password="testpass123")
        self.approver = User.objects.create_user(username="deleg_mgr", password="testpass123")
        self.delegate = User.objects.create_user(username="deleg_backup", password="testpass123")
        self.finance_admin = User.objects.create_user(
            username="deleg_admin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.department = Department.objects.create(
            dept_code="D-DEL",
            dept_name="Delegation Dept",
            dept_type=DepartmentType.GENERAL,
        )
        self.project = Project.objects.create(
            project_code="PJT-DEL",
            project_name="Delegation Project",
            owning_department=self.department,
            budget_amount=Decimal("1000.00"),
            is_active=True,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            title="Delegation PR",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            status=RequestStatus.SUBMITTED,
            request_date=date.today(),
            currency="USD",
            estimated_total=Decimal("100.00"),
            justification="Delegation test",
        )
        self.rule = ApprovalRule.objects.create(
            rule_code="DEL-RULE",
            rule_name="Delegation Rule",
            request_type=RequestType.PURCHASE,
            is_active=True,
        )
        self.step = ApprovalRuleStep.objects.create(
            rule=self.rule,
            step_no=1,
            step_name="Manager Approval",
            approver_type=ApproverType.SPECIFIC_USER,
            approver_user=self.approver,
            is_active=True,
        )
        self.task = ApprovalTask.objects.create(
            purchase_request=self.purchase_request,
            rule=self.rule,
            step=self.step,
            step_no=1,
            step_name="Manager Approval",
            assigned_user=self.approver,
            status=ApprovalTaskStatus.PENDING,
            due_at=timezone.now() - timedelta(days=3),
        )

    def test_active_delegate_can_approve_and_history_records_delegation(self):
        ApprovalDelegation.objects.create(
            original_approver=self.approver,
            delegate_user=self.delegate,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=1),
            created_by=self.approver,
        )

        self.task.approve(self.delegate, comment="Looks good.")

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ApprovalTaskStatus.APPROVED)
        self.assertEqual(self.task.acted_by, self.delegate)
        history = self.task.history_entries.order_by("-id").first()
        self.assertIn("Delegated approval on behalf of", history.comment)

    def test_expired_delegate_cannot_approve(self):
        ApprovalDelegation.objects.create(
            original_approver=self.approver,
            delegate_user=self.delegate,
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() - timedelta(days=1),
            created_by=self.approver,
        )

        with self.assertRaisesMessage(ValidationError, "Only the current assignee can approve this task."):
            self.task.approve(self.delegate)

    def test_admin_reassign_requires_reason_and_blocks_requester(self):
        with self.assertRaisesMessage(ValidationError, "Reassignment reason is required."):
            self.task.reassign(acting_user=self.finance_admin, new_assignee=self.delegate, reason="")

        with self.assertRaisesMessage(ValidationError, "Requester self-approval is not allowed."):
            self.task.reassign(acting_user=self.finance_admin, new_assignee=self.requester, reason="No self approval.")

    def test_process_approval_escalations_command_runs_dry_run(self):
        out = StringIO()
        call_command("process_approval_escalations", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertTrue(
            "Dry run completed." in output
            or "No escalated overdue approval tasks found." in output
        )

    def test_delegation_pages_render(self):
        self.client.force_login(self.approver)
        response = self.client.get(reverse("approvals:my_delegations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Delegations")

        response = self.client.get(reverse("approvals:delegation_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Delegation")

    def test_finance_admin_can_open_task_reassign_page(self):
        self.client.force_login(self.finance_admin)
        response = self.client.get(reverse("approvals:task_reassign", args=[self.task.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reassign Approval Task")


class ApprovalRuleAdminViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="rule_admin",
            email="rule_admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            email="normal_user@example.com",
            password="testpass123",
            is_staff=False,
        )
        self.department = Department.objects.create(
            dept_code="MIS",
            dept_name="Management Information Systems",
        )

    def _valid_rule_post_data(self):
        return {
            "rule_code": "PR-001",
            "rule_name": "Purchase Rule 001",
            "request_type": RequestType.PURCHASE,
            "department": str(self.department.id),
            "amount_from": "0.00",
            "amount_to": "10000.00",
            "requester_level": "",
            "specific_requester": "",
            "priority": "1",
            "is_active": "on",

            "steps-TOTAL_FORMS": "1",
            "steps-INITIAL_FORMS": "0",
            "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",

            "steps-0-step_no": "1",
            "steps-0-step_name": "Department Manager Approval",
            "steps-0-approver_type": ApproverType.DEPARTMENT_MANAGER,
            "steps-0-approver_user": "",
            "steps-0-approver_department": "",
            "steps-0-approver_level": "",
            "steps-0-is_required": "on",
            "steps-0-allow_self_skip": "",
            "steps-0-sla_days": "2",
            "steps-0-is_active": "on",
            "steps-0-DELETE": "",
        }

    def test_rule_list_page_loads_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("approvals:rule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval Rules")

    def test_rule_create_page_loads_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("approvals:rule_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Approval Rule")

    def test_non_staff_cannot_open_rule_pages(self):
        self.client.force_login(self.normal_user)

        response = self.client.get(reverse("approvals:rule_list"))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("approvals:rule_create"))
        self.assertEqual(response.status_code, 403)

    def test_rule_create_saves_valid_rule_and_step(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse("approvals:rule_create"),
            data=self._valid_rule_post_data(),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ApprovalRule.objects.count(), 1)
        self.assertEqual(ApprovalRuleStep.objects.count(), 1)

        rule = ApprovalRule.objects.first()
        self.assertEqual(rule.rule_code, "PR-001")
        self.assertEqual(rule.request_type, RequestType.PURCHASE)

        step = ApprovalRuleStep.objects.first()
        self.assertEqual(step.step_no, 1)
        self.assertEqual(step.step_name, "Department Manager Approval")

    def test_rule_form_blocks_invalid_amount_range(self):
        self.client.force_login(self.staff_user)
        payload = self._valid_rule_post_data()
        payload["amount_from"] = "2000.00"
        payload["amount_to"] = "1000.00"

        response = self.client.post(reverse("approvals:rule_create"), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amount From cannot be greater than Amount To.")
        self.assertEqual(ApprovalRule.objects.count(), 0)

    def test_general_fallback_rule_cannot_have_specific_filters(self):
        self.client.force_login(self.staff_user)
        payload = self._valid_rule_post_data()
        payload["is_general_fallback"] = "on"

        response = self.client.post(reverse("approvals:rule_create"), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "General fallback rule cannot be limited to a department.")
        self.assertEqual(ApprovalRule.objects.count(), 0)

    def test_purchase_rule_matching_uses_general_fallback_after_regular_rules_miss(self):
        project = Project.objects.create(
            project_code="PJT-FALLBACK",
            project_name="Fallback Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            is_active=True,
        )
        purchase_request = PurchaseRequest.objects.create(
            title="Fallback Match Purchase",
            requester=self.normal_user,
            request_department=self.department,
            project=project,
            request_date=date.today(),
            currency="USD",
            justification="Fallback rule test",
        )
        PurchaseRequestLine.objects.create(
            request=purchase_request,
            line_no=1,
            item_name="Fallback Item",
            quantity=Decimal("1"),
            unit_price=Decimal("250.00"),
        )
        ApprovalRule.objects.create(
            rule_code="PR-SMALL",
            rule_name="Small Purchase Rule",
            request_type=RequestType.PURCHASE,
            department=self.department,
            amount_from=Decimal("0.00"),
            amount_to=Decimal("100.00"),
            priority=1,
            is_active=True,
        )
        fallback_rule = ApprovalRule.objects.create(
            rule_code="PR-GENERAL",
            rule_name="General Purchase Fallback",
            request_type=RequestType.PURCHASE,
            is_general_fallback=True,
            priority=999,
            is_active=True,
        )

        self.assertEqual(purchase_request.resolve_approval_rule(), fallback_rule)

    def test_rule_formset_blocks_duplicate_step_no(self):
        self.client.force_login(self.staff_user)
        payload = self._valid_rule_post_data()
        payload["steps-TOTAL_FORMS"] = "2"

        payload["steps-1-step_no"] = "1"
        payload["steps-1-step_name"] = "Finance Approval"
        payload["steps-1-approver_type"] = ApproverType.FINANCE
        payload["steps-1-approver_user"] = ""
        payload["steps-1-approver_department"] = ""
        payload["steps-1-approver_level"] = ""
        payload["steps-1-is_required"] = "on"
        payload["steps-1-allow_self_skip"] = ""
        payload["steps-1-sla_days"] = "2"
        payload["steps-1-is_active"] = "on"
        payload["steps-1-DELETE"] = ""

        response = self.client.post(reverse("approvals:rule_create"), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Step No found: 1")
        self.assertEqual(ApprovalRule.objects.count(), 0)

    def test_rule_formset_blocks_non_continuous_active_step_numbers(self):
        self.client.force_login(self.staff_user)
        payload = self._valid_rule_post_data()
        payload["steps-TOTAL_FORMS"] = "2"

        payload["steps-1-step_no"] = "3"
        payload["steps-1-step_name"] = "Finance Approval"
        payload["steps-1-approver_type"] = ApproverType.FINANCE
        payload["steps-1-approver_user"] = ""
        payload["steps-1-approver_department"] = ""
        payload["steps-1-approver_level"] = ""
        payload["steps-1-is_required"] = "on"
        payload["steps-1-allow_self_skip"] = ""
        payload["steps-1-sla_days"] = "2"
        payload["steps-1-is_active"] = "on"
        payload["steps-1-DELETE"] = ""

        response = self.client.post(reverse("approvals:rule_create"), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active Step No values must be continuous starting from 1.")
        self.assertEqual(ApprovalRule.objects.count(), 0)

    def test_specific_user_step_requires_approver_user(self):
        self.client.force_login(self.staff_user)
        payload = self._valid_rule_post_data()
        payload["steps-0-approver_type"] = ApproverType.SPECIFIC_USER
        payload["steps-0-approver_user"] = ""

        response = self.client.post(reverse("approvals:rule_create"), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Specific User approver type requires Approver User.")
        self.assertEqual(ApprovalRule.objects.count(), 0)

    def test_rule_edit_updates_existing_rule(self):
        rule = ApprovalRule.objects.create(
            rule_code="TR-001",
            rule_name="Travel Rule 001",
            request_type=RequestType.TRAVEL,
            department=self.department,
            priority=1,
            is_active=True,
        )
        ApprovalRuleStep.objects.create(
            rule=rule,
            step_no=1,
            step_name="Department Manager Approval",
            approver_type=ApproverType.DEPARTMENT_MANAGER,
            sla_days=2,
            is_required=True,
            is_active=True,
        )

        self.client.force_login(self.staff_user)
        payload = {
            "rule_code": "TR-001",
            "rule_name": "Travel Rule Updated",
            "request_type": RequestType.TRAVEL,
            "department": str(self.department.id),
            "amount_from": "0.00",
            "amount_to": "5000.00",
            "requester_level": "",
            "specific_requester": "",
            "priority": "2",
            "is_active": "on",

            "steps-TOTAL_FORMS": "1",
            "steps-INITIAL_FORMS": "1",
            "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",

            "steps-0-id": str(rule.steps.first().id),
            "steps-0-step_no": "1",
            "steps-0-step_name": "Finance Approval",
            "steps-0-approver_type": ApproverType.FINANCE,
            "steps-0-approver_user": "",
            "steps-0-approver_department": "",
            "steps-0-approver_level": "",
            "steps-0-is_required": "on",
            "steps-0-allow_self_skip": "",
            "steps-0-sla_days": "3",
            "steps-0-is_active": "on",
            "steps-0-DELETE": "",
        }

        response = self.client.post(
            reverse("approvals:rule_edit", args=[rule.id]),
            data=payload,
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        rule.refresh_from_db()
        step = rule.steps.first()

        self.assertEqual(rule.rule_name, "Travel Rule Updated")
        self.assertEqual(rule.priority, 2)
        self.assertEqual(step.step_name, "Finance Approval")
        self.assertEqual(step.approver_type, ApproverType.FINANCE)
        self.assertEqual(step.sla_days, 3)


class ApprovalPagesSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="approver_test",
            password="testpass123",
            email="approver@example.com",
        )
        self.staff_user = User.objects.create_user(
            username="approval_rule_admin",
            password="testpass123",
            email="rule_admin@example.com",
            is_staff=True,
        )

    def test_my_tasks_page_loads(self):
        self.client.login(username="approver_test", password="testpass123")
        response = self.client.get(reverse("approvals:my_tasks"))
        self.assertEqual(response.status_code, 200)

    def test_staff_nav_shows_approval_rules_entry(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("approvals:rule_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval Rules")
        self.assertContains(response, reverse("approvals:rule_list"))


class ApprovalCrossRequestRegressionTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_cross",
            password="testpass123",
            email="req_cross@example.com",
        )
        self.manager = User.objects.create_user(
            username="mgr_cross",
            password="testpass123",
            email="mgr_cross@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-CROSS-01",
            dept_name="Cross Dept",
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
            project_code="PJT-CROSS-01",
            project_name="Cross Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            is_active=True,
        )

        self.purchase_rule = ApprovalRule.objects.create(
            rule_code="PUR-CROSS",
            rule_name="Purchase Cross Rule",
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
            rule_code="TRV-CROSS",
            rule_name="Travel Cross Rule",
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

    def _viewer_for_task(self, task):
        if task.assigned_user:
            return task.assigned_user

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        return candidate.user

    def _open_my_tasks(self, **params):
        self.client.force_login(self.pool_approver)
        return self.client.get(reverse("approvals:my_tasks"), params)

    def _create_purchase_and_submit(self):
        pr = PurchaseRequest.objects.create(
            title="Cross Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Cross request test purchase",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Keyboard",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()
        return pr

    def _create_travel_and_submit(self):
        tr = TravelRequest.objects.create(
            purpose="Cross Travel",
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

        tr.submit(acting_user=self.requester)
        tr.refresh_from_db()
        return tr

    def test_my_tasks_shows_purchase_and_travel_assigned_tasks(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        self.client.login(username="mgr_cross", password="testpass123")
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase")
        self.assertContains(response, "Travel")
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, reverse("purchase:pr_detail", args=[pr.id]))
        self.assertContains(response, reverse("travel:tr_detail", args=[tr.id]))


class ApprovalPoolRegressionTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_pool",
            password="testpass123",
            email="req_pool@example.com",
        )
        self.pool_approver = User.objects.create_user(
            username="pool_approver",
            password="testpass123",
            email="pool_approver@example.com",
        )
        self.department_manager = User.objects.create_user(
            username="dept_mgr_pool",
            password="testpass123",
            email="dept_mgr_pool@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-POOL-01",
            dept_name="Pool Dept",
            dept_type=DepartmentType.GENERAL,
            manager=self.department_manager,
        )

        UserDepartment.objects.create(
            user=self.requester,
            department=self.department,
            is_active=True,
            can_approve=False,
        )

        UserDepartment.objects.create(
            user=self.pool_approver,
            department=self.department,
            is_active=True,
            can_approve=True,
        )

        self.requester.primary_department = self.department
        self.requester.save(update_fields=["primary_department"])

        self.project = Project.objects.create(
            project_code="PJT-POOL-01",
            project_name="Pool Project",
            owning_department=self.department,
            budget_amount=Decimal("20000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            is_active=True,
        )

        self.purchase_rule = ApprovalRule.objects.create(
            rule_code="PUR-POOL",
            rule_name="Purchase Pool Rule",
            request_type=RequestType.PURCHASE,
            department=self.department,
            is_active=True,
            priority=1,
        )

        ApprovalRuleStep.objects.create(
            rule=self.purchase_rule,
            step_no=1,
            step_name="Department Pool Approval",
            approver_type=ApproverType.DEPARTMENT_APPROVER,
            is_active=True,
        )

        self.travel_rule = ApprovalRule.objects.create(
            rule_code="TRV-POOL",
            rule_name="Travel Pool Rule",
            request_type=RequestType.TRAVEL,
            department=self.department,
            is_active=True,
            priority=1,
        )

        ApprovalRuleStep.objects.create(
            rule=self.travel_rule,
            step_no=1,
            step_name="Department Pool Approval",
            approver_type=ApproverType.DEPARTMENT_APPROVER,
            is_active=True,
        )

    def _run_reminder_dry_run(self):
        out = StringIO()
        call_command("send_approval_overdue_reminders", "--dry-run", stdout=out)
        return out.getvalue()

    def _run_escalation_dry_run(self):
        out = StringIO()
        call_command("send_approval_escalations", "--dry-run", stdout=out)
        return out.getvalue()

    def _run_escalation_dry_run(self):
        out = StringIO()
        call_command("send_approval_escalations", "--dry-run", stdout=out)
        return out.getvalue()

    def _viewer_for_task(self, task):
        if task.assigned_user:
            return task.assigned_user

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        return candidate.user

    def _open_my_tasks(self, **params):
        self.client.force_login(self.pool_approver)
        return self.client.get(reverse("approvals:my_tasks"), params)

    def _create_purchase_and_submit(self):
        pr = PurchaseRequest.objects.create(
            title="Pool Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Pool regression purchase",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Docking Station",
            quantity=Decimal("1"),
            unit_price=Decimal("250.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()
        return pr

    def _create_travel_and_submit(self):
        tr = TravelRequest.objects.create(
            purpose="Pool Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=7),
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

        TravelEstimatedExpenseLine.objects.create(
            travel_request=tr,
            line_no=1,
            expense_type="HOTEL",
            expense_date=tr.start_date,
            estimated_amount=Decimal("450.00"),
            currency="USD",
            expense_location="Seattle",
            checkin_date=tr.start_date,
            checkout_date=tr.end_date,
        )

        tr.submit(acting_user=self.requester)
        tr.refresh_from_db()
        return tr

    def test_purchase_pool_claim_release_and_approve_regression(self):
        pr = self._create_purchase_and_submit()

        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertIsNone(task.assigned_user)
        self.assertTrue(task.candidates.filter(user=self.pool_approver, is_active=True).exists())

        self.client.login(username="pool_approver", password="testpass123")

        response = self.client.get(reverse("approvals:my_tasks"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)

        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        response = self.client.post(reverse("approvals:task_release", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertIsNone(task.assigned_user)

        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        response = self.client.post(
            reverse("approvals:task_approve", args=[task.id]),
            data={"comment": "Pool purchase approved"},
        )
        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(task.status, ApprovalTaskStatus.APPROVED)
        self.assertEqual(pr.status, RequestStatus.APPROVED)

    def test_travel_pool_claim_and_approve_regression(self):
        tr = self._create_travel_and_submit()

        task = tr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertIsNone(task.assigned_user)
        self.assertTrue(task.candidates.filter(user=self.pool_approver, is_active=True).exists())

        self.client.login(username="pool_approver", password="testpass123")

        response = self.client.get(reverse("approvals:my_tasks"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)

        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        response = self.client.post(
            reverse("approvals:task_approve", args=[task.id]),
            data={"comment": "Pool travel approved"},
        )
        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(task.status, ApprovalTaskStatus.APPROVED)
        self.assertEqual(tr.status, TravelRequestStatus.APPROVED)

    def test_purchase_pool_claim_and_return_regression(self):
        pr = self._create_purchase_and_submit()

        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertTrue(task.candidates.filter(user=self.pool_approver, is_active=True).exists())

        self.client.login(username="pool_approver", password="testpass123")

        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        response = self.client.post(
            reverse("approvals:task_return", args=[task.id]),
            data={"comment": "Returned in pool regression test"},
        )
        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.RETURNED)
        self.assertTrue(pr.can_user_edit(self.requester))
        self.assertIsNone(pr.get_current_task())

    def test_travel_pool_claim_and_reject_regression(self):
        tr = self._create_travel_and_submit()

        task = tr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertTrue(task.candidates.filter(user=self.pool_approver, is_active=True).exists())

        self.client.login(username="pool_approver", password="testpass123")

        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        response = self.client.post(
            reverse("approvals:task_reject", args=[task.id]),
            data={"comment": "Rejected in pool regression test"},
        )
        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.REJECTED)
        self.assertFalse(tr.can_user_edit(self.requester))
        self.assertIsNone(tr.get_current_task())

    def test_non_candidate_cannot_claim_pool_task(self):
        outsider = User.objects.create_user(
            username="outsider_pool",
            password="testpass123",
            email="outsider_pool@example.com",
        )

        pr = self._create_purchase_and_submit()
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        self.client.login(username="outsider_pool", password="testpass123")
        response = self.client.post(reverse("approvals:task_claim", args=[task.id]))

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertIsNone(task.assigned_user)

    def test_non_assignee_cannot_approve_pending_task(self):
        outsider = User.objects.create_user(
            username="outsider_pending",
            password="testpass123",
            email="outsider_pending@example.com",
        )

        pr = self._create_purchase_and_submit()
        task = pr.get_current_task()
        self.assertIsNotNone(task)

        self.client.login(username="pool_approver", password="testpass123")
        claim_response = self.client.post(reverse("approvals:task_claim", args=[task.id]))
        self.assertEqual(claim_response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.pool_approver)

        self.client.login(username="outsider_pending", password="testpass123")
        response = self.client.post(
            reverse("approvals:task_approve", args=[task.id]),
            data={"comment": "Unauthorized approve attempt"},
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        pr.refresh_from_db()

        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertNotEqual(pr.status, RequestStatus.APPROVED)

    def test_my_tasks_filter_form_preserves_selected_request_type(self):
        self.client.force_login(self.pool_approver)
        response = self.client.get(reverse("approvals:my_tasks"), {"request_type": "PURCHASE"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<option value="PURCHASE" selected>Purchase</option>',
            html=True,
        )

    def test_my_tasks_request_type_filter_changes_visible_results(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        response = self._open_my_tasks(request_type="PURCHASE")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, pr.title)
        self.assertNotContains(response, tr.travel_no)
        self.assertNotContains(response, tr.purpose)

    def test_my_tasks_requester_filter_changes_visible_results(self):
        other_requester = User.objects.create_user(
            username="req_pool_other",
            password="testpass123",
            email="req_pool_other@example.com",
        )

        UserDepartment.objects.create(
            user=other_requester,
            department=self.department,
            is_active=True,
            can_approve=False,
        )

        other_requester.primary_department = self.department
        other_requester.save(update_fields=["primary_department"])

        pr_self = self._create_purchase_and_submit()

        pr_other = PurchaseRequest.objects.create(
            title="Other Requester Purchase",
            requester=other_requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Other requester pool regression purchase",
        )

        PurchaseRequestLine.objects.create(
            request=pr_other,
            line_no=1,
            item_name="Other Requester Dock",
            quantity=Decimal("1"),
            unit_price=Decimal("275.00"),
        )

        pr_other.submit(acting_user=other_requester)
        pr_other.refresh_from_db()

        response = self._open_my_tasks(requester=str(self.requester.id))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr_self.pr_no)
        self.assertContains(response, pr_self.title)
        self.assertNotContains(response, pr_other.pr_no)
        self.assertNotContains(response, pr_other.title)

    def test_my_tasks_uses_request_neutral_column_labels(self):
        self.client.force_login(self.pool_approver)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request No")
        self.assertContains(response, "Request Status")
        self.assertContains(response, "Ownership")

    def test_my_tasks_shows_pool_task_ownership_label(self):
        self._create_purchase_and_submit()

        self.client.force_login(self.pool_approver)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pool task")

    def test_my_tasks_shows_due_status_for_open_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due Status")
        self.assertContains(response, "On Time")

    def test_my_tasks_shows_due_status_for_travel_task(self):
        tr = self._create_travel_and_submit()

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due Status")
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "On Time")

    def test_my_tasks_shows_overdue_for_travel_task(self):
        tr = self._create_travel_and_submit()

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        viewer = self._viewer_for_task(task)

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due Status")
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Overdue by")

    def test_my_tasks_orders_overdue_tasks_first(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        purchase_task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        travel_task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()

        self.assertIsNotNone(purchase_task)
        self.assertIsNotNone(travel_task)

        purchase_task.due_at = timezone.now() + timedelta(days=2)
        purchase_task.save(update_fields=["due_at"])

        travel_task.due_at = timezone.now() - timedelta(days=2)
        travel_task.save(update_fields=["due_at"])

        viewer = self._viewer_for_task(travel_task)
        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.find(tr.travel_no), content.find(pr.pr_no))

    def test_my_tasks_can_filter_by_due_state_overdue(self):
        tr = self._create_travel_and_submit()
        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()

        self.assertIsNotNone(task)
        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        viewer = self._viewer_for_task(task)
        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"), {"due_state": "overdue"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Overdue")

    def test_my_tasks_can_filter_by_due_state_on_time(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()

        self.assertIsNotNone(task)
        task.due_at = timezone.now() + timedelta(days=2)
        task.save(update_fields=["due_at"])

        viewer = self._viewer_for_task(task)
        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_tasks"), {"due_state": "on_time"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "On Time")

    def test_my_history_page_loads(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:my_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Approval History")

    def test_my_history_shows_acted_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        task.claim(viewer) if task.status == ApprovalTaskStatus.POOL else None
        task.approve(viewer, comment="Approved in history test")

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Approved in history test")
        self.assertContains(response, "Approved")

    def test_my_history_shows_acted_travel_task(self):
        tr = TravelRequest.objects.create(
            purpose="History Travel",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        task.claim(viewer) if task.status == ApprovalTaskStatus.POOL else None
        task.return_to_requester(viewer, comment="Returned in history test")

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Returned in history test")
        self.assertContains(response, "Returned")

    def test_my_history_shows_approved_purchase_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)
        task.approve(viewer, comment="Approved in history test")

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Approved in history test")
        self.assertContains(response, "Approved")

    def test_my_history_shows_returned_travel_task(self):
        tr = TravelRequest.objects.create(
            purpose="History Travel",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)
        task.return_to_requester(viewer, comment="Returned in history test")

        self.client.force_login(viewer)
        response = self.client.get(reverse("approvals:my_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Returned in history test")
        self.assertContains(response, "Returned")

    def test_my_history_can_filter_by_outcome_status_approved(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)
        task.approve(viewer, comment="Approved only filter test")

        self.client.force_login(viewer)
        response = self.client.get(
            reverse("approvals:my_history"),
            {"outcome_status": "APPROVED"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Approved")

    def test_my_history_can_filter_by_outcome_status_returned(self):
        tr = TravelRequest.objects.create(
            purpose="Returned Filter Travel",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)
        task.return_to_requester(viewer, comment="Returned only filter test")

        self.client.force_login(viewer)
        response = self.client.get(
            reverse("approvals:my_history"),
            {"outcome_status": "RETURNED"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Returned")

    def test_overdue_reminder_command_picks_up_pending_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        out = StringIO()
        call_command("send_approval_overdue_reminders", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertIn("Would send to", output)
        self.assertIn(pr.pr_no, output)

    def test_overdue_reminder_command_picks_up_pool_task(self):
        tr = TravelRequest.objects.create(
            purpose="Reminder Pool Travel",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        out = StringIO()
        call_command("send_approval_overdue_reminders", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertIn("Would send to", output)
        self.assertIn(tr.travel_no, output)

    def test_overdue_reminder_command_skips_completed_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)
        task.approve(viewer, comment="done")

        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        out = StringIO()
        call_command("send_approval_overdue_reminders", "--dry-run", stdout=out)
        output = out.getvalue()

        self.assertNotIn(pr.pr_no, output)

    def test_get_approval_summary_for_user_counts_assigned_and_pool_tasks(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        purchase_task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        travel_task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()

        self.assertIsNotNone(purchase_task)
        self.assertIsNotNone(travel_task)

        summary_user = self._viewer_for_task(travel_task)
        summary = get_approval_summary_for_user(summary_user)

        self.assertIn("assigned_count", summary)
        self.assertIn("pool_count", summary)
        self.assertIn("total_overdue_count", summary)

    def test_dashboard_shows_approval_summary_and_history_link(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval Summary")
        self.assertContains(response, "My Tasks")
        self.assertContains(response, "My Approval History")

    def test_escalation_command_skips_task_overdue_less_than_2_days(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=1)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertNotIn(pr.pr_no, output)

    def test_escalation_command_pending_task_includes_assigned_user_and_requester(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertIsNotNone(task.assigned_user)

        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertIn(pr.pr_no, output)
        self.assertIn(self.requester.email, output)
        self.assertIn(task.assigned_user.email, output)

    def test_escalation_command_pool_task_includes_candidates_and_requester(self):
        tr = self._create_travel_and_submit()

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        self.assertIsNotNone(candidate.user.email)

        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertIn(tr.travel_no, output)
        self.assertIn(self.requester.email, output)
        self.assertIn(candidate.user.email, output)

    def test_escalation_command_pool_task_includes_candidates_and_requester(self):
        tr = TravelRequest.objects.create(
            purpose="Escalation Pool Travel",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)

        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        self.assertIsNotNone(candidate.user.email)

        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertIn(tr.travel_no, output)
        self.assertIn(self.requester.email, output)
        self.assertIn(candidate.user.email, output)

    def test_escalation_command_skips_completed_task(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.approve(viewer, comment="completed")
        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertNotIn(pr.pr_no, output)

    def test_reminder_command_skips_task_with_recent_reminder(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.last_reminder_sent_at = timezone.now()
        task.save(update_fields=["due_at", "last_reminder_sent_at"])

        output = self._run_reminder_dry_run()

        self.assertNotIn(pr.pr_no, output)

    def test_reminder_command_allows_task_after_reminder_cooldown(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.last_reminder_sent_at = timezone.now() - timedelta(hours=25)
        task.save(update_fields=["due_at", "last_reminder_sent_at"])

        output = self._run_reminder_dry_run()

        self.assertIn(pr.pr_no, output)

    def test_escalation_command_skips_task_overdue_less_than_2_days(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=1)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertNotIn(pr.pr_no, output)

    def test_escalation_command_pending_task_includes_assigned_user_and_requester(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertIsNotNone(task.assigned_user)

        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertIn(pr.pr_no, output)
        self.assertIn(self.requester.email, output)
        self.assertIn(task.assigned_user.email, output)

    def test_escalation_command_pool_task_includes_candidates_and_requester(self):
        tr = self._create_travel_and_submit()
        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=tr.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        self.assertIsNotNone(candidate.user.email)

        task.due_at = timezone.now() - timedelta(days=3)
        task.save(update_fields=["due_at"])

        output = self._run_escalation_dry_run()

        self.assertIn(tr.travel_no, output)
        self.assertIn(self.requester.email, output)
        self.assertIn(candidate.user.email, output)

    def test_escalation_command_skips_task_with_recent_escalation(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=3)
        task.last_escalation_sent_at = timezone.now()
        task.save(update_fields=["due_at", "last_escalation_sent_at"])

        output = self._run_escalation_dry_run()

        self.assertNotIn(pr.pr_no, output)

    def test_reminder_command_dry_run_creates_notification_log(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.last_reminder_sent_at = None
        task.save(update_fields=["due_at", "last_reminder_sent_at"])

        call_command("send_approval_overdue_reminders", "--dry-run")

        self.assertTrue(
            ApprovalNotificationLog.objects.filter(
                task=task,
                notification_type=ApprovalNotificationType.REMINDER,
                status=ApprovalNotificationStatus.DRY_RUN,
            ).exists()
        )

    def test_escalation_command_dry_run_creates_notification_log(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=3)
        task.last_escalation_sent_at = None
        task.save(update_fields=["due_at", "last_escalation_sent_at"])

        call_command("send_approval_escalations", "--dry-run")

        self.assertTrue(
            ApprovalNotificationLog.objects.filter(
                task=task,
                notification_type=ApprovalNotificationType.ESCALATION,
                status=ApprovalNotificationStatus.DRY_RUN,
            ).exists()
        )

    def test_reminder_command_respects_cooldown_and_does_not_create_new_log(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.last_reminder_sent_at = timezone.now()
        task.save(update_fields=["due_at", "last_reminder_sent_at"])

        before_count = ApprovalNotificationLog.objects.count()
        call_command("send_approval_overdue_reminders", "--dry-run")
        after_count = ApprovalNotificationLog.objects.count()

        self.assertEqual(before_count, after_count)

    def test_purchase_detail_shows_notification_log_entry_after_reminder_dry_run(self):
        pr = self._create_purchase_and_submit()
        task = ApprovalTask.objects.filter(purchase_request=pr).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        viewer = self._viewer_for_task(task)
        if task.status == ApprovalTaskStatus.POOL:
            task.claim(viewer)

        task.due_at = timezone.now() - timedelta(days=2)
        task.last_reminder_sent_at = None
        task.save(update_fields=["due_at", "last_reminder_sent_at"])

        call_command("send_approval_overdue_reminders", "--dry-run")

        self.client.force_login(self.requester)
        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Activity")
        self.assertContains(response, "Reminder")
        self.assertContains(response, "Dry Run")

    def test_accounting_review_queue_page_loads(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:accounting_review_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accounting Review Queue")

    def test_accounting_review_queue_page_loads(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:accounting_review_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accounting Review Queue")

    def test_accounting_review_queue_shows_purchase_pending_review_item(self):
        pr = PurchaseRequest.objects.create(
            title="Purchase Review Queue",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="test",
            estimated_total=Decimal("100.00"),
            status=RequestStatus.APPROVED,
            is_over_estimate=True,
            actual_review_status=PurchaseActualReviewStatus.PENDING_REVIEW,
        )

        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:accounting_review_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Pending Review")

    def test_accounting_review_queue_shows_travel_pending_review_item(self):
        tr = TravelRequest.objects.create(
            purpose="Travel Review Queue",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.APPROVED,
            estimated_total=Decimal("100.00"),
            actual_total=Decimal("130.00"),
            is_over_estimate=True,
            actual_review_status=TravelActualReviewStatus.PENDING_REVIEW,
        )

        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:accounting_review_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Pending Review")

    def test_variance_exception_report_page_loads(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:variance_exception_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Variance / Exception Report")

    def test_variance_exception_report_shows_purchase_item(self):
        pr = PurchaseRequest.objects.create(
            title="Purchase Variance Report",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="test",
            estimated_total=Decimal("100.00"),
            status=RequestStatus.APPROVED,
            is_over_estimate=True,
            actual_review_status=PurchaseActualReviewStatus.PENDING_REVIEW,
        )

        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            amount=Decimal("100.00"),
            notes="reserve",
            created_by=self.requester,
        )

        PurchaseActualSpend.objects.create(
            purchase_request=pr,
            spend_date=date.today(),
            amount=Decimal("130.00"),
            currency="USD",
            created_by=self.requester,
        )

        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:variance_exception_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Pending Review")

    def test_variance_exception_report_shows_travel_item(self):
        tr = TravelRequest.objects.create(
            purpose="Travel Variance Report",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.APPROVED,
            estimated_total=Decimal("100.00"),
            actual_total=Decimal("130.00"),
            is_over_estimate=True,
            actual_review_status=TravelActualReviewStatus.PENDING_REVIEW,
        )

        self.client.force_login(self.requester)
        response = self.client.get(reverse("approvals:variance_exception_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, "Pending Review")

    def test_variance_exception_report_can_filter_by_review_status(self):
        pr = PurchaseRequest.objects.create(
            title="Approved Variance Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="test",
            estimated_total=Decimal("100.00"),
            status=RequestStatus.APPROVED,
            is_over_estimate=True,
            actual_review_status=PurchaseActualReviewStatus.APPROVED_TO_PROCEED,
        )

        self.client.force_login(self.requester)
        response = self.client.get(
            reverse("approvals:variance_exception_report"),
            {"review_status": "APPROVED_TO_PROCEED"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, "Approved to Proceed")
