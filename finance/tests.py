from datetime import date
from decimal import Decimal
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Department
from common.choices import BudgetEntryType, DepartmentType, RequestStatus, RequestType
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseActualSpend, PurchaseRequest, PurchaseRequestLine
from purchase.models import PurchaseRequestAttachment, PurchaseRequestAttachmentType
from travel.models import TravelActualExpenseLine, TravelActualExpenseType, TravelRequest, TravelRequestStatus

from common.templatetags.money import money
from .reporting import build_project_budget_summary, build_reserved_vs_consumed_summary
from .models import (
    AccountingReviewItem,
    AccountingReviewReason,
    AccountingPeriod,
    AccountingPeriodStatus,
    ActualExpenseAttachment,
    ActualExpenseAttachmentType,
    CardTransaction,
    CardTransactionMatchStatus,
    DirectProjectCostAction,
    DirectProjectCostPolicy,
    ExchangeRate,
    ExchangeRateSource,
    FXVarianceAction,
    FXVariancePolicy,
    OverBudgetAction,
    OverBudgetPolicy,
    PaymentMethod,
    ReceiptPolicy,
    VarianceType,
)
from .services import (
    allocate_card_transaction,
    build_duplicate_actual_expense_candidates,
    build_money_snapshot,
    create_duplicate_card_review_item,
    evaluate_actual_expense_policy,
    link_purchase_attachment_to_actual,
)


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

    def test_receipt_policy_creates_missing_receipt_review_item_and_blocks_close(self):
        ReceiptPolicy.objects.create(
            policy_code="RCPT-REQ",
            policy_name="Receipt Required",
            request_type=RequestType.PURCHASE,
            payment_method=PaymentMethod.REIMBURSEMENT,
            amount_from=Decimal("0.01"),
            requires_receipt=True,
            priority=1,
            is_active=True,
        )

        actual_spend = self.purchase_request.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("50.00"),
            acting_user=self.accounting,
            vendor_name="Receipt Vendor",
            reference_no="INV-RCPT",
        )

        self.assertTrue(
            AccountingReviewItem.objects.filter(
                purchase_request=self.purchase_request,
                purchase_actual_spend=actual_spend,
                reason=AccountingReviewReason.MISSING_RECEIPT,
            ).exists()
        )
        with self.assertRaisesMessage(ValidationError, "Cannot close request while accounting review items are unresolved."):
            self.purchase_request.close_purchase(acting_user=self.accounting)

    def test_line_level_receipt_link_resolves_missing_receipt_review(self):
        ReceiptPolicy.objects.create(
            policy_code="RCPT-LINE",
            policy_name="Line Receipt Required",
            request_type=RequestType.PURCHASE,
            payment_method=PaymentMethod.REIMBURSEMENT,
            amount_from=Decimal("0.01"),
            requires_receipt=True,
            priority=1,
            is_active=True,
        )
        actual_spend = self.purchase_request.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("50.00"),
            acting_user=self.accounting,
            vendor_name="Receipt Vendor",
            reference_no="INV-LINE",
        )
        review_item = AccountingReviewItem.objects.get(
            purchase_request=self.purchase_request,
            purchase_actual_spend=actual_spend,
            reason=AccountingReviewReason.MISSING_RECEIPT,
        )
        attachment = PurchaseRequestAttachment.objects.create(
            purchase_request=self.purchase_request,
            document_type=PurchaseRequestAttachmentType.SUPPORT,
            file=SimpleUploadedFile("receipt.pdf", b"receipt bytes", content_type="application/pdf"),
            title="receipt.pdf",
            uploaded_by=self.accounting,
        )

        link_purchase_attachment_to_actual(
            actual_expense=actual_spend,
            purchase_attachment=attachment,
            attachment_type=ActualExpenseAttachmentType.RECEIPT,
            acting_user=self.accounting,
        )

        self.assertTrue(
            ActualExpenseAttachment.objects.filter(
                purchase_actual_spend=actual_spend,
                purchase_attachment=attachment,
                attachment_type=ActualExpenseAttachmentType.RECEIPT,
            ).exists()
        )
        review_item.refresh_from_db()
        self.assertEqual(review_item.status, "RESOLVED")

    def test_card_allocation_cannot_exceed_unallocated_amount(self):
        card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Card Vendor",
            amount=Decimal("100.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="CARD-001",
            imported_by=self.accounting,
        )

        allocate_card_transaction(
            card_transaction=card_transaction,
            amount=Decimal("80.00"),
            purchase_request=self.purchase_request,
            acting_user=self.accounting,
        )
        card_transaction.refresh_from_db()
        self.assertEqual(card_transaction.match_status, CardTransactionMatchStatus.PARTIALLY_MATCHED)

        with self.assertRaisesMessage(ValidationError, "Allocation amount cannot exceed"):
            allocate_card_transaction(
                card_transaction=card_transaction,
                amount=Decimal("30.00"),
                purchase_request=self.purchase_request,
                acting_user=self.accounting,
            )

    def test_direct_project_cost_policy_review_creates_review_item(self):
        policy = DirectProjectCostPolicy.objects.create(
            policy_code="DPC-REV",
            policy_name="Direct Project Cost Review",
            project=self.project,
            payment_method=PaymentMethod.COMPANY_CARD,
            amount_from=Decimal("0.01"),
            action=DirectProjectCostAction.REVIEW,
            priority=1,
            is_active=True,
        )
        card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Direct Cost Vendor",
            amount=Decimal("75.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="DPC-001",
            imported_by=self.accounting,
        )

        allocation = allocate_card_transaction(
            card_transaction=card_transaction,
            amount=Decimal("75.00"),
            project=self.project,
            acting_user=self.accounting,
        )

        self.assertEqual(allocation.direct_project_cost_policy, policy)
        self.assertEqual(allocation.direct_project_cost_action, DirectProjectCostAction.REVIEW)
        self.assertTrue(
            AccountingReviewItem.objects.filter(
                card_transaction=card_transaction,
                card_allocation=allocation,
                reason=AccountingReviewReason.DIRECT_PROJECT_COST,
                direct_project_cost_policy=policy,
                policy_action=DirectProjectCostAction.REVIEW,
            ).exists()
        )

    def test_direct_project_cost_policy_requires_project_owner_review(self):
        policy = DirectProjectCostPolicy.objects.create(
            policy_code="DPC-OWNER",
            policy_name="Direct Project Cost Owner Review",
            project=self.project,
            payment_method=PaymentMethod.COMPANY_CARD,
            amount_from=Decimal("0.01"),
            action=DirectProjectCostAction.REQUIRE_PROJECT_OWNER_APPROVAL,
            priority=1,
            is_active=True,
        )
        card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Owner Review Direct Cost",
            amount=Decimal("85.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="DPC-OWN-001",
            imported_by=self.accounting,
        )

        allocation = allocate_card_transaction(
            card_transaction=card_transaction,
            amount=Decimal("85.00"),
            project=self.project,
            acting_user=self.accounting,
        )

        self.assertEqual(allocation.direct_project_cost_policy, policy)
        self.assertEqual(allocation.direct_project_cost_action, DirectProjectCostAction.REQUIRE_PROJECT_OWNER_APPROVAL)
        self.assertEqual(allocation.project_owner_review_status, "PENDING_REVIEW")
        self.assertTrue(
            AccountingReviewItem.objects.filter(
                card_transaction=card_transaction,
                card_allocation=allocation,
                reason=AccountingReviewReason.DIRECT_PROJECT_COST,
                policy_action=DirectProjectCostAction.REQUIRE_PROJECT_OWNER_APPROVAL,
            ).exists()
        )

    def test_direct_project_cost_policy_block_prevents_allocation(self):
        DirectProjectCostPolicy.objects.create(
            policy_code="DPC-BLOCK",
            policy_name="Direct Project Cost Block",
            project=self.project,
            payment_method=PaymentMethod.COMPANY_CARD,
            amount_from=Decimal("0.01"),
            action=DirectProjectCostAction.BLOCK,
            priority=1,
            is_active=True,
        )
        card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Blocked Direct Cost",
            amount=Decimal("75.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="DPC-002",
            imported_by=self.accounting,
        )

        with self.assertRaisesMessage(ValidationError, "Direct project cost is blocked"):
            allocate_card_transaction(
                card_transaction=card_transaction,
                amount=Decimal("75.00"),
                project=self.project,
                acting_user=self.accounting,
            )

    def test_duplicate_card_transaction_creates_review_item_without_blocking(self):
        base = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Duplicate Merchant",
            amount=Decimal("42.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="DUP-001",
            imported_by=self.accounting,
        )
        duplicate = CardTransaction.objects.create(
            statement_date=base.statement_date,
            transaction_date=base.transaction_date,
            merchant_name=base.merchant_name,
            amount=base.amount,
            currency=base.currency,
            cardholder=self.requester,
            reference_no=base.reference_no,
            imported_by=self.accounting,
        )

        review_item = create_duplicate_card_review_item(duplicate, created_by=self.accounting)

        self.assertIsNotNone(review_item)
        self.assertEqual(review_item.reason, AccountingReviewReason.DUPLICATE_CARD)
        self.assertEqual(review_item.card_transaction, duplicate)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class DuplicateActualExpenseReviewTest(TestCase):
    def setUp(self):
        self.accounting = User.objects.create_user(
            username="dup_actual_acct",
            password="testpass123",
            is_staff=True,
        )
        self.requester = User.objects.create_user(username="dup_actual_req", password="testpass123")
        self.department = Department.objects.create(
            dept_code="DUP-ACT",
            dept_name="Duplicate Actual Dept",
            dept_type=DepartmentType.GENERAL,
        )
        self.project = Project.objects.create(
            project_code="DUP-ACT-PRJ",
            project_name="Duplicate Actual Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            is_active=True,
        )
        self.purchase = PurchaseRequest.objects.create(
            title="Duplicate Actual Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            status=RequestStatus.APPROVED,
            estimated_total=Decimal("1000.00"),
            currency="USD",
        )
        PurchaseRequestLine.objects.create(
            request=self.purchase,
            line_no=1,
            item_name="Duplicate Actual Item",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
        )
        self.travel = TravelRequest.objects.create(
            purpose="Duplicate Actual Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today(),
            end_date=date.today(),
            origin_city="San Jose",
            destination_city="Taipei",
            status=TravelRequestStatus.APPROVED,
            estimated_total=Decimal("1000.00"),
            currency="USD",
        )

    def test_same_vendor_date_amount_reference_creates_duplicate_actual_review(self):
        self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("100.00"),
            acting_user=self.accounting,
            vendor_name="Same Vendor",
            reference_no="INV-100",
        )
        second = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("100.00"),
            acting_user=self.accounting,
            vendor_name="Same Vendor",
            reference_no="INV-100",
        )

        self.assertTrue(
            AccountingReviewItem.objects.filter(
                purchase_actual_spend=second,
                reason=AccountingReviewReason.DUPLICATE_EXPENSE,
                status="PENDING_REVIEW",
            ).exists()
        )
        self.assertEqual(PurchaseActualSpend.objects.filter(purchase_request=self.purchase).count(), 2)

    def test_same_receipt_hash_creates_duplicate_actual_review(self):
        first = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("110.00"),
            acting_user=self.accounting,
            vendor_name="Vendor A",
            reference_no="INV-A",
        )
        second = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("120.00"),
            acting_user=self.accounting,
            vendor_name="Vendor B",
            reference_no="INV-B",
        )
        first_attachment = PurchaseRequestAttachment.objects.create(
            purchase_request=self.purchase,
            document_type=PurchaseRequestAttachmentType.SUPPORT,
            title="Receipt A",
            file=SimpleUploadedFile("receipt-a.txt", b"same receipt bytes"),
            uploaded_by=self.accounting,
        )
        second_attachment = PurchaseRequestAttachment.objects.create(
            purchase_request=self.purchase,
            document_type=PurchaseRequestAttachmentType.SUPPORT,
            title="Receipt B",
            file=SimpleUploadedFile("receipt-b.txt", b"same receipt bytes"),
            uploaded_by=self.accounting,
        )

        link_purchase_attachment_to_actual(
            actual_expense=first,
            purchase_attachment=first_attachment,
            attachment_type=ActualExpenseAttachmentType.RECEIPT,
            acting_user=self.accounting,
        )
        link_purchase_attachment_to_actual(
            actual_expense=second,
            purchase_attachment=second_attachment,
            attachment_type=ActualExpenseAttachmentType.RECEIPT,
            acting_user=self.accounting,
        )

        self.assertEqual(first_attachment.file_hash, second_attachment.file_hash)
        self.assertTrue(
            AccountingReviewItem.objects.filter(
                purchase_actual_spend=second,
                reason=AccountingReviewReason.DUPLICATE_EXPENSE,
                status="PENDING_REVIEW",
                description__icontains="hash",
            ).exists()
        )
        candidates = build_duplicate_actual_expense_candidates(second)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["object_id"], first.id)
        self.assertEqual(candidates[0]["match_type"], "Receipt/Invoice Hash")

    def test_duplicate_candidate_helper_returns_structured_purchase_candidate(self):
        first = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("130.00"),
            acting_user=self.accounting,
            vendor_name="Candidate Vendor",
            reference_no="INV-CAND",
        )
        second = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("130.00"),
            acting_user=self.accounting,
            vendor_name="Candidate Vendor",
            reference_no="INV-CAND",
        )
        candidates = build_duplicate_actual_expense_candidates(second)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["type"], "PURCHASE_ACTUAL")
        self.assertEqual(candidates[0]["object_id"], first.id)
        self.assertEqual(candidates[0]["request_no"], self.purchase.pr_no)
        self.assertEqual(candidates[0]["amount"], Decimal("130.00"))
        self.assertEqual(candidates[0]["vendor"], "Candidate Vendor")
        self.assertEqual(candidates[0]["reference"], "INV-CAND")
        self.assertEqual(candidates[0]["match_type"], "Vendor/Date/Amount/Reference")
        self.assertEqual(candidates[0]["url"], reverse("purchase:pr_detail", args=[self.purchase.id]))

    def test_duplicate_review_detail_shows_clickable_purchase_candidate_without_blocking_records(self):
        first = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("130.00"),
            acting_user=self.accounting,
            vendor_name="Candidate Vendor",
            reference_no="INV-CAND",
        )
        second = self.purchase.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("130.00"),
            acting_user=self.accounting,
            vendor_name="Candidate Vendor",
            reference_no="INV-CAND",
        )
        review_item = AccountingReviewItem.objects.get(
            purchase_actual_spend=second,
            reason=AccountingReviewReason.DUPLICATE_EXPENSE,
        )

        self.client.force_login(self.accounting)
        response = self.client.get(reverse("finance:accounting_review_detail", args=[review_item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Candidate Review")
        self.assertContains(response, "Vendor/Date/Amount/Reference")
        self.assertContains(response, reverse("purchase:pr_detail", args=[self.purchase.id]))
        self.assertContains(response, f"{self.purchase.pr_no} actual #{first.id}")
        self.assertEqual(PurchaseActualSpend.objects.filter(purchase_request=self.purchase).count(), 2)
        self.assertTrue(PurchaseActualSpend.objects.filter(pk=first.pk).exists())
        self.assertTrue(PurchaseActualSpend.objects.filter(pk=second.pk).exists())

    def test_duplicate_review_detail_shows_clickable_travel_candidate(self):
        first = self.travel.record_actual_expense(
            expense_type="HOTEL",
            expense_date=date.today(),
            actual_amount=Decimal("140.00"),
            acting_user=self.accounting,
            vendor_name="Travel Candidate Vendor",
            reference_no="TR-INV-CAND",
            skip_finance_policy=True,
        )
        second = self.travel.record_actual_expense(
            expense_type="HOTEL",
            expense_date=date.today(),
            actual_amount=Decimal("140.00"),
            acting_user=self.accounting,
            vendor_name="Travel Candidate Vendor",
            reference_no="TR-INV-CAND",
            skip_finance_policy=True,
        )
        review_item = AccountingReviewItem.objects.get(
            travel_actual_expense=second,
            reason=AccountingReviewReason.DUPLICATE_EXPENSE,
        )

        self.client.force_login(self.accounting)
        response = self.client.get(reverse("finance:accounting_review_detail", args=[review_item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Candidate Review")
        self.assertContains(response, "Vendor/Date/Amount/Reference")
        self.assertContains(response, reverse("travel:tr_detail", args=[self.travel.id]))
        self.assertContains(response, f"{self.travel.travel_no} actual #{first.id}")
        self.assertEqual(self.travel.actual_expense_lines.count(), 2)


class FinanceReportCurrencyFormattingTest(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            dept_code="D-FIN-RPT",
            dept_name="Finance Report Dept",
            dept_type=DepartmentType.FIN,
        )

    def test_money_filter_formats_currency_decimals_and_negative_amounts(self):
        self.assertEqual(money(Decimal("12710"), "USD"), "USD 12,710.00")
        self.assertEqual(money(Decimal("100000"), "TWD"), "TWD 100,000.00")
        self.assertEqual(money(Decimal("-300"), "USD"), "USD -300.00")


class FinanceReportDrillDownSmokeTest(TestCase):
    def setUp(self):
        self.accounting = User.objects.create_user(
            username="finance_report_links",
            password="testpass123",
            is_staff=True,
        )
        self.requester = User.objects.create_user(username="finance_report_req", password="testpass123")
        self.department = Department.objects.create(
            dept_code="D-FIN-LINK",
            dept_name="Finance Link Dept",
            dept_type=DepartmentType.FIN,
        )
        self.project = Project.objects.create(
            project_code="FIN-LINK-PRJ",
            project_name="Finance Link Project",
            owning_department=self.department,
            budget_amount=Decimal("1000.00"),
            is_active=True,
        )
        self.purchase = PurchaseRequest.objects.create(
            title="Finance Link Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            status=RequestStatus.SUBMITTED,
            estimated_total=Decimal("100.00"),
            currency="USD",
        )
        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PURCHASE,
            source_id=self.purchase.id,
            amount=Decimal("100.00"),
            created_by=self.accounting,
        )
        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.PURCHASE,
            source_id=self.purchase.id,
            amount=Decimal("75.00"),
            created_by=self.accounting,
        )
        self.purchase_actual = PurchaseActualSpend.objects.create(
            purchase_request=self.purchase,
            spend_date=date.today(),
            amount=Decimal("75.00"),
            transaction_amount=Decimal("75.00"),
            base_amount=Decimal("75.00"),
            vendor_name="Department Vendor",
            reference_no="PR-ACT-LINK",
            created_by=self.accounting,
        )
        self.travel = TravelRequest.objects.create(
            purpose="Finance Link Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            origin_city="Taipei",
            destination_city="Los Angeles",
            start_date=date.today(),
            end_date=date.today(),
            status=TravelRequestStatus.APPROVED,
            estimated_total=Decimal("200.00"),
            currency="USD",
        )
        self.travel_actual = TravelActualExpenseLine.objects.create(
            travel_request=self.travel,
            line_no=1,
            expense_type=TravelActualExpenseType.MEAL,
            expense_date=date.today(),
            actual_amount=Decimal("35.00"),
            transaction_amount=Decimal("35.00"),
            base_amount=Decimal("35.00"),
            vendor_name="Department Travel Vendor",
            reference_no="TR-ACT-LINK",
            created_by=self.accounting,
        )
        self.review_item = AccountingReviewItem.objects.create(
            source_type=RequestType.PURCHASE,
            purchase_request=self.purchase,
            reason=AccountingReviewReason.OVER_BUDGET,
            status="PENDING_REVIEW",
            amount=Decimal("25.00"),
            over_amount=Decimal("25.00"),
            title="Over budget report link",
            description="Report drill-down review item.",
            created_by=self.accounting,
        )
        self.card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Unmatched Merchant",
            amount=Decimal("40.00"),
            cardholder=self.requester,
            reference_no="CARD-LINK-1",
            imported_by=self.accounting,
        )

    def test_finance_reports_render_core_drill_down_links(self):
        self.client.force_login(self.accounting)
        response = self.client.get(reverse("finance:finance_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("projects:project_budget_ledger", args=[self.project.id]))
        self.assertContains(response, reverse("finance:department_spending_drilldown", args=[self.department.id]))
        self.assertContains(response, reverse("purchase:pr_detail", args=[self.purchase.id]))
        self.assertContains(response, reverse("finance:accounting_review_detail", args=[self.review_item.id]))
        self.assertContains(response, reverse("finance:card_transaction_detail", args=[self.card_transaction.id]))

    def test_department_spending_drilldown_returns_source_records(self):
        self.client.force_login(self.accounting)
        response = self.client.get(reverse("finance:department_spending_drilldown", args=[self.department.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.department.dept_code)
        self.assertContains(response, self.project.project_code)
        self.assertContains(response, reverse("projects:project_budget_ledger", args=[self.project.id]))
        self.assertContains(response, self.purchase.pr_no)
        self.assertContains(response, reverse("purchase:pr_detail", args=[self.purchase.id]))
        self.assertContains(response, self.travel.travel_no)
        self.assertContains(response, reverse("travel:tr_detail", args=[self.travel.id]))
        self.assertContains(response, "Department Vendor")
        self.assertContains(response, "Department Travel Vendor")
        self.assertContains(response, "USD 75.00")
        self.assertContains(response, "USD 35.00")

    def test_requester_cannot_access_department_spending_drilldown_directly(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("finance:department_spending_drilldown", args=[self.department.id]))

        self.assertEqual(response.status_code, 403)


class FinanceCurrencySetupViewTest(TestCase):
    def setUp(self):
        self.finance_admin = User.objects.create_user(
            username="currency_fin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.requester = User.objects.create_user(username="currency_req", password="testpass123")
        self.department = Department.objects.create(
            dept_code="D-FIN-CUR",
            dept_name="Finance Currency Dept",
            dept_type=DepartmentType.FIN,
        )

    def test_currency_exchange_rate_and_fx_policy_pages_render(self):
        self.client.force_login(self.finance_admin)
        urls = [
            reverse("finance:currency_list"),
            reverse("finance:currency_create"),
            reverse("finance:exchange_rate_list"),
            reverse("finance:exchange_rate_create"),
            reverse("finance:fx_variance_policy_list"),
            reverse("finance:fx_variance_policy_create"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_requester_cannot_access_currency_setup(self):
        self.client.force_login(self.requester)
        response = self.client.get(reverse("finance:currency_list"))

        self.assertEqual(response.status_code, 403)

    def test_finance_admin_group_user_can_access_currency_setup_without_staff_flag(self):
        group = Group.objects.create(name="Finance Admin")
        group_user = User.objects.create_user(username="currency_group_fin", password="testpass123")
        group_user.groups.add(group)
        self.client.force_login(group_user)

        response = self.client.get(reverse("finance:currency_list"))

        self.assertEqual(response.status_code, 200)

    def test_exchange_rate_create_sets_created_by(self):
        self.client.force_login(self.finance_admin)
        response = self.client.post(
            reverse("finance:exchange_rate_create"),
            {
                "from_currency": "TWD",
                "to_currency": "USD",
                "rate": "0.03150000",
                "effective_date": date.today().isoformat(),
                "source": ExchangeRateSource.COMPANY_RATE,
                "notes": "Company test rate.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        rate = ExchangeRate.objects.get(from_currency="TWD", to_currency="USD")
        self.assertEqual(rate.created_by, self.finance_admin)

    def test_project_budget_summary_reports_company_base_currency(self):
        usd_project = Project.objects.create(
            project_code="RPT-USD",
            project_name="USD Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            currency="USD",
            is_active=True,
        )
        ProjectBudgetEntry.objects.create(
            project=usd_project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PROJECT,
            source_id=usd_project.id,
            amount=Decimal("530.00"),
        )
        ProjectBudgetEntry.objects.create(
            project=usd_project,
            entry_type=BudgetEntryType.CONSUME,
            source_type=RequestType.PROJECT,
            source_id=usd_project.id,
            amount=Decimal("520.00"),
        )
        twd_project = Project.objects.create(
            project_code="RPT-TWD",
            project_name="Converted TWD Project",
            owning_department=self.department,
            budget_amount=Decimal("3000.00"),
            currency="USD",
            is_active=True,
        )
        ProjectBudgetEntry.objects.create(
            project=twd_project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PROJECT,
            source_id=twd_project.id,
            amount=Decimal("600.00"),
            currency="USD",
            source_transaction_currency="TWD",
            source_transaction_amount=Decimal("20000.00"),
            source_exchange_rate=Decimal("0.03000000"),
            source_exchange_rate_source=ExchangeRateSource.COMPANY_RATE,
        )

        rows = {row["project"].project_code: row for row in build_project_budget_summary()}

        self.assertEqual(rows["RPT-USD"]["currency"], "USD")
        self.assertEqual(money(rows["RPT-USD"]["reserved"], rows["RPT-USD"]["currency"]), "USD 530.00")
        self.assertEqual(money(rows["RPT-USD"]["consumed"], rows["RPT-USD"]["currency"]), "USD 520.00")
        self.assertEqual(money(rows["RPT-USD"]["available"], rows["RPT-USD"]["currency"]), "USD 8,950.00")
        self.assertEqual(rows["RPT-TWD"]["currency"], "USD")
        self.assertEqual(money(rows["RPT-TWD"]["reserved"], rows["RPT-TWD"]["currency"]), "USD 600.00")

    def test_reserved_vs_consumed_summary_reports_base_currency_totals(self):
        usd_project = Project.objects.create(
            project_code="RPT-MIX-USD",
            project_name="Mixed USD Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            currency="USD",
            is_active=True,
        )
        twd_project = Project.objects.create(
            project_code="RPT-MIX-TWD",
            project_name="Converted TWD Project",
            owning_department=self.department,
            budget_amount=Decimal("3000.00"),
            currency="USD",
            is_active=True,
        )
        ProjectBudgetEntry.objects.create(
            project=usd_project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PROJECT,
            source_id=usd_project.id,
            amount=Decimal("1000.00"),
        )
        ProjectBudgetEntry.objects.create(
            project=twd_project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PROJECT,
            source_id=twd_project.id,
            amount=Decimal("600.00"),
            currency="USD",
            source_transaction_currency="TWD",
            source_transaction_amount=Decimal("20000.00"),
            source_exchange_rate=Decimal("0.03000000"),
            source_exchange_rate_source=ExchangeRateSource.COMPANY_RATE,
        )

        row = build_reserved_vs_consumed_summary()

        self.assertEqual(row["currency"], "USD")
        self.assertEqual(row["reserved"], Decimal("1600.00"))


class MultiCurrencyServiceTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(username="mc_req", password="testpass123")
        self.department = Department.objects.create(
            dept_code="D-MC",
            dept_name="Multi Currency Dept",
            dept_type=DepartmentType.GENERAL,
        )
        self.project = Project.objects.create(
            project_code="PJT-MC",
            project_name="Multi Currency Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            currency="USD",
            is_active=True,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            title="TWD hotel estimate",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            status=RequestStatus.APPROVED,
            request_date=date.today(),
            currency="USD",
            estimated_total=Decimal("930.00"),
            transaction_currency="TWD",
            transaction_amount=Decimal("30000.00"),
            base_currency="USD",
            base_amount=Decimal("930.00"),
            justification="Multi-currency policy test",
        )

    def test_build_money_snapshot_uses_company_exchange_rate(self):
        ExchangeRate.objects.create(
            from_currency="TWD",
            to_currency="USD",
            rate=Decimal("0.03150000"),
            effective_date=date.today(),
            source=ExchangeRateSource.COMPANY_RATE,
        )

        snapshot = build_money_snapshot(transaction_amount=Decimal("3000.00"), transaction_currency="TWD")

        self.assertEqual(snapshot["base_currency"], "USD")
        self.assertEqual(snapshot["base_amount"], Decimal("94.50"))
        self.assertEqual(snapshot["exchange_rate_source"], ExchangeRateSource.COMPANY_RATE)

    def test_fx_variance_is_not_treated_as_spending_overrun(self):
        FXVariancePolicy.objects.create(
            policy_code="FX-WARN",
            policy_name="FX Warning",
            fx_variance_amount_to=Decimal("100.00"),
            action=FXVarianceAction.WARNING,
            priority=1,
            is_active=True,
        )

        result = evaluate_actual_expense_policy(
            self.purchase_request,
            current_actual_amount=Decimal("960.00"),
            current_transaction_amount=Decimal("30000.00"),
            transaction_currency="TWD",
            base_amount=Decimal("960.00"),
            exchange_rate=Decimal("0.03200000"),
            exchange_rate_source=ExchangeRateSource.COMPANY_RATE,
        )

        self.assertEqual(result.variance_type, VarianceType.FX_VARIANCE)
        self.assertEqual(result.action, OverBudgetAction.WARNING)

    def test_transaction_amount_increase_is_spending_overrun(self):
        OverBudgetPolicy.objects.create(
            policy_code="MC-OB-REV",
            policy_name="MC Over Budget Review",
            request_type=RequestType.PURCHASE,
            over_amount_from=Decimal("0.01"),
            action=OverBudgetAction.REVIEW,
            priority=1,
            is_active=True,
        )

        result = evaluate_actual_expense_policy(
            self.purchase_request,
            current_actual_amount=Decimal("1280.00"),
            current_transaction_amount=Decimal("40000.00"),
            transaction_currency="TWD",
            base_amount=Decimal("1280.00"),
            exchange_rate=Decimal("0.03200000"),
            exchange_rate_source=ExchangeRateSource.COMPANY_RATE,
        )

        self.assertEqual(result.variance_type, VarianceType.SPENDING_OVERRUN)
        self.assertEqual(result.action, OverBudgetAction.REVIEW)

    def test_company_card_preserves_original_currency_and_posted_base_amount(self):
        card_transaction = CardTransaction.objects.create(
            statement_date=date.today(),
            transaction_date=date.today(),
            merchant_name="Taipei Hotel",
            amount=Decimal("95.12"),
            currency="USD",
            transaction_currency="TWD",
            transaction_amount=Decimal("3000.00"),
            base_currency="USD",
            base_amount=Decimal("95.12"),
            exchange_rate_source=ExchangeRateSource.CARD_STATEMENT,
            cardholder=self.requester,
            reference_no="MC-CARD-001",
        )

        self.assertEqual(card_transaction.amount, Decimal("95.12"))
        self.assertEqual(card_transaction.base_amount, Decimal("95.12"))
        self.assertEqual(card_transaction.transaction_amount, Decimal("3000.00"))
        self.assertEqual(card_transaction.transaction_currency, "TWD")
        self.assertEqual(card_transaction.exchange_rate_source, ExchangeRateSource.CARD_STATEMENT)

    def test_missing_exchange_rate_blocks_snapshot(self):
        with self.assertRaisesMessage(ValidationError, "No exchange rate found for JPY to USD"):
            build_money_snapshot(transaction_amount=Decimal("1000.00"), transaction_currency="JPY")


class AccountingPeriodWorkflowTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(username="period_req", password="testpass123")
        self.finance_admin = User.objects.create_user(
            username="period_fin",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.department = Department.objects.create(
            dept_code="D-PER",
            dept_name="Period Dept",
            dept_type=DepartmentType.FIN,
        )
        self.project = Project.objects.create(
            project_code="PJT-PER",
            project_name="Period Project",
            owning_department=self.department,
            budget_amount=Decimal("1000.00"),
            currency="USD",
            is_active=True,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            title="Period PR",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            status=RequestStatus.APPROVED,
            request_date=date(2026, 5, 10),
            currency="USD",
            estimated_total=Decimal("200.00"),
            justification="Period workflow",
        )
        ProjectBudgetEntry.objects.create(
            project=self.project,
            entry_type=BudgetEntryType.RESERVE,
            source_type=RequestType.PURCHASE,
            source_id=self.purchase_request.id,
            amount=Decimal("200.00"),
            currency="USD",
            created_by=self.requester,
        )
        self.period = AccountingPeriod.objects.create(
            period_code="2026-05",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            status=AccountingPeriodStatus.OPEN,
        )

    def test_period_close_page_renders_checklist(self):
        self.client.force_login(self.finance_admin)
        response = self.client.get(reverse("finance:accounting_period_detail", args=[self.period.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Period Close Checklist")
        self.assertContains(response, "No open requests with remaining reserve")

    def test_period_close_sets_closed_metadata(self):
        self.client.force_login(self.finance_admin)
        response = self.client.post(
            reverse("finance:accounting_period_close", args=[self.period.id]),
            {"notes": "May close reviewed."},
        )

        self.assertRedirects(response, reverse("finance:accounting_period_detail", args=[self.period.id]))
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, AccountingPeriodStatus.CLOSED)
        self.assertEqual(self.period.closed_by, self.finance_admin)
        self.assertIsNotNone(self.period.closed_at)

    def test_closed_period_blocks_actual_spend_and_card_allocation(self):
        self.period.status = AccountingPeriodStatus.CLOSED
        self.period.closed_by = self.finance_admin
        self.period.save(update_fields=["status", "closed_by"])

        with self.assertRaisesMessage(ValidationError, "closed accounting period"):
            self.purchase_request.record_actual_spend(
                spend_date=date(2026, 5, 12),
                amount=Decimal("50.00"),
                acting_user=self.finance_admin,
            )

        card_transaction = CardTransaction.objects.create(
            statement_date=date(2026, 5, 31),
            transaction_date=date(2026, 5, 12),
            merchant_name="Closed Period Merchant",
            amount=Decimal("50.00"),
            currency="USD",
            cardholder=self.requester,
            reference_no="PER-CARD-001",
            imported_by=self.finance_admin,
        )
        with self.assertRaisesMessage(ValidationError, "closed accounting period"):
            allocate_card_transaction(
                card_transaction=card_transaction,
                amount=Decimal("50.00"),
                purchase_request=self.purchase_request,
                acting_user=self.finance_admin,
            )

    def test_refund_creates_negative_actual_and_budget_entry(self):
        actual = self.purchase_request.record_actual_spend(
            spend_date=date(2026, 5, 12),
            amount=Decimal("80.00"),
            acting_user=self.finance_admin,
        )

        refund = self.purchase_request.record_refund(
            original_actual_spend=actual,
            refund_date=date(2026, 5, 13),
            amount=Decimal("30.00"),
            acting_user=self.finance_admin,
            reference_no="REF-001",
        )

        self.assertEqual(refund.amount, Decimal("-30.00"))
        self.assertEqual(refund.original_actual_spend, actual)
        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                entry_type=BudgetEntryType.CONSUME,
                source_type=RequestType.PURCHASE,
                source_id=self.purchase_request.id,
                amount=Decimal("-30.00"),
            ).exists()
        )

    def test_closed_request_can_be_reopened_by_finance_admin(self):
        self.purchase_request.record_actual_spend(
            spend_date=date(2026, 5, 12),
            amount=Decimal("200.00"),
            acting_user=self.finance_admin,
        )
        self.purchase_request.close_purchase(acting_user=self.finance_admin)

        self.purchase_request.reopen_for_correction(
            acting_user=self.finance_admin,
            reason="Correct vendor reference.",
            correction_reference="COR-001",
        )

        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, RequestStatus.APPROVED)
        self.assertEqual(self.purchase_request.correction_status, "OPEN")
        self.assertEqual(self.purchase_request.correction_reference, "COR-001")

    def test_closed_period_blocks_reopen_correction(self):
        self.purchase_request.record_actual_spend(
            spend_date=date(2026, 5, 12),
            amount=Decimal("200.00"),
            acting_user=self.finance_admin,
        )
        self.purchase_request.close_purchase(acting_user=self.finance_admin)
        self.period.status = AccountingPeriodStatus.CLOSED
        self.period.save(update_fields=["status"])

        with self.assertRaisesMessage(ValidationError, "closed accounting period"):
            self.purchase_request.reopen_for_correction(
                acting_user=self.finance_admin,
                reason="Closed-period correction.",
            )
