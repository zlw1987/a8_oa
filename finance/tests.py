from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Department
from common.choices import BudgetEntryType, DepartmentType, RequestStatus, RequestType
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseRequest

from .models import (
    AccountingReviewItem,
    AccountingReviewReason,
    OverBudgetAction,
    OverBudgetPolicy,
    PaymentMethod,
)
from .services import evaluate_actual_expense_policy


User = get_user_model()


class OverBudgetPolicyServiceTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="finance_req",
            password="testpass123",
            email="finance_req@example.com",
        )
        self.accounting = User.objects.create_user(
            username="finance_acct",
            password="testpass123",
            email="finance_acct@example.com",
            is_staff=True,
        )
        self.department = Department.objects.create(
            dept_code="D-FIN-T",
            dept_name="Finance Test Dept",
            dept_type=DepartmentType.GENERAL,
        )
        self.project = Project.objects.create(
            project_code="PJT-FIN-T",
            project_name="Finance Test Project",
            owning_department=self.department,
            budget_amount=Decimal("1000.00"),
            is_active=True,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            title="Finance policy purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            status=RequestStatus.APPROVED,
            request_date=date.today(),
            currency="USD",
            estimated_total=Decimal("100.00"),
            justification="Finance policy regression",
        )
        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PURCHASE,
            source_id=self.purchase_request.id,
            amount=Decimal("100.00"),
            created_by=self.requester,
        )

    def test_evaluate_actual_expense_policy_matches_review_threshold(self):
        policy = OverBudgetPolicy.objects.create(
            policy_code="OB-REV",
            policy_name="Over Budget Review",
            request_type=RequestType.PURCHASE,
            payment_method=PaymentMethod.REIMBURSEMENT,
            over_amount_from=Decimal("0.01"),
            over_amount_to=Decimal("500.00"),
            over_percent_from=Decimal("0.0001"),
            action=OverBudgetAction.REVIEW,
            priority=1,
            is_active=True,
        )

        result = evaluate_actual_expense_policy(
            self.purchase_request,
            current_actual_amount=Decimal("120.00"),
            payment_method=PaymentMethod.REIMBURSEMENT,
            currency="USD",
        )

        self.assertEqual(result.policy, policy)
        self.assertEqual(result.action, OverBudgetAction.REVIEW)
        self.assertEqual(result.over_amount, Decimal("20.00"))
        self.assertEqual(result.over_percent, Decimal("0.2000"))

    def test_purchase_actual_spend_creates_accounting_review_item_for_review_action(self):
        OverBudgetPolicy.objects.create(
            policy_code="OB-PR-REV",
            policy_name="Purchase Review",
            request_type=RequestType.PURCHASE,
            payment_method=PaymentMethod.REIMBURSEMENT,
            over_amount_from=Decimal("0.01"),
            action=OverBudgetAction.REVIEW,
            priority=1,
            is_active=True,
        )

        actual_spend = self.purchase_request.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("120.00"),
            acting_user=self.accounting,
            vendor_name="Policy Vendor",
            reference_no="INV-001",
        )

        self.purchase_request.refresh_from_db()
        self.assertEqual(actual_spend.amount, Decimal("120.00"))
        self.assertEqual(self.purchase_request.actual_review_status, "PENDING_REVIEW")
        self.assertTrue(
            AccountingReviewItem.objects.filter(
                purchase_request=self.purchase_request,
                purchase_actual_spend=actual_spend,
                reason=AccountingReviewReason.OVER_BUDGET,
                policy_action=OverBudgetAction.REVIEW,
            ).exists()
        )
