from datetime import date, timedelta
from decimal import Decimal
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db.models import Sum

from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import (
    ApproverType,
    RequestStatus,
    RequestType,
    DepartmentType,
    BudgetEntryType,
    ApprovalTaskStatus,
)
from projects.models import Project, ProjectBudgetEntry, ProjectMember, ProjectStatus
from purchase.forms import PurchaseRequestForm, PurchaseRequestLineCreateFormSet, PurchaseRequestLineEditFormSet
from purchase.models import (
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseFulfillmentStatus,
    PurchaseRequestAttachment, 
    PurchaseRequestContentAudit,
)
from purchase.services import (
    create_purchase_request_from_forms,
    update_purchase_request_from_forms,
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

        ProjectMember.objects.create(
            project=self.project,
            user=self.requester,
            is_active=True,
            added_by=self.manager,
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

    def test_purchase_form_shows_only_open_member_projects(self):
        open_member_project = Project.objects.create(
            project_code="PJT-PUR-MEMBER-OPEN",
            project_name="Purchase Open Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        closed_member_project = Project.objects.create(
            project_code="PJT-PUR-MEMBER-CLOSED",
            project_name="Purchase Closed Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )
        open_nonmember_project = Project.objects.create(
            project_code="PJT-PUR-NONMEMBER-OPEN",
            project_name="Purchase Open Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        ProjectMember.objects.create(project=open_member_project, user=self.requester, is_active=True, added_by=self.manager)
        ProjectMember.objects.create(project=closed_member_project, user=self.requester, is_active=True, added_by=self.manager)

        form = PurchaseRequestForm(user=self.requester)

        project_ids = list(form.fields["project"].queryset.values_list("id", flat=True))
        self.assertIn(open_member_project.id, project_ids)
        self.assertNotIn(closed_member_project.id, project_ids)
        self.assertNotIn(open_nonmember_project.id, project_ids)

    def test_purchase_form_rejects_non_member_project(self):
        nonmember_project = Project.objects.create(
            project_code="PJT-PUR-NONMEMBER",
            project_name="Purchase Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        form = PurchaseRequestForm(
            data={
                "title": "Unauthorized Purchase",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": nonmember_project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Trying to use nonmember project",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_purchase_submit_rejects_closed_project_on_server_side(self):
        closed_project = Project.objects.create(
            project_code="PJT-PUR-SUBMIT-CLOSED",
            project_name="Purchase Submit Closed Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )

        ProjectMember.objects.create(project=closed_project, user=self.requester, is_active=True, added_by=self.manager)

        pr = PurchaseRequest.objects.create(
            title="Submit Closed Project Purchase",
            requester=self.requester,
            request_department=self.department,
            project=closed_project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Closed project submit server-side check",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Server Check Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

        with self.assertRaises(ValidationError):
            pr.submit(acting_user=self.requester)
        
    def test_purchase_form_shows_only_open_member_projects(self):
        open_member_project = Project.objects.create(
            project_code="PJT-PUR-MEMBER-OPEN",
            project_name="Purchase Open Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        closed_member_project = Project.objects.create(
            project_code="PJT-PUR-MEMBER-CLOSED",
            project_name="Purchase Closed Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )
        open_nonmember_project = Project.objects.create(
            project_code="PJT-PUR-NONMEMBER-OPEN",
            project_name="Purchase Open Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        ProjectMember.objects.create(project=open_member_project, user=self.requester, is_active=True, added_by=self.manager)
        ProjectMember.objects.create(project=closed_member_project, user=self.requester, is_active=True, added_by=self.manager)

        form = PurchaseRequestForm(user=self.requester)

        project_ids = list(form.fields["project"].queryset.values_list("id", flat=True))
        self.assertIn(open_member_project.id, project_ids)
        self.assertNotIn(closed_member_project.id, project_ids)
        self.assertNotIn(open_nonmember_project.id, project_ids)

    def test_purchase_form_rejects_closed_project_even_for_member(self):
        closed_project = Project.objects.create(
            project_code="PJT-PUR-CLOSED",
            project_name="Purchase Closed Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )

        ProjectMember.objects.create(project=closed_project, user=self.requester, is_active=True, added_by=self.manager)

        form = PurchaseRequestForm(
            data={
                "title": "Closed Project Purchase",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": closed_project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Trying to use closed project",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_purchase_department_manager_can_view_request_detail(self):
        pr = PurchaseRequest.objects.create(
            title="Manager Visible Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Department manager visibility test",
        )

        self.client.login(username="mgr_purchase", password="testpass123")
        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.title)

    def test_purchase_create_service_saves_lines_and_audit(self):
        form = PurchaseRequestForm(
            data={
                "title": "Service Create Purchase",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Service create test",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            user=self.requester,
        )

        formset = PurchaseRequestLineCreateFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-line_no": "",
                "lines-0-item_name": "Keyboard",
                "lines-0-item_description": "Mechanical keyboard",
                "lines-0-quantity": "2",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "80.00",
                "lines-0-notes": "",
            },
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        pr = create_purchase_request_from_forms(
            form=form,
            formset=formset,
            acting_user=self.requester,
            action="draft",
        )

        pr.refresh_from_db()

        self.assertEqual(pr.requester, self.requester)
        self.assertEqual(pr.status, RequestStatus.DRAFT)
        self.assertEqual(pr.lines.count(), 1)
        self.assertEqual(pr.estimated_total, Decimal("160.00"))
        self.assertTrue(pr.content_audits.exists())

    def test_purchase_update_service_can_submit_request(self):
        pr = PurchaseRequest.objects.create(
            title="Service Update Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Original",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Mouse",
            quantity=Decimal("1"),
            unit_price=Decimal("20.00"),
        )
        pr.estimated_total = pr.get_lines_total()
        pr.save(update_fields=["estimated_total"])

        form = PurchaseRequestForm(
            data={
                "title": "Service Update Purchase Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Updated by service",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            instance=pr,
            user=self.requester,
        )

        formset = PurchaseRequestLineEditFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-id": pr.lines.first().id,
                "lines-0-line_no": "1",
                "lines-0-item_name": "Monitor",
                "lines-0-item_description": "",
                "lines-0-quantity": "2",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "100.00",
                "lines-0-notes": "",
            },
            instance=pr,
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        pr = update_purchase_request_from_forms(
            purchase_request=pr,
            form=form,
            formset=formset,
            acting_user=self.requester,
            action="submit",
        )

        pr.refresh_from_db()

        self.assertEqual(pr.title, "Service Update Purchase Revised")
        self.assertEqual(pr.estimated_total, Decimal("200.00"))
        self.assertNotEqual(pr.status, RequestStatus.DRAFT)
        self.assertTrue(pr.content_audits.exists())
        self.assertTrue(pr.approval_tasks.exists())

    def test_purchase_create_service_rolls_back_on_submit_failure(self):
        self.rule.is_active = False
        self.rule.save(update_fields=["is_active"])

        form = PurchaseRequestForm(
            data={
                "title": "Rollback Create Purchase",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Rollback create test",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            user=self.requester,
        )

        formset = PurchaseRequestLineCreateFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-line_no": "",
                "lines-0-item_name": "Rollback Item",
                "lines-0-item_description": "",
                "lines-0-quantity": "1",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "50.00",
                "lines-0-notes": "",
            },
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        before_count = PurchaseRequest.objects.count()

        with self.assertRaises(ValidationError):
            create_purchase_request_from_forms(
                form=form,
                formset=formset,
                acting_user=self.requester,
                action="submit",
            )

        self.assertEqual(PurchaseRequest.objects.count(), before_count)
        self.assertFalse(
            PurchaseRequest.objects.filter(title="Rollback Create Purchase").exists()
        )

    def test_purchase_update_service_rolls_back_on_submit_failure(self):
        pr = PurchaseRequest.objects.create(
            title="Rollback Update Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Original justification",
        )

        line = PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Original Item",
            quantity=Decimal("1"),
            unit_price=Decimal("20.00"),
        )
        pr.estimated_total = pr.get_lines_total()
        pr.save(update_fields=["estimated_total"])

        self.rule.is_active = False
        self.rule.save(update_fields=["is_active"])

        form = PurchaseRequestForm(
            data={
                "title": "Rollback Update Purchase Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Revised justification",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            instance=pr,
            user=self.requester,
        )

        formset = PurchaseRequestLineEditFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-id": line.id,
                "lines-0-line_no": "1",
                "lines-0-item_name": "Revised Item",
                "lines-0-item_description": "",
                "lines-0-quantity": "2",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "100.00",
                "lines-0-notes": "",
            },
            instance=pr,
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        with self.assertRaises(ValidationError):
            update_purchase_request_from_forms(
                purchase_request=pr,
                form=form,
                formset=formset,
                acting_user=self.requester,
                action="submit",
            )

        pr.refresh_from_db()
        line.refresh_from_db()

        self.assertEqual(pr.title, "Rollback Update Purchase")
        self.assertEqual(pr.justification, "Original justification")
        self.assertEqual(pr.status, RequestStatus.DRAFT)
        self.assertEqual(pr.estimated_total, Decimal("20.00"))
        self.assertEqual(line.item_name, "Original Item")
        self.assertEqual(line.quantity, Decimal("1.00"))
        self.assertEqual(line.unit_price, Decimal("20.00"))

    def test_purchase_full_lifecycle_budget_regression(self):
        pr = PurchaseRequest.objects.create(
            title="Full Lifecycle Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Full lifecycle purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Lifecycle Monitor",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
                amount=Decimal("500.00"),
            ).exists()
        )

        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.approve(self.manager, comment="Approve full lifecycle purchase")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)

        pr.record_actual_spend(
            spend_date=date.today(),
            amount=Decimal("450.00"),
            acting_user=self.requester,
            vendor_name="Lifecycle Vendor",
            reference_no="LC-PR-001",
            notes="Lifecycle actual spend",
        )
        pr.refresh_from_db()

        self.assertEqual(pr.get_actual_spent_total(), Decimal("450.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("50.00"))

        pr.close_purchase(
            acting_user=self.requester,
            comment="Close lifecycle purchase",
        )
        pr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        consume_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.CONSUME,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.CLOSED)
        self.assertEqual(reserve_total, Decimal("500.00"))
        self.assertEqual(consume_total, Decimal("450.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_purchase_submit_then_cancel_releases_budget_and_cancels_tasks(self):
        pr = PurchaseRequest.objects.create(
            title="Cancel Lifecycle Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Cancel lifecycle purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Cancel Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
                amount=Decimal("500.00"),
            ).exists()
        )
        self.assertTrue(pr.approval_tasks.exists())

        pr.cancel(acting_user=self.requester)
        pr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.CANCELLED)
        self.assertEqual(reserve_total, Decimal("500.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

        active_task_count = pr.approval_tasks.filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ).count()
        self.assertEqual(active_task_count, 0)

    def test_purchase_return_releases_budget_and_cancels_remaining_tasks(self):
        pr = PurchaseRequest.objects.create(
            title="Return Lifecycle Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Return lifecycle purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Return Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.return_to_requester(self.manager, comment="Return for revision")
        pr.refresh_from_db()

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.RETURNED)
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

        active_task_count = pr.approval_tasks.filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ).count()
        self.assertEqual(active_task_count, 0)

    def test_purchase_reject_releases_budget_and_cancels_remaining_tasks(self):
        pr = PurchaseRequest.objects.create(
            title="Reject Lifecycle Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Reject lifecycle purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Reject Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.reject(self.manager, comment="Rejected")
        pr.refresh_from_db()

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.REJECTED)
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

        active_task_count = pr.approval_tasks.filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ).count()
        self.assertEqual(active_task_count, 0)

    def test_purchase_return_edit_resubmit_regression(self):
        pr = PurchaseRequest.objects.create(
            title="Return Resubmit Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Return and resubmit purchase test",
        )

        line = PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Original Purchase Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )
        pr.estimated_total = pr.get_lines_total()
        pr.save(update_fields=["estimated_total"])

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.return_to_requester(self.manager, comment="Please revise and resubmit")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.RETURNED)
        self.assertTrue(pr.can_user_edit(self.requester))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("0.00"))

        form = PurchaseRequestForm(
            data={
                "title": "Return Resubmit Purchase Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=10),
                "currency": "USD",
                "justification": "Revised after return",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            instance=pr,
            user=self.requester,
        )

        formset = PurchaseRequestLineEditFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-id": line.id,
                "lines-0-line_no": "1",
                "lines-0-item_name": "Revised Purchase Item",
                "lines-0-item_description": "",
                "lines-0-quantity": "1",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "600.00",
                "lines-0-notes": "",
            },
            instance=pr,
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        pr = update_purchase_request_from_forms(
            purchase_request=pr,
            form=form,
            formset=formset,
            acting_user=self.requester,
            action="submit",
        )
        pr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        active_task_count = pr.approval_tasks.filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ).count()

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(pr.title, "Return Resubmit Purchase Revised")
        self.assertEqual(pr.estimated_total, Decimal("600.00"))
        self.assertEqual(reserve_total, Decimal("1100.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(pr.get_reserved_remaining_amount(), Decimal("600.00"))
        self.assertEqual(active_task_count, 1)
        self.assertIsNotNone(pr.get_current_task())

    def test_purchase_detail_loads_for_historical_request_after_project_closed(self):
        pr = PurchaseRequest.objects.create(
            title="Historical Closed Project Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Historical closed project detail test",
        )

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        self.client.login(username="req_purchase", password="testpass123")
        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pr.title)
        self.assertContains(response, self.project.project_code)

    def test_purchase_returned_request_cannot_resubmit_when_original_project_closed(self):
        pr = PurchaseRequest.objects.create(
            title="Returned Closed Project Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Returned closed project resubmit test",
            status=RequestStatus.RETURNED,
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Returned Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )
        pr.estimated_total = pr.get_lines_total()
        pr.save(update_fields=["estimated_total"])

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        form = PurchaseRequestForm(
            data={
                "title": "Returned Closed Project Purchase Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Try resubmit with closed project",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            instance=pr,
            user=self.requester,
        )

        formset = PurchaseRequestLineEditFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-id": pr.lines.first().id,
                "lines-0-line_no": "1",
                "lines-0-item_name": "Returned Item Revised",
                "lines-0-item_description": "",
                "lines-0-quantity": "1",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "500.00",
                "lines-0-notes": "",
            },
            instance=pr,
            prefix="lines",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_purchase_returned_request_can_move_to_new_open_project_and_resubmit(self):
        pr = PurchaseRequest.objects.create(
            title="Move Project Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Move to new project test",
            status=RequestStatus.RETURNED,
        )

        line = PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Move Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )
        pr.estimated_total = pr.get_lines_total()
        pr.save(update_fields=["estimated_total"])

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        new_project = Project.objects.create(
            project_code="PJT-PUR-NEW-OPEN",
            project_name="New Open Purchase Project",
            owning_department=self.department,
            budget_amount=Decimal("8000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        ProjectMember.objects.create(
            project=new_project,
            user=self.requester,
            is_active=True,
            added_by=self.manager,
        )

        form = PurchaseRequestForm(
            data={
                "title": "Move Project Purchase Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": new_project.id,
                "request_date": date.today(),
                "needed_by_date": date.today() + timedelta(days=7),
                "currency": "USD",
                "justification": "Move to new open project",
                "vendor_suggestion": "",
                "delivery_location": "",
                "notes": "",
            },
            instance=pr,
            user=self.requester,
        )

        formset = PurchaseRequestLineEditFormSet(
            data={
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-id": line.id,
                "lines-0-line_no": "1",
                "lines-0-item_name": "Move Item Revised",
                "lines-0-item_description": "",
                "lines-0-quantity": "1",
                "lines-0-uom": "EA",
                "lines-0-unit_price": "600.00",
                "lines-0-notes": "",
            },
            instance=pr,
            prefix="lines",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        pr = update_purchase_request_from_forms(
            purchase_request=pr,
            form=form,
            formset=formset,
            acting_user=self.requester,
            action="submit",
        )
        pr.refresh_from_db()

        self.assertEqual(pr.project, new_project)
        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(pr.estimated_total, Decimal("600.00"))

    def test_purchase_submit_twice_does_not_duplicate_reserve_or_tasks(self):
        pr = PurchaseRequest.objects.create(
            title="Duplicate Submit Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Duplicate submit guard test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Duplicate Submit Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        first_task_count = pr.approval_tasks.count()

        reserve_total_after_first_submit = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(reserve_total_after_first_submit, Decimal("500.00"))
        self.assertGreater(first_task_count, 0)

        with self.assertRaises(ValidationError):
            pr.submit(acting_user=self.requester)

        pr.refresh_from_db()

        reserve_total_after_second_submit = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(pr.status, RequestStatus.SUBMITTED)
        self.assertEqual(reserve_total_after_second_submit, Decimal("500.00"))
        self.assertEqual(pr.approval_tasks.count(), first_task_count)

    def test_purchase_closed_request_cannot_record_actual_spend(self):
        pr = PurchaseRequest.objects.create(
            title="Closed Purchase No Spend",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Closed purchase spend guard test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Closed Purchase Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.approve(self.manager, comment="Approve before close")
        pr.refresh_from_db()

        pr.close_purchase(
            acting_user=self.requester,
            comment="Close before invalid spend attempt",
        )
        pr.refresh_from_db()

        before_consume_count = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.PURCHASE,
            source_id=pr.id,
            entry_type=BudgetEntryType.CONSUME,
        ).count()

        with self.assertRaises(ValidationError):
            pr.record_actual_spend(
                spend_date=date.today(),
                amount=Decimal("100.00"),
                acting_user=self.requester,
                vendor_name="Late Vendor",
                reference_no="LATE-PR-001",
                notes="Should fail after close",
            )

        self.assertEqual(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.PURCHASE,
                source_id=pr.id,
                entry_type=BudgetEntryType.CONSUME,
            ).count(),
            before_consume_count,
        )

    def test_purchase_task_cannot_be_approved_twice(self):
        pr = PurchaseRequest.objects.create(
            title="Stale Approve Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Task stale approve test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Approve Twice Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.approve(self.manager, comment="First approval")
        task.refresh_from_db()
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)

        with self.assertRaises(ValidationError):
            task.approve(self.manager, comment="Second approval should fail")

    def test_purchase_cancelled_request_task_cannot_be_approved_after_system_cancel(self):
        pr = PurchaseRequest.objects.create(
            title="Cancelled Task Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Cancelled task stale action test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Cancel Task Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        pr.cancel(acting_user=self.requester)
        pr.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.CANCELLED)
        self.assertNotIn(task.status, [ApprovalTaskStatus.POOL, ApprovalTaskStatus.PENDING])

        with self.assertRaises(ValidationError):
            task.approve(self.manager, comment="Approve after cancel should fail")

    def test_purchase_released_task_old_assignee_cannot_approve_without_reclaim(self):
        step = self.rule.steps.order_by("step_no", "id").first()
        step.approver_type = ApproverType.DEPARTMENT_APPROVER
        step.approver_department = self.department
        step.save(update_fields=["approver_type", "approver_department"])

        manager_link, _ = UserDepartment.objects.get_or_create(
            user=self.manager,
            department=self.department,
            defaults={
                "is_active": True,
                "can_approve": True,
            },
        )
        if not manager_link.is_active or not manager_link.can_approve:
            manager_link.is_active = True
            manager_link.can_approve = True
            manager_link.save(update_fields=["is_active", "can_approve"])

        pr = PurchaseRequest.objects.create(
            title="Released Pool Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Release to pool stale approve test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Released Pool Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        task.claim(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)

        task.release_to_pool(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        with self.assertRaises(ValidationError):
            task.approve(self.manager, comment="Approve after release should fail")

    def test_purchase_released_task_can_be_reclaimed_and_approved(self):
        step = self.rule.steps.order_by("step_no", "id").first()
        step.approver_type = ApproverType.DEPARTMENT_APPROVER
        step.approver_department = self.department
        step.save(update_fields=["approver_type", "approver_department"])

        manager_link, _ = UserDepartment.objects.get_or_create(
            user=self.manager,
            department=self.department,
            defaults={
                "is_active": True,
                "can_approve": True,
            },
        )
        if not manager_link.is_active or not manager_link.can_approve:
            manager_link.is_active = True
            manager_link.can_approve = True
            manager_link.save(update_fields=["is_active", "can_approve"])

        pr = PurchaseRequest.objects.create(
            title="Reclaim Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Reclaim purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Reclaim Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        task.claim(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)

        task.release_to_pool(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        task.claim(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)

        task.approve(self.manager, comment="Approve after reclaim")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)

    def test_purchase_second_candidate_claim_after_release_regression(self):
        other_approver = User.objects.create_user(
            username="alt_purchase_approver",
            password="testpass123",
            email="alt_purchase_approver@example.com",
        )

        rule = ApprovalRule.objects.filter(
            request_type=RequestType.PURCHASE,
            department=self.department,
            is_active=True,
        ).order_by("priority", "id").first()
        self.assertIsNotNone(rule)

        step = rule.steps.order_by("step_no", "id").first()
        self.assertIsNotNone(step)

        step.approver_type = ApproverType.DEPARTMENT_APPROVER
        step.approver_department = self.department
        step.save(update_fields=["approver_type", "approver_department"])

        for approver in [self.manager, other_approver]:
            link, _ = UserDepartment.objects.get_or_create(
                user=approver,
                department=self.department,
                defaults={
                    "is_active": True,
                    "can_approve": True,
                },
            )
            if not link.is_active or not link.can_approve:
                link.is_active = True
                link.can_approve = True
                link.save(update_fields=["is_active", "can_approve"])

        pr = PurchaseRequest.objects.create(
            title="Second Candidate Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Second candidate pool claim test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Pool Claim Item",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
        )

        pr.submit(acting_user=self.requester)
        task = pr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        task.claim(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, self.manager)

        with self.assertRaises(ValidationError):
            task.claim(other_approver)

        task.release_to_pool(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)
        self.assertIsNone(task.assigned_user)

        task.claim(other_approver)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)
        self.assertEqual(task.assigned_user, other_approver)

        with self.assertRaises(ValidationError):
            task.approve(self.manager, comment="Old assignee should fail")

        task.approve(other_approver, comment="New assignee approves")
        pr.refresh_from_db()

        self.assertEqual(pr.status, RequestStatus.APPROVED)

    def test_purchase_detail_shows_matched_rule_and_task_assignment_label(self):
        pr = PurchaseRequest.objects.create(
            title="Explainability Purchase",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            needed_by_date=date.today() + timedelta(days=7),
            currency="USD",
            justification="Explainability purchase test",
        )

        PurchaseRequestLine.objects.create(
            request=pr,
            line_no=1,
            item_name="Explain Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

        pr.submit(acting_user=self.requester)
        pr.refresh_from_db()

        self.client.login(username="req_purchase", password="testpass123")
        response = self.client.get(reverse("purchase:pr_detail", args=[pr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matched Approval Rule")
        self.assertContains(response, "Current Task Ownership")