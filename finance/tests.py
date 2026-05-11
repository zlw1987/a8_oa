from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Department
from common.choices import BudgetEntryType, DepartmentType, RequestStatus, RequestType
from projects.models import Project, ProjectBudgetEntry
from purchase.models import PurchaseRequest

from common.templatetags.money import money
from .reporting import build_project_budget_summary, build_reserved_vs_consumed_summary
from .models import (
    AccountingReviewItem,
    AccountingReviewReason,
    CardTransaction,
    CardTransactionMatchStatus,
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
    build_money_snapshot,
    create_duplicate_card_review_item,
    evaluate_actual_expense_policy,
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
