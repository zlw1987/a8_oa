from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core import mail
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from approvals.models import ApprovalTask
from travel.models import TravelRequest


from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import (
    ApprovalTaskStatus,
    ApproverType,
    RequestType,
    DepartmentType,
    RequestStatus,
)
from projects.models import Project
from purchase.models import PurchaseRequest, PurchaseRequestLine
from travel.models import TravelRequest, TravelItinerary, TravelEstimatedExpenseLine, TravelRequestStatus


User = get_user_model()


class ApprovalPagesSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="approver_test",
            password="testpass123",
            email="approver@example.com",
        )

    def test_my_tasks_page_loads(self):
        self.client.login(username="approver_test", password="testpass123")
        response = self.client.get(reverse("approvals:my_tasks"))
        self.assertEqual(response.status_code, 200)


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