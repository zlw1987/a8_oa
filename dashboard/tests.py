from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import ApproverType, DepartmentType, RequestType
from projects.models import DepartmentGeneralProject, Project, ProjectType
from purchase.models import PurchaseRequest, PurchaseRequestLine
from travel.models import TravelRequest, TravelItinerary, TravelEstimatedExpenseLine


User = get_user_model()


class DashboardSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dashboard_user",
            password="testpass123",
            email="dashboard@example.com",
        )

        self.manager = User.objects.create_user(
            username="dashboard_manager",
            password="testpass123",
            email="dashboard_manager@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-DASH-NAV-01",
            dept_name="Dashboard Nav Dept",
            dept_type=DepartmentType.GENERAL,
            manager=self.manager,
        )

    def test_dashboard_home_loads(self):
        self.client.login(username="dashboard_user", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_language_switcher_renders_and_set_language_endpoint_exists(self):
        self.client.login(username="dashboard_user", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("set_language"))
        self.assertContains(response, "English")
        self.assertContains(response, "中文")

        switch_response = self.client.post(
            reverse("set_language"),
            {"language": "zh-hans", "next": reverse("dashboard:home")},
        )
        self.assertEqual(switch_response.status_code, 302)
        zh_response = self.client.get(reverse("dashboard:home"))
        self.assertContains(zh_response, "仪表板")

    def test_dashboard_renders_chinese_shell_when_requested(self):
        self.client.login(username="dashboard_user", password="testpass123")
        response = self.client.get(reverse("dashboard:home"), HTTP_ACCEPT_LANGUAGE="zh-hans")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "仪表板")
        self.assertContains(response, "审批摘要")

    def test_dashboard_nav_shows_projects_link_for_authenticated_user(self):
        self.client.login(username="dashboard_user", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("projects:project_list"))
        self.assertNotContains(response, reverse("projects:project_create"))

    def test_dashboard_nav_shows_new_project_link_for_department_manager(self):
        self.client.login(username="dashboard_manager", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("projects:project_list"))
        self.assertContains(response, reverse("projects:project_create"))

    def test_system_setup_uses_custom_user_admin_url(self):
        admin_user = User.objects.create_superuser(
            username="dashboard_sys_admin",
            password="testpass123",
            email="dashboard_sys_admin@example.com",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("dashboard:system_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:accounts_user_changelist"))
        self.assertContains(response, reverse("admin:auth_group_changelist"))

    def test_system_setup_uses_business_currency_setup_urls(self):
        admin_user = User.objects.create_superuser(
            username="dashboard_currency_admin",
            password="testpass123",
            email="dashboard_currency_admin@example.com",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("dashboard:system_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("finance:currency_list"))
        self.assertContains(response, reverse("finance:exchange_rate_list"))
        self.assertContains(response, reverse("finance:fx_variance_policy_list"))
        self.assertNotContains(response, reverse("admin:finance_currency_changelist"))
        self.assertNotContains(response, reverse("admin:finance_exchangerate_changelist"))
        self.assertNotContains(response, reverse("admin:finance_fxvariancepolicy_changelist"))

    def test_system_setup_shows_current_year_missing_general_budget_warning(self):
        admin_user = User.objects.create_superuser(
            username="dashboard_dept_general_admin",
            password="testpass123",
            email="dashboard_dept_general_admin@example.com",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("dashboard:system_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dept General Budgets")
        self.assertContains(response, "1 missing")

    def test_system_setup_general_budget_warning_clears_after_current_year_setup(self):
        admin_user = User.objects.create_superuser(
            username="dashboard_dept_general_complete_admin",
            password="testpass123",
            email="dashboard_dept_general_complete_admin@example.com",
        )
        general_project = Project.objects.create(
            project_code="D-DASH-NAV-01-GENERAL",
            project_name="Dashboard General Budget",
            owning_department=self.department,
            project_type=ProjectType.DEPARTMENT_GENERAL,
            budget_amount=Decimal("1000.00"),
            is_active=True,
        )
        DepartmentGeneralProject.objects.create(
            department=self.department,
            fiscal_year=date.today().year,
            project=general_project,
            budget_amount=Decimal("1000.00"),
            is_active=True,
            created_by=admin_user,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("dashboard:system_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dept General Budgets")
        self.assertContains(response, "Complete")


class DashboardCrossRequestRegressionTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_dash_cross",
            password="testpass123",
            email="req_dash_cross@example.com",
        )
        self.manager = User.objects.create_user(
            username="mgr_dash_cross",
            password="testpass123",
            email="mgr_dash_cross@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-DASH-01",
            dept_name="Dashboard Dept",
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
            project_code="PJT-DASH-01",
            project_name="Dashboard Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            is_active=True,
        )

        self.purchase_rule = ApprovalRule.objects.create(
            rule_code="PUR-DASH",
            rule_name="Purchase Dashboard Rule",
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
            rule_code="TRV-DASH",
            rule_name="Travel Dashboard Rule",
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

    def _create_purchase_and_submit(self):
        pr = PurchaseRequest.objects.create(
            title="Dashboard Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Dashboard purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Mouse",
            quantity=Decimal("1"),
            unit_price=Decimal("50.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()
        return pr

    def _create_travel_and_submit(self):
        tr = TravelRequest.objects.create(
            purpose="Dashboard Travel",
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

    def test_dashboard_shows_purchase_and_travel_recent_requests_for_requester(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        self.client.login(username="req_dash_cross", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, reverse("purchase:pr_detail", args=[pr.id]))
        self.assertContains(response, reverse("travel:tr_detail", args=[tr.id]))

    def test_dashboard_shows_purchase_and_travel_assigned_tasks_for_manager(self):
        pr = self._create_purchase_and_submit()
        tr = self._create_travel_and_submit()

        self.client.login(username="mgr_dash_cross", password="testpass123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase")
        self.assertContains(response, "Travel")
        self.assertContains(response, pr.pr_no)
        self.assertContains(response, tr.travel_no)
        self.assertContains(response, reverse("purchase:pr_detail", args=[pr.id]))
        self.assertContains(response, reverse("travel:tr_detail", args=[tr.id]))
