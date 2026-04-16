from datetime import date, timedelta
from decimal import Decimal
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import (
    ApproverType,
    RequestStatus,
    RequestType,
    DepartmentType,
    BudgetEntryType,
)
from projects.models import Project, ProjectBudgetEntry
from purchase.models import (
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseFulfillmentStatus,
    PurchaseRequestAttachment, 
    PurchaseRequestContentAudit
)


User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MEDIA_ROOT=tempfile.gettempdir(),
)
class PurchaseSmokeTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_purchase",
            password="testpass123",
            email="req_purchase@example.com",
        )
        self.manager = User.objects.create_user(
            username="mgr_purchase",
            password="testpass123",
            email="mgr_purchase@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-PUR-01",
            dept_name="Purchase Dept",
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
            project_code="PJT-PUR-01",
            project_name="Purchase Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            is_active=True,
        )

        self.rule = ApprovalRule.objects.create(
            rule_code="PUR-DEFAULT",
            rule_name="Purchase Default Rule",
            request_type=RequestType.PURCHASE,
            department=self.department,
            is_active=True,
            priority=1,
        )

        ApprovalRuleStep.objects.create(
            rule=self.rule,
            step_no=1,
            step_name="Department Manager Approval",
            approver_type=ApproverType.DEPARTMENT_MANAGER,
            is_active=True,
        )

    def test_purchase_submit_creates_task(self):
        self.client.login(username="req_purchase", password="testpass123")

        pr = PurchaseRequest.objects.create(
            title="Test Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Need test item",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Laptop",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
        )

        response = self.client.post(reverse("purchase:pr_submit", args=[pr.id]))
        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(pr.approval_tasks.count(), 1)

    def test_purchase_detail_page_loads(self):
        self.client.login(username="req_purchase", password="testpass123")

        pr = PurchaseRequest.objects.create(
            title="Detail Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Need detail test",
        )

        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase")

    def test_purchase_full_workflow_regression(self):
        self.client.login(username="req_purchase", password="testpass123")

        pr = PurchaseRequest.objects.create(
            title="Workflow Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Workflow regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Monitor",
            quantity=Decimal("2"),
            unit_price=Decimal("300.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(pr.approval_tasks.count(), 1)

        current_task = pr.get_current_task()
        self.assertIsNotNone(current_task)
        self.assertEqual(current_task.assigned_user, self.manager)

        current_task.approve(self.manager, comment="Approved in regression test")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)

        pr.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("550.00"),
            acting_user=self.requester,
            vendor_name="Test Vendor",
            reference_no="PO-TEST-001",
            notes="Regression spend entry",
        )
        pr.refresh_from_db()

        self.assertEqual(pr.actual_spend_entries.count(), 1)
        self.assertEqual(pr.get_actual_spent_total(), Decimal("550.00"))

        pr.close_purchase(
            acting_user=self.requester,
            comment="Closed in regression test",
        )
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.CLOSED)

        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))
        self.assertEqual(response.status_code, 200)

    def test_purchase_submit_sends_requester_and_approver_notifications(self):
        self.client.login(username="req_purchase", password="testpass123")

        pr = PurchaseRequest.objects.create(
            title="Notify Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Purchase notification regression",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Headset",
            quantity=Decimal("1"),
            unit_price=Decimal("120.00"),
        )

        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("purchase:pr_submit", args=[pr.id]))

        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(len(mail.outbox), 2)

        subjects = [message.subject for message in mail.outbox]
        recipients = [recipient for message in mail.outbox for recipient in message.to]

        self.assertTrue(any(pr.pr_no in subject and "submitted" in subject.lower() for subject in subjects))
        self.assertTrue(any(pr.pr_no in subject and "approval needed" in subject.lower() for subject in subjects))
        self.assertIn(self.requester.email, recipients)
        self.assertIn(self.manager.email, recipients)

    def test_purchase_return_sends_requester_notification(self):
        pr = PurchaseRequest.objects.create(
            title="Return Notify Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Purchase return notification regression",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Speaker",
            quantity=Decimal("1"),
            unit_price=Decimal("200.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)

        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            task.return_to_requester(self.manager, comment="Need more detail")

        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.RETURNED)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertIn(pr.pr_no, message.subject)
        self.assertIn("returned", message.subject.lower())
        self.assertIn(self.requester.email, message.to)

    def test_purchase_submit_creates_budget_reserve_entry(self):
        pr = PurchaseRequest.objects.create(
            title="Budget Reserve Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Reserve regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Chair",
            quantity=Decimal("2"),
            unit_price=Decimal("150.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(pr.estimated_total, Decimal("300.00"))

        reserve_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.RESERVE,
        )
        self.assertEqual(reserve_entries.count(), 1)
        self.assertEqual(reserve_entries.first().amount, Decimal("300.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("300.00"))

    def test_purchase_return_releases_reserved_budget(self):
        pr = PurchaseRequest.objects.create(
            title="Budget Return Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Return budget regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Desk",
            quantity=Decimal("1"),
            unit_price=Decimal("400.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)

        task.return_to_requester(self.manager, comment="Need revision")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.RETURNED)

        reserve_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.RESERVE,
        )
        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.RELEASE,
        )

        self.assertEqual(reserve_entries.count(), 1)
        self.assertEqual(release_entries.count(), 1)
        self.assertEqual(reserve_entries.first().amount, Decimal("400.00"))
        self.assertEqual(release_entries.first().amount, Decimal("400.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_purchase_actual_spend_creates_consume_and_partial_release(self):
        pr = PurchaseRequest.objects.create(
            title="Budget Consume Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Consume regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Printer",
            quantity=Decimal("1"),
            unit_price=Decimal("600.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        task.approve(self.manager, comment="Approved for budget consume test")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("600.00"))

        pr.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("550.00"),
            acting_user=self.requester,
            vendor_name="Budget Vendor",
            reference_no="BUD-001",
            notes="Budget consume regression",
        )
        pr.refresh_from_db()

        consume_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.CONSUME,
        )
        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.RELEASE,
        ).order_by("id")

        self.assertEqual(pr.actual_spend_entries.count(), 1)
        self.assertEqual(pr.get_actual_spent_total(), Decimal("550.00"))
        self.assertEqual(consume_entries.count(), 1)
        self.assertEqual(consume_entries.first().amount, Decimal("550.00"))
        self.assertEqual(release_entries.count(), 1)
        self.assertEqual(release_entries.first().amount, Decimal("550.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("50.00"))
        self.assertEqual(pr.fulfillment_status, PurchaseFulfillmentStatus.PARTIAL)

    def test_purchase_close_releases_remaining_reserved_budget(self):
        pr = PurchaseRequest.objects.create(
            title="Budget Close Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Close regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Tablet",
            quantity=Decimal("1"),
            unit_price=Decimal("600.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        task.approve(self.manager, comment="Approved for close test")
        pr.refresh_from_db()

        pr.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("550.00"),
            acting_user=self.requester,
            vendor_name="Close Vendor",
            reference_no="CLS-001",
            notes="Close budget regression",
        )
        pr.refresh_from_db()

        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("50.00"))

        pr.close_purchase(
            acting_user=self.requester,
            comment="Closed in budget regression test",
        )
        pr.refresh_from_db()

        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.RELEASE,
        ).order_by("id")

        self.assertEqual(pr.status, RequestStatus.CLOSED)
        self.assertEqual(pr.fulfillment_status, PurchaseFulfillmentStatus.COMPLETED)
        self.assertEqual(release_entries.count(), 2)
        self.assertEqual(release_entries[0].amount, Decimal("550.00"))
        self.assertEqual(release_entries[1].amount, Decimal("50.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_purchase_attachment_upload_and_delete_regression(self):
        self.client.login(username="req_purchase", password="testpass123")

        pr = PurchaseRequest.objects.create(
            title="Attachment Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Attachment regression test",
        )

        upload_file = SimpleUploadedFile(
            "quote.txt",
            b"vendor quote content",
            content_type="text/plain",
        )

        response = self.client.post(
            reverse("purchase:pr_upload_attachment", args=[pr.id]),
            data={
                "document_type": "QUOTE",
                "title": "Vendor Quote",
                "file": upload_file,
            },
        )
        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        self.assertEqual(pr.attachments.count(), 1)

        attachment = pr.attachments.first()
        self.assertEqual(attachment.document_type, "QUOTE")
        self.assertEqual(attachment.title, "Vendor Quote")

        response = self.client.post(
            reverse("purchase:pr_delete_attachment", args=[pr.id, attachment.id]),
        )
        self.assertEqual(response.status_code, 302)

        pr.refresh_from_db()
        self.assertEqual(pr.attachments.count(), 0)
        self.assertEqual(PurchaseRequestAttachment.objects.filter(pk=attachment.id).count(), 0)

    def test_purchase_create_generates_initial_content_audit(self):
        pr = PurchaseRequest.objects.create(
            title="Audit Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Audit create regression test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Mouse",
            quantity=Decimal("2"),
            unit_price=Decimal("25.00"),
        )

        pr._add_content_audit(
            action_type="HEADER_CREATED",
            changed_by=self.requester,
            notes="Purchase request created.",
        )
        pr._add_content_audit(
            action_type="LINE_ADDED",
            changed_by=self.requester,
            line_no=1,
            new_value="Mouse / Qty 2 / Unit Price 25.00",
            notes="Initial line added during create.",
        )

        audits = pr.content_audits.all()
        self.assertEqual(audits.count(), 2)
        self.assertTrue(audits.filter(action_type="HEADER_CREATED").exists())
        self.assertTrue(audits.filter(action_type="LINE_ADDED", line_no=1).exists())

    def test_purchase_edit_updates_content_audit(self):
        pr = PurchaseRequest.objects.create(
            title="Audit Edit Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Original justification",
        )

        pr._add_content_audit(
            action_type="HEADER_CREATED",
            changed_by=self.requester,
            notes="Purchase request created.",
        )

        pr.justification = "Updated justification"
        pr.save(update_fields=["justification"])

        pr._add_content_audit(
            action_type="HEADER_UPDATED",
            changed_by=self.requester,
            field_name="Justification",
            old_value="Original justification",
            new_value="Updated justification",
            notes="Header field updated.",
        )

        audits = pr.content_audits.filter(
            action_type="HEADER_UPDATED",
            field_name="Justification",
        )
        self.assertEqual(audits.count(), 1)

        audit = audits.first()
        self.assertEqual(audit.old_value, "Original justification")
        self.assertEqual(audit.new_value, "Updated justification")

    def test_purchase_only_requester_can_edit_draft(self):
        other_user = User.objects.create_user(
            username="other_purchase_user",
            password="testpass123",
            email="other_purchase_user@example.com",
        )

        pr = PurchaseRequest.objects.create(
            title="Permission Draft Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Permission test",
        )

        self.assertTrue(pr.can_user_edit(self.requester))
        self.assertFalse(pr.can_user_edit(other_user))

    def test_purchase_requester_cannot_edit_after_submit(self):
        pr = PurchaseRequest.objects.create(
            title="Permission Submitted Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Permission submit test",
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

        self.assertFalse(pr.can_user_edit(self.requester))

    def test_purchase_non_requester_cannot_upload_attachment(self):
        other_user = User.objects.create_user(
            username="other_purchase_attach",
            password="testpass123",
            email="other_purchase_attach@example.com",
        )

        pr = PurchaseRequest.objects.create(
            title="Permission Attachment Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Attachment permission test",
        )

        upload_file = SimpleUploadedFile(
            "quote.txt",
            b"unauthorized upload attempt",
            content_type="text/plain",
        )

        self.client.login(username="other_purchase_attach", password="testpass123")
        response = self.client.post(
            reverse("purchase:pr_upload_attachment", args=[pr.id]),
            data={
                "document_type": "QUOTE",
                "title": "Unauthorized Quote",
                "file": upload_file,
            },
        )

        self.assertEqual(response.status_code, 404)
        pr.refresh_from_db()
        self.assertEqual(pr.attachments.count(), 0)