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
    RequestType,
    DepartmentType,
    BudgetEntryType,
)
from projects.models import Project, ProjectBudgetEntry
from travel.models import (
    TravelRequest,
    TravelItinerary,
    TravelEstimatedExpenseLine,
    TravelRequestStatus,
    TravelRequestAttachment, 
    TravelRequestContentAudit
)


User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MEDIA_ROOT=tempfile.gettempdir(),
)
class TravelSmokeTest(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="req_travel",
            password="testpass123",
            email="req_travel@example.com",
        )
        self.manager = User.objects.create_user(
            username="mgr_travel",
            password="testpass123",
            email="mgr_travel@example.com",
        )

        self.department = Department.objects.create(
            dept_code="D-TRV-01",
            dept_name="Travel Dept",
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
            project_code="PJT-TRV-01",
            project_name="Travel Project",
            owning_department=self.department,
            budget_amount=Decimal("10000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            is_active=True,
        )

        self.rule = ApprovalRule.objects.create(
            rule_code="TRV-DEFAULT",
            rule_name="Travel Default Rule",
            request_type=RequestType.TRAVEL,
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

    def test_travel_submit_creates_task(self):
        self.client.login(username="req_travel", password="testpass123")

        tr = TravelRequest.objects.create(
            purpose="Business Trip",
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

        response = self.client.post(reverse("travel:tr_submit", args=[tr.id]))
        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(tr.get_approval_tasks_queryset().count(), 1)

    def test_travel_detail_page_loads(self):
        self.client.login(username="req_travel", password="testpass123")

        tr = TravelRequest.objects.create(
            purpose="Detail Travel",
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

        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Travel")

    def test_travel_full_workflow_regression(self):
        self.client.login(username="req_travel", password="testpass123")

        tr = TravelRequest.objects.create(
            purpose="Workflow Travel",
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
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(tr.get_approval_tasks_queryset().count(), 1)

        current_task = tr.get_current_task()
        self.assertIsNotNone(current_task)
        self.assertEqual(current_task.assigned_user, self.manager)

        current_task.approve(self.manager, comment="Approved in regression test")
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.APPROVED)

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("520.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Seattle Hotel",
            reference_no="HTL-001",
            expense_location="Seattle",
            notes="Regression actual expense",
        )
        tr.refresh_from_db()

        self.assertEqual(tr.actual_expense_lines.count(), 1)
        self.assertEqual(tr.actual_total, Decimal("520.00"))
        self.assertEqual(tr.status, TravelRequestStatus.EXPENSE_PENDING)

        tr.close_request(
            acting_user=self.requester,
            comment="Closed in regression test",
        )
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.CLOSED)

        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))
        self.assertEqual(response.status_code, 200)

    def test_travel_submit_sends_requester_and_approver_notifications(self):
        self.client.login(username="req_travel", password="testpass123")

        tr = TravelRequest.objects.create(
            purpose="Notify Travel",
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

        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("travel:tr_submit", args=[tr.id]))

        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(len(mail.outbox), 2)

        subjects = [message.subject for message in mail.outbox]
        recipients = [recipient for message in mail.outbox for recipient in message.to]

        self.assertTrue(any(tr.travel_no in subject and "submitted" in subject.lower() for subject in subjects))
        self.assertTrue(any(tr.travel_no in subject and "approval needed" in subject.lower() for subject in subjects))
        self.assertIn(self.requester.email, recipients)
        self.assertIn(self.manager.email, recipients)

    def test_travel_close_sends_requester_notification(self):
        tr = TravelRequest.objects.create(
            purpose="Close Notify Travel",
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
        tr.refresh_from_db()

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        task.approve(self.manager, comment="Approved for close notification test")
        tr.refresh_from_db()

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("520.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Seattle Hotel",
            reference_no="HTL-CLOSE-001",
            expense_location="Seattle",
            notes="Close notification regression",
        )
        tr.refresh_from_db()

        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            tr.close_request(
                acting_user=self.requester,
                comment="Trip fully completed",
            )

        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.CLOSED)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertIn(tr.travel_no, message.subject)
        self.assertIn("closed", message.subject.lower())
        self.assertIn(self.requester.email, message.to)

    def test_travel_submit_creates_budget_reserve_entry(self):
        tr = TravelRequest.objects.create(
            purpose="Budget Reserve Travel",
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

        reserve_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.RESERVE,
        )

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(reserve_entries.count(), 1)
        self.assertEqual(reserve_entries.first().amount, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("500.00"))

    def test_travel_return_releases_reserved_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Budget Return Travel",
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
        task = tr.get_current_task()
        self.assertIsNotNone(task)

        task.return_to_requester(self.manager, comment="Need revision")
        tr.refresh_from_db()

        reserve_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.RESERVE,
        )
        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.RELEASE,
        )

        self.assertEqual(tr.status, TravelRequestStatus.RETURNED)
        self.assertEqual(reserve_entries.count(), 1)
        self.assertEqual(release_entries.count(), 1)
        self.assertEqual(release_entries.first().amount, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_actual_expense_creates_consume_and_partial_release(self):
        tr = TravelRequest.objects.create(
            purpose="Budget Consume Travel",
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
        self.assertIsNotNone(task)
        task.approve(self.manager, comment="Approved for travel budget consume test")
        tr.refresh_from_db()

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("450.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Travel Vendor",
            reference_no="TRV-BUD-001",
            expense_location="Seattle",
            notes="Travel budget consume regression",
        )
        tr.refresh_from_db()

        consume_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.CONSUME,
        )
        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.RELEASE,
        ).order_by("id")

        self.assertEqual(tr.actual_expense_lines.count(), 1)
        self.assertEqual(tr.actual_total, Decimal("450.00"))
        self.assertEqual(consume_entries.count(), 1)
        self.assertEqual(consume_entries.first().amount, Decimal("450.00"))
        self.assertEqual(release_entries.count(), 1)
        self.assertEqual(release_entries.first().amount, Decimal("450.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("50.00"))

    def test_travel_close_releases_remaining_reserved_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Budget Close Travel",
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
        self.assertIsNotNone(task)
        task.approve(self.manager, comment="Approved for travel close test")
        tr.refresh_from_db()

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("450.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Travel Close Vendor",
            reference_no="TRV-CLS-001",
            expense_location="Seattle",
            notes="Travel close budget regression",
        )
        tr.refresh_from_db()

        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("50.00"))

        tr.close_request(
            acting_user=self.requester,
            comment="Closed in travel budget regression test",
        )
        tr.refresh_from_db()

        release_entries = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.RELEASE,
        ).order_by("id")

        self.assertEqual(tr.status, TravelRequestStatus.CLOSED)
        self.assertEqual(release_entries.count(), 2)
        self.assertEqual(release_entries[0].amount, Decimal("450.00"))
        self.assertEqual(release_entries[1].amount, Decimal("50.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_attachment_upload_and_delete_regression(self):
        self.client.login(username="req_travel", password="testpass123")

        tr = TravelRequest.objects.create(
            purpose="Attachment Travel",
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

        upload_file = SimpleUploadedFile(
            "itinerary.txt",
            b"flight itinerary content",
            content_type="text/plain",
        )

        response = self.client.post(
            reverse("travel:tr_upload_attachment", args=[tr.id]),
            data={
                "document_type": "ITINERARY",
                "title": "Flight Itinerary",
                "file": upload_file,
            },
        )
        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        self.assertEqual(tr.attachments.count(), 1)

        attachment = tr.attachments.first()
        self.assertEqual(attachment.document_type, "ITINERARY")
        self.assertEqual(attachment.title, "Flight Itinerary")

        response = self.client.post(
            reverse("travel:tr_delete_attachment", args=[tr.id, attachment.id]),
        )
        self.assertEqual(response.status_code, 302)

        tr.refresh_from_db()
        self.assertEqual(tr.attachments.count(), 0)
        self.assertEqual(TravelRequestAttachment.objects.filter(pk=attachment.id).count(), 0)

    def test_travel_create_generates_initial_content_audit(self):
        tr = TravelRequest.objects.create(
            purpose="Audit Travel",
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

        tr._add_content_audit(
            action_type="HEADER_CREATED",
            changed_by=self.requester,
            section="HEADER",
            notes="Travel request created.",
        )
        tr._add_content_audit(
            action_type="ITINERARY_ADDED",
            changed_by=self.requester,
            section="ITINERARY",
            line_no=1,
            new_value="San Jose -> Seattle / AIR",
            notes="Initial itinerary line added during create.",
        )

        audits = tr.content_audits.all()
        self.assertEqual(audits.count(), 2)
        self.assertTrue(audits.filter(section="HEADER", action_type="HEADER_CREATED").exists())
        self.assertTrue(audits.filter(section="ITINERARY", action_type="ITINERARY_ADDED", line_no=1).exists())

    def test_travel_edit_updates_content_audit(self):
        tr = TravelRequest.objects.create(
            purpose="Original Purpose",
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

        tr._add_content_audit(
            action_type="HEADER_CREATED",
            changed_by=self.requester,
            section="HEADER",
            notes="Travel request created.",
        )

        tr.purpose = "Updated Purpose"
        tr.save(update_fields=["purpose"])

        tr._add_content_audit(
            action_type="HEADER_UPDATED",
            changed_by=self.requester,
            section="HEADER",
            field_name="Purpose",
            old_value="Original Purpose",
            new_value="Updated Purpose",
            notes="Header field updated.",
        )

        audits = tr.content_audits.filter(action_type="HEADER_UPDATED", field_name="Purpose")
        self.assertEqual(audits.count(), 1)

        audit = audits.first()
        self.assertEqual(audit.old_value, "Original Purpose")
        self.assertEqual(audit.new_value, "Updated Purpose")

    def test_travel_only_requester_can_edit_draft(self):
        other_user = User.objects.create_user(
            username="other_travel_user",
            password="testpass123",
            email="other_travel_user@example.com",
        )

        tr = TravelRequest.objects.create(
            purpose="Permission Draft Travel",
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

        self.assertTrue(tr.can_user_edit(self.requester))
        self.assertFalse(tr.can_user_edit(other_user))

    def test_travel_requester_can_record_actual_expense_only_after_approved(self):
        tr = TravelRequest.objects.create(
            purpose="Permission Actual Expense Travel",
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

        self.assertFalse(tr.can_user_record_actual_expense(self.requester))

        tr.status = TravelRequestStatus.APPROVED
        tr.save(update_fields=["status"])

        self.assertTrue(tr.can_user_record_actual_expense(self.requester))

    def test_travel_non_requester_cannot_upload_attachment(self):
        other_user = User.objects.create_user(
            username="other_travel_attach",
            password="testpass123",
            email="other_travel_attach@example.com",
        )

        tr = TravelRequest.objects.create(
            purpose="Permission Attachment Travel",
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

        upload_file = SimpleUploadedFile(
            "itinerary.txt",
            b"unauthorized travel attachment",
            content_type="text/plain",
        )

        self.client.login(username="other_travel_attach", password="testpass123")
        response = self.client.post(
            reverse("travel:tr_upload_attachment", args=[tr.id]),
            data={
                "document_type": "ITINERARY",
                "title": "Unauthorized Itinerary",
                "file": upload_file,
            },
        )

        self.assertEqual(response.status_code, 404)
        tr.refresh_from_db()
        self.assertEqual(tr.attachments.count(), 0)