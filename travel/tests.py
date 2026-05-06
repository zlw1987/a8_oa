from datetime import date, timedelta
from decimal import Decimal

import tempfile

from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.contrib.contenttypes.models import ContentType

from approvals.models import ApprovalTask
from accounts.models import Department, UserDepartment
from approvals.models import ApprovalRule, ApprovalRuleStep
from common.choices import (
    ApproverType,
    RequestType,
    DepartmentType,
    BudgetEntryType,
    ApprovalTaskStatus,
    RequestStatus,
)
from projects.models import Project, ProjectBudgetEntry, ProjectMember, ProjectStatus
from travel.models import (
    TravelRequest,
    TravelItinerary,
    TravelEstimatedExpenseLine,
    TravelRequestStatus,
    TravelRequestAttachment, 
    TravelRequestContentAudit
)
from travel.services import (
    create_travel_request_from_forms,
    update_travel_request_from_forms,
)
from travel.forms import (
    TravelRequestForm,
    TravelItineraryCreateFormSet,
    TravelItineraryEditFormSet,
    TravelEstimatedExpenseCreateFormSet,
    TravelEstimatedExpenseEditFormSet,
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

        ProjectMember.objects.create(
            project=self.project,
            user=self.requester,
            is_active=True,
            added_by=self.manager,
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

    def _get_travel_task_and_viewer(self, travel_request):
        task = ApprovalTask.objects.filter(
            request_content_type=ContentType.objects.get_for_model(TravelRequest),
            request_object_id=travel_request.id,
        ).order_by("step_no", "id").first()
        self.assertIsNotNone(task)

        if task.assigned_user:
            return task, task.assigned_user

        candidate = task.candidates.filter(is_active=True).select_related("user").first()
        self.assertIsNotNone(candidate)
        return task, candidate.user

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

    def test_travel_form_shows_only_open_member_projects(self):
        open_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-OPEN",
            project_name="Travel Open Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        closed_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-CLOSED",
            project_name="Travel Closed Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )
        open_nonmember_project = Project.objects.create(
            project_code="PJT-TRV-NONMEMBER-OPEN",
            project_name="Travel Open Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        ProjectMember.objects.create(project=open_member_project, user=self.requester, is_active=True, added_by=self.manager)
        ProjectMember.objects.create(project=closed_member_project, user=self.requester, is_active=True, added_by=self.manager)

        form = TravelRequestForm(user=self.requester)

        project_ids = list(form.fields["project"].queryset.values_list("id", flat=True))
        self.assertIn(open_member_project.id, project_ids)
        self.assertNotIn(closed_member_project.id, project_ids)
        self.assertNotIn(open_nonmember_project.id, project_ids)

    def test_travel_form_shows_only_open_member_projects(self):
        open_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-OPEN",
            project_name="Travel Open Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        closed_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-CLOSED",
            project_name="Travel Closed Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )
        open_nonmember_project = Project.objects.create(
            project_code="PJT-TRV-NONMEMBER-OPEN",
            project_name="Travel Open Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        ProjectMember.objects.create(project=open_member_project, user=self.requester, is_active=True, added_by=self.manager)
        ProjectMember.objects.create(project=closed_member_project, user=self.requester, is_active=True, added_by=self.manager)

        form = TravelRequestForm(user=self.requester)

        project_ids = list(form.fields["project"].queryset.values_list("id", flat=True))
        self.assertIn(open_member_project.id, project_ids)
        self.assertNotIn(closed_member_project.id, project_ids)
        self.assertNotIn(open_nonmember_project.id, project_ids)

    def test_travel_form_rejects_non_member_project(self):
        nonmember_project = Project.objects.create(
            project_code="PJT-TRV-NONMEMBER",
            project_name="Travel Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        form = TravelRequestForm(
            data={
                "purpose": "Unauthorized Travel",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": nonmember_project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=3),
                "end_date": date.today() + timedelta(days=5),
                "origin_city": "San Jose",
                "destination_city": "Seattle",
                "currency": "USD",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_travel_form_rejects_closed_project_even_for_member(self):
        closed_project = Project.objects.create(
            project_code="PJT-TRV-CLOSED",
            project_name="Travel Closed Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )

        ProjectMember.objects.create(project=closed_project, user=self.requester, is_active=True, added_by=self.manager)

        form = TravelRequestForm(
            data={
                "purpose": "Closed Travel Project",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": closed_project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=3),
                "end_date": date.today() + timedelta(days=5),
                "origin_city": "San Jose",
                "destination_city": "Seattle",
                "currency": "USD",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_travel_form_shows_only_open_member_projects(self):
        open_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-OPEN",
            project_name="Travel Open Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )
        closed_member_project = Project.objects.create(
            project_code="PJT-TRV-MEMBER-CLOSED",
            project_name="Travel Closed Member Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )
        open_nonmember_project = Project.objects.create(
            project_code="PJT-TRV-NONMEMBER-OPEN",
            project_name="Travel Open Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        ProjectMember.objects.create(project=open_member_project, user=self.requester, is_active=True, added_by=self.manager)
        ProjectMember.objects.create(project=closed_member_project, user=self.requester, is_active=True, added_by=self.manager)

        form = TravelRequestForm(user=self.requester)

        project_ids = list(form.fields["project"].queryset.values_list("id", flat=True))
        self.assertIn(open_member_project.id, project_ids)
        self.assertNotIn(closed_member_project.id, project_ids)
        self.assertNotIn(open_nonmember_project.id, project_ids)

    def test_travel_form_rejects_non_member_project(self):
        nonmember_project = Project.objects.create(
            project_code="PJT-TRV-NONMEMBER",
            project_name="Travel Nonmember Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.OPEN,
            is_active=True,
        )

        form = TravelRequestForm(
            data={
                "purpose": "Unauthorized Travel",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": nonmember_project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=3),
                "end_date": date.today() + timedelta(days=5),
                "origin_city": "San Jose",
                "destination_city": "Seattle",
                "currency": "USD",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_travel_form_rejects_closed_project_even_for_member(self):
        closed_project = Project.objects.create(
            project_code="PJT-TRV-CLOSED",
            project_name="Travel Closed Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )

        ProjectMember.objects.create(project=closed_project, user=self.requester, is_active=True, added_by=self.manager)

        form = TravelRequestForm(
            data={
                "purpose": "Closed Travel Project",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": closed_project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=3),
                "end_date": date.today() + timedelta(days=5),
                "origin_city": "San Jose",
                "destination_city": "Seattle",
                "currency": "USD",
                "notes": "",
            },
            user=self.requester,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_travel_submit_rejects_closed_project_on_server_side(self):
        closed_project = Project.objects.create(
            project_code="PJT-TRV-SUBMIT-CLOSED",
            project_name="Travel Submit Closed Project",
            owning_department=self.department,
            budget_amount=Decimal("5000.00"),
            currency="USD",
            status=ProjectStatus.CLOSED,
            is_active=True,
        )

        ProjectMember.objects.create(project=closed_project, user=self.requester, is_active=True, added_by=self.manager)

        tr = TravelRequest.objects.create(
            purpose="Submit Closed Travel Project",
            requester=self.requester,
            request_department=self.department,
            project=closed_project,
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

        with self.assertRaises(ValidationError):
            tr.submit(acting_user=self.requester)

    def test_travel_department_manager_can_view_request_detail(self):
        tr = TravelRequest.objects.create(
            purpose="Manager Visible Travel",
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

        self.client.login(username="mgr_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.purpose)

    def test_travel_create_service_saves_itinerary_expense_and_audit(self):
        form = TravelRequestForm(
            data={
                "purpose": "Service Create Travel",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=3),
                "end_date": date.today() + timedelta(days=5),
                "origin_city": "San Jose",
                "destination_city": "Seattle",
                "currency": "USD",
                "notes": "",
            },
            user=self.requester,
        )

        itinerary_formset = TravelItineraryCreateFormSet(
            data={
                "itineraries-TOTAL_FORMS": "1",
                "itineraries-INITIAL_FORMS": "0",
                "itineraries-MIN_NUM_FORMS": "0",
                "itineraries-MAX_NUM_FORMS": "1000",
                "itineraries-0-line_no": "",
                "itineraries-0-trip_date": date.today() + timedelta(days=3),
                "itineraries-0-from_city": "San Jose",
                "itineraries-0-to_city": "Seattle",
                "itineraries-0-transport_type": "AIR",
                "itineraries-0-departure_time": "",
                "itineraries-0-arrival_time": "",
                "itineraries-0-notes": "",
            },
            prefix="itineraries",
        )

        itinerary_date = date.today() + timedelta(days=3)
        checkout_date = date.today() + timedelta(days=5)

        expense_formset = TravelEstimatedExpenseCreateFormSet(
            data={
                "expenses-TOTAL_FORMS": "1",
                "expenses-INITIAL_FORMS": "0",
                "expenses-MIN_NUM_FORMS": "0",
                "expenses-MAX_NUM_FORMS": "1000",
                "expenses-0-line_no": "",
                "expenses-0-expense_type": "HOTEL",
                "expenses-0-expense_date": itinerary_date,
                "expenses-0-estimated_amount": "500.00",
                "expenses-0-currency": "USD",
                "expenses-0-from_location": "",
                "expenses-0-to_location": "",
                "expenses-0-departure_dt": "",
                "expenses-0-arrival_dt": "",
                "expenses-0-expense_location": "Seattle",
                "expenses-0-checkin_date": itinerary_date,
                "expenses-0-checkout_date": checkout_date,
                "expenses-0-itinerary_line_no": "",
                "expenses-0-exception_reason": "",
                "expenses-0-notes": "",
            },
            prefix="expenses",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(itinerary_formset.is_valid(), itinerary_formset.errors)
        self.assertTrue(expense_formset.is_valid(), expense_formset.errors)

        tr = create_travel_request_from_forms(
            form=form,
            itinerary_formset=itinerary_formset,
            expense_formset=expense_formset,
            acting_user=self.requester,
        )

        tr.refresh_from_db()

        self.assertEqual(tr.requester, self.requester)
        self.assertEqual(tr.status, TravelRequestStatus.DRAFT)
        self.assertEqual(tr.itineraries.count(), 1)
        self.assertEqual(tr.estimated_expense_lines.count(), 1)
        self.assertEqual(tr.estimated_total, Decimal("500.00"))
        self.assertTrue(tr.content_audits.exists())

    def test_travel_update_service_updates_header_lines_and_audit(self):
        tr = TravelRequest.objects.create(
            purpose="Service Update Travel",
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

        itinerary = TravelItinerary.objects.create(
            travel_request=tr,
            line_no=1,
            trip_date=tr.start_date,
            from_city="San Jose",
            to_city="Seattle",
            transport_type="AIR",
        )

        expense = TravelEstimatedExpenseLine.objects.create(
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

        form = TravelRequestForm(
            data={
                "purpose": "Service Update Travel Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=4),
                "end_date": date.today() + timedelta(days=6),
                "origin_city": "San Jose",
                "destination_city": "Portland",
                "currency": "USD",
                "notes": "",
            },
            instance=tr,
            user=self.requester,
        )

        new_start = date.today() + timedelta(days=4)
        new_end = date.today() + timedelta(days=6)

        itinerary_formset = TravelItineraryEditFormSet(
            data={
                "itineraries-TOTAL_FORMS": "1",
                "itineraries-INITIAL_FORMS": "1",
                "itineraries-MIN_NUM_FORMS": "0",
                "itineraries-MAX_NUM_FORMS": "1000",
                "itineraries-0-id": itinerary.id,
                "itineraries-0-line_no": "1",
                "itineraries-0-trip_date": new_start,
                "itineraries-0-from_city": "San Jose",
                "itineraries-0-to_city": "Portland",
                "itineraries-0-transport_type": "AIR",
                "itineraries-0-departure_time": "",
                "itineraries-0-arrival_time": "",
                "itineraries-0-notes": "",
            },
            instance=tr,
            prefix="itineraries",
        )

        expense_formset = TravelEstimatedExpenseEditFormSet(
            data={
                "expenses-TOTAL_FORMS": "1",
                "expenses-INITIAL_FORMS": "1",
                "expenses-MIN_NUM_FORMS": "0",
                "expenses-MAX_NUM_FORMS": "1000",
                "expenses-0-id": expense.id,
                "expenses-0-line_no": "1",
                "expenses-0-expense_type": "HOTEL",
                "expenses-0-expense_date": new_start,
                "expenses-0-estimated_amount": "650.00",
                "expenses-0-currency": "USD",
                "expenses-0-from_location": "",
                "expenses-0-to_location": "",
                "expenses-0-departure_dt": "",
                "expenses-0-arrival_dt": "",
                "expenses-0-expense_location": "Portland",
                "expenses-0-checkin_date": new_start,
                "expenses-0-checkout_date": new_end,
                "expenses-0-itinerary_line_no": "",
                "expenses-0-exception_reason": "",
                "expenses-0-notes": "",
            },
            instance=tr,
            prefix="expenses",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(itinerary_formset.is_valid(), itinerary_formset.errors)
        self.assertTrue(expense_formset.is_valid(), expense_formset.errors)

        tr = update_travel_request_from_forms(
            travel_request=tr,
            form=form,
            itinerary_formset=itinerary_formset,
            expense_formset=expense_formset,
            acting_user=self.requester,
        )

        tr.refresh_from_db()

        self.assertEqual(tr.purpose, "Service Update Travel Revised")
        self.assertEqual(tr.destination_city, "Portland")
        self.assertEqual(tr.estimated_total, Decimal("650.00"))
        self.assertTrue(tr.content_audits.exists())

    def test_travel_submit_rolls_back_when_no_active_rule(self):
        tr = TravelRequest.objects.create(
            purpose="Rollback Submit Travel",
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

        ApprovalRule.objects.filter(request_type=RequestType.TRAVEL).update(is_active=False)

        with self.assertRaises(ValidationError):
            tr.submit(acting_user=self.requester)

        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.DRAFT)
        self.assertFalse(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).exists()
        )
        self.assertFalse(tr.get_approval_tasks_queryset().exists())

    def test_travel_record_actual_expense_rolls_back_when_overspend_exceeds_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Rollback Actual Expense Travel",
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

        before_actual_count = tr.actual_expense_lines.count()

        with self.assertRaises(ValidationError):
            tr.record_actual_expense(
                expense_type="HOTEL",
                expense_date=tr.start_date,
                actual_amount=Decimal("20000.00"),
                acting_user=self.requester,
                estimated_expense_line=estimated_line,
                currency="USD",
                vendor_name="Rollback Vendor",
                reference_no="RB-TR-001",
                expense_location="Seattle",
                notes="Should roll back",
            )

        tr.refresh_from_db()

        self.assertEqual(tr.actual_expense_lines.count(), before_actual_count)
        self.assertEqual(tr.get_actual_total(), Decimal("0.00"))
        self.assertFalse(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.CONSUME,
            ).exists()
        )

    def test_travel_full_lifecycle_budget_regression(self):
        tr = TravelRequest.objects.create(
            purpose="Full Lifecycle Travel",
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

        tr.refresh_estimated_total(commit=True)

        tr.submit(acting_user=self.requester)
        tr.refresh_from_db()

        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
                amount=Decimal("500.00"),
            ).exists()
        )

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.approve(self.manager, comment="Approve full lifecycle travel")
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.APPROVED)

        tr.record_actual_expense(
            expense_type="HOTEL",
            expense_date=tr.start_date,
            actual_amount=Decimal("450.00"),
            acting_user=self.requester,
            estimated_expense_line=estimated_line,
            currency="USD",
            vendor_name="Lifecycle Travel Vendor",
            reference_no="LC-TR-001",
            expense_location="Seattle",
            notes="Lifecycle actual expense",
        )
        tr.refresh_from_db()

        self.assertEqual(tr.get_actual_total(), Decimal("450.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("50.00"))

        tr.close_request(
            acting_user=self.requester,
            comment="Close lifecycle travel",
        )
        tr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        consume_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.CONSUME,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.CLOSED)
        self.assertEqual(reserve_total, Decimal("500.00"))
        self.assertEqual(consume_total, Decimal("450.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_submit_then_cancel_releases_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Cancel Lifecycle Travel",
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
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertTrue(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
                amount=Decimal("500.00"),
            ).exists()
        )

        tr.cancel(acting_user=self.requester)
        tr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.CANCELLED)
        self.assertEqual(reserve_total, Decimal("500.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_return_releases_reserved_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Return Lifecycle Travel",
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
        tr.refresh_from_db()

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.return_to_requester(self.manager, comment="Return for revision")
        tr.refresh_from_db()

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.RETURNED)
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_reject_releases_reserved_budget(self):
        tr = TravelRequest.objects.create(
            purpose="Reject Lifecycle Travel",
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
        tr.refresh_from_db()

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.reject(self.manager, comment="Rejected")
        tr.refresh_from_db()

        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.REJECTED)
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

    def test_travel_return_edit_resubmit_regression(self):
        tr = TravelRequest.objects.create(
            purpose="Return Resubmit Travel",
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

        itinerary = TravelItinerary.objects.create(
            travel_request=tr,
            line_no=1,
            trip_date=tr.start_date,
            from_city="San Jose",
            to_city="Seattle",
            transport_type="AIR",
        )

        expense = TravelEstimatedExpenseLine.objects.create(
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
        tr.refresh_from_db()

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.return_to_requester(self.manager, comment="Please revise and resubmit")
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.RETURNED)
        self.assertTrue(tr.can_user_edit(self.requester))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("0.00"))

        new_start = date.today() + timedelta(days=4)
        new_end = date.today() + timedelta(days=6)

        form = TravelRequestForm(
            data={
                "purpose": "Return Resubmit Travel Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "start_date": new_start,
                "end_date": new_end,
                "origin_city": "San Jose",
                "destination_city": "Portland",
                "currency": "USD",
                "notes": "",
            },
            instance=tr,
            user=self.requester,
        )

        itinerary_formset = TravelItineraryEditFormSet(
            data={
                "itineraries-TOTAL_FORMS": "1",
                "itineraries-INITIAL_FORMS": "1",
                "itineraries-MIN_NUM_FORMS": "0",
                "itineraries-MAX_NUM_FORMS": "1000",
                "itineraries-0-id": itinerary.id,
                "itineraries-0-line_no": "1",
                "itineraries-0-trip_date": new_start,
                "itineraries-0-from_city": "San Jose",
                "itineraries-0-to_city": "Portland",
                "itineraries-0-transport_type": "AIR",
                "itineraries-0-departure_time": "",
                "itineraries-0-arrival_time": "",
                "itineraries-0-notes": "",
            },
            instance=tr,
            prefix="itineraries",
        )

        expense_formset = TravelEstimatedExpenseEditFormSet(
            data={
                "expenses-TOTAL_FORMS": "1",
                "expenses-INITIAL_FORMS": "1",
                "expenses-MIN_NUM_FORMS": "0",
                "expenses-MAX_NUM_FORMS": "1000",
                "expenses-0-id": expense.id,
                "expenses-0-line_no": "1",
                "expenses-0-expense_type": "HOTEL",
                "expenses-0-expense_date": new_start,
                "expenses-0-estimated_amount": "650.00",
                "expenses-0-currency": "USD",
                "expenses-0-from_location": "",
                "expenses-0-to_location": "",
                "expenses-0-departure_dt": "",
                "expenses-0-arrival_dt": "",
                "expenses-0-expense_location": "Portland",
                "expenses-0-checkin_date": new_start,
                "expenses-0-checkout_date": new_end,
                "expenses-0-itinerary_line_no": "",
                "expenses-0-exception_reason": "",
                "expenses-0-notes": "",
            },
            instance=tr,
            prefix="expenses",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(itinerary_formset.is_valid(), itinerary_formset.errors)
        self.assertTrue(expense_formset.is_valid(), expense_formset.errors)

        tr = update_travel_request_from_forms(
            travel_request=tr,
            form=form,
            itinerary_formset=itinerary_formset,
            expense_formset=expense_formset,
            acting_user=self.requester,
        )
        tr.refresh_from_db()

        tr.submit(acting_user=self.requester)
        tr.refresh_from_db()

        reserve_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        release_total = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RELEASE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        active_task_count = tr.get_approval_tasks_queryset().filter(
            status__in=[
                ApprovalTaskStatus.WAITING,
                ApprovalTaskStatus.POOL,
                ApprovalTaskStatus.PENDING,
            ]
        ).count()

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(tr.purpose, "Return Resubmit Travel Revised")
        self.assertEqual(tr.destination_city, "Portland")
        self.assertEqual(tr.estimated_total, Decimal("650.00"))
        self.assertEqual(reserve_total, Decimal("1150.00"))
        self.assertEqual(release_total, Decimal("500.00"))
        self.assertEqual(tr.get_reserved_remaining_amount(), Decimal("650.00"))
        self.assertEqual(active_task_count, 1)
        self.assertIsNotNone(tr.get_current_task())

    def test_travel_detail_loads_for_historical_request_after_project_closed(self):
        tr = TravelRequest.objects.create(
            purpose="Historical Closed Project Travel",
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

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tr.purpose)
        self.assertContains(response, self.project.project_code)

    def test_travel_returned_request_cannot_resubmit_when_original_project_closed(self):
        tr = TravelRequest.objects.create(
            purpose="Returned Closed Project Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.RETURNED,
        )

        itinerary = TravelItinerary.objects.create(
            travel_request=tr,
            line_no=1,
            trip_date=tr.start_date,
            from_city="San Jose",
            to_city="Seattle",
            transport_type="AIR",
        )

        expense = TravelEstimatedExpenseLine.objects.create(
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

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        form = TravelRequestForm(
            data={
                "purpose": "Returned Closed Project Travel Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": self.project.id,
                "request_date": date.today(),
                "start_date": date.today() + timedelta(days=4),
                "end_date": date.today() + timedelta(days=6),
                "origin_city": "San Jose",
                "destination_city": "Portland",
                "currency": "USD",
                "notes": "",
            },
            instance=tr,
            user=self.requester,
        )

        itinerary_formset = TravelItineraryEditFormSet(
            data={
                "itineraries-TOTAL_FORMS": "1",
                "itineraries-INITIAL_FORMS": "1",
                "itineraries-MIN_NUM_FORMS": "0",
                "itineraries-MAX_NUM_FORMS": "1000",
                "itineraries-0-id": itinerary.id,
                "itineraries-0-line_no": "1",
                "itineraries-0-trip_date": date.today() + timedelta(days=4),
                "itineraries-0-from_city": "San Jose",
                "itineraries-0-to_city": "Portland",
                "itineraries-0-transport_type": "AIR",
                "itineraries-0-departure_time": "",
                "itineraries-0-arrival_time": "",
                "itineraries-0-notes": "",
            },
            instance=tr,
            prefix="itineraries",
        )

        expense_formset = TravelEstimatedExpenseEditFormSet(
            data={
                "expenses-TOTAL_FORMS": "1",
                "expenses-INITIAL_FORMS": "1",
                "expenses-MIN_NUM_FORMS": "0",
                "expenses-MAX_NUM_FORMS": "1000",
                "expenses-0-id": expense.id,
                "expenses-0-line_no": "1",
                "expenses-0-expense_type": "HOTEL",
                "expenses-0-expense_date": date.today() + timedelta(days=4),
                "expenses-0-estimated_amount": "650.00",
                "expenses-0-currency": "USD",
                "expenses-0-from_location": "",
                "expenses-0-to_location": "",
                "expenses-0-departure_dt": "",
                "expenses-0-arrival_dt": "",
                "expenses-0-expense_location": "Portland",
                "expenses-0-checkin_date": date.today() + timedelta(days=4),
                "expenses-0-checkout_date": date.today() + timedelta(days=6),
                "expenses-0-itinerary_line_no": "",
                "expenses-0-exception_reason": "",
                "expenses-0-notes": "",
            },
            instance=tr,
            prefix="expenses",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)
        self.assertTrue(itinerary_formset.is_valid(), itinerary_formset.errors)
        self.assertTrue(expense_formset.is_valid(), expense_formset.errors)

    def test_travel_returned_request_can_move_to_new_open_project_and_resubmit(self):
        tr = TravelRequest.objects.create(
            purpose="Move Project Travel",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.RETURNED,
        )

        itinerary = TravelItinerary.objects.create(
            travel_request=tr,
            line_no=1,
            trip_date=tr.start_date,
            from_city="San Jose",
            to_city="Seattle",
            transport_type="AIR",
        )

        expense = TravelEstimatedExpenseLine.objects.create(
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

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=["status"])

        new_project = Project.objects.create(
            project_code="PJT-TR-NEW-OPEN",
            project_name="New Open Travel Project",
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

        new_start = date.today() + timedelta(days=4)
        new_end = date.today() + timedelta(days=6)

        form = TravelRequestForm(
            data={
                "purpose": "Move Project Travel Revised",
                "requester": self.requester.id,
                "request_department": self.department.id,
                "project": new_project.id,
                "request_date": date.today(),
                "start_date": new_start,
                "end_date": new_end,
                "origin_city": "San Jose",
                "destination_city": "Portland",
                "currency": "USD",
                "notes": "",
            },
            instance=tr,
            user=self.requester,
        )

        itinerary_formset = TravelItineraryEditFormSet(
            data={
                "itineraries-TOTAL_FORMS": "1",
                "itineraries-INITIAL_FORMS": "1",
                "itineraries-MIN_NUM_FORMS": "0",
                "itineraries-MAX_NUM_FORMS": "1000",
                "itineraries-0-id": itinerary.id,
                "itineraries-0-line_no": "1",
                "itineraries-0-trip_date": new_start,
                "itineraries-0-from_city": "San Jose",
                "itineraries-0-to_city": "Portland",
                "itineraries-0-transport_type": "AIR",
                "itineraries-0-departure_time": "",
                "itineraries-0-arrival_time": "",
                "itineraries-0-notes": "",
            },
            instance=tr,
            prefix="itineraries",
        )

        expense_formset = TravelEstimatedExpenseEditFormSet(
            data={
                "expenses-TOTAL_FORMS": "1",
                "expenses-INITIAL_FORMS": "1",
                "expenses-MIN_NUM_FORMS": "0",
                "expenses-MAX_NUM_FORMS": "1000",
                "expenses-0-id": expense.id,
                "expenses-0-line_no": "1",
                "expenses-0-expense_type": "HOTEL",
                "expenses-0-expense_date": new_start,
                "expenses-0-estimated_amount": "650.00",
                "expenses-0-currency": "USD",
                "expenses-0-from_location": "",
                "expenses-0-to_location": "",
                "expenses-0-departure_dt": "",
                "expenses-0-arrival_dt": "",
                "expenses-0-expense_location": "Portland",
                "expenses-0-checkin_date": new_start,
                "expenses-0-checkout_date": new_end,
                "expenses-0-itinerary_line_no": "",
                "expenses-0-exception_reason": "",
                "expenses-0-notes": "",
            },
            instance=tr,
            prefix="expenses",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(itinerary_formset.is_valid(), itinerary_formset.errors)
        self.assertTrue(expense_formset.is_valid(), expense_formset.errors)

        tr = update_travel_request_from_forms(
            travel_request=tr,
            form=form,
            itinerary_formset=itinerary_formset,
            expense_formset=expense_formset,
            acting_user=self.requester,
        )
        tr.refresh_from_db()

        tr.submit(acting_user=self.requester)
        tr.refresh_from_db()

        self.assertEqual(tr.project, new_project)
        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(tr.estimated_total, Decimal("650.00"))

    def test_travel_submit_twice_does_not_duplicate_reserve_or_tasks(self):
        tr = TravelRequest.objects.create(
            purpose="Duplicate Submit Travel",
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
        tr.refresh_from_db()

        first_task_count = tr.get_approval_tasks_queryset().count()

        reserve_total_after_first_submit = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(reserve_total_after_first_submit, Decimal("500.00"))
        self.assertGreater(first_task_count, 0)

        with self.assertRaises(ValidationError):
            tr.submit(acting_user=self.requester)

        tr.refresh_from_db()

        reserve_total_after_second_submit = (
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.RESERVE,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        self.assertEqual(tr.status, TravelRequestStatus.PENDING_APPROVAL)
        self.assertEqual(reserve_total_after_second_submit, Decimal("500.00"))
        self.assertEqual(tr.get_approval_tasks_queryset().count(), first_task_count)

    def test_travel_cancelled_request_cannot_record_actual_expense(self):
        tr = TravelRequest.objects.create(
            purpose="Cancelled Travel No Expense",
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

        tr.refresh_estimated_total(commit=True)
        tr.submit(acting_user=self.requester)
        tr.cancel(acting_user=self.requester)
        tr.refresh_from_db()

        before_consume_count = ProjectBudgetEntry.objects.filter(
            project=self.project,
            source_type=RequestType.TRAVEL,
            source_id=tr.id,
            entry_type=BudgetEntryType.CONSUME,
        ).count()

        before_actual_count = tr.actual_expense_lines.count()

        with self.assertRaises(ValidationError):
            tr.record_actual_expense(
                expense_type="HOTEL",
                expense_date=tr.start_date,
                actual_amount=Decimal("100.00"),
                acting_user=self.requester,
                estimated_expense_line=estimated_line,
                currency="USD",
                vendor_name="Late Travel Vendor",
                reference_no="LATE-TR-001",
                expense_location="Seattle",
                notes="Should fail after cancel",
            )

        self.assertEqual(
            ProjectBudgetEntry.objects.filter(
                project=self.project,
                source_type=RequestType.TRAVEL,
                source_id=tr.id,
                entry_type=BudgetEntryType.CONSUME,
            ).count(),
            before_consume_count,
        )
        self.assertEqual(tr.actual_expense_lines.count(), before_actual_count)

    def test_travel_task_cannot_be_returned_twice(self):
        tr = TravelRequest.objects.create(
            purpose="Stale Return Travel",
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

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.return_to_requester(self.manager, comment="First return")
        task.refresh_from_db()
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.RETURNED)

        with self.assertRaises(ValidationError):
            task.return_to_requester(self.manager, comment="Second return should fail")

    def test_travel_rejected_task_cannot_be_approved_again(self):
        tr = TravelRequest.objects.create(
            purpose="Rejected Stale Travel",
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

        task = tr.get_current_task()
        self.assertIsNotNone(task)

        if task.status == ApprovalTaskStatus.POOL:
            task.claim(self.manager)
            task.refresh_from_db()

        task.reject(self.manager, comment="First reject")
        task.refresh_from_db()
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.REJECTED)

        with self.assertRaises(ValidationError):
            task.approve(self.manager, comment="Approve after reject should fail")

    def test_travel_released_task_old_assignee_cannot_return_without_reclaim(self):
        travel_rule = ApprovalRule.objects.filter(
            request_type=RequestType.TRAVEL,
            department=self.department,
            is_active=True,
        ).order_by("priority", "id").first()
        self.assertIsNotNone(travel_rule)

        step = travel_rule.steps.order_by("step_no", "id").first()
        self.assertIsNotNone(step)

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

        tr = TravelRequest.objects.create(
            purpose="Released Pool Travel",
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

        task = tr.get_current_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        task.claim(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.PENDING)

        task.release_to_pool(self.manager)
        task.refresh_from_db()
        self.assertEqual(task.status, ApprovalTaskStatus.POOL)

        with self.assertRaises(ValidationError):
            task.return_to_requester(self.manager, comment="Return after release should fail")

    def test_travel_released_task_can_be_reclaimed_and_rejected(self):
        travel_rule = ApprovalRule.objects.filter(
            request_type=RequestType.TRAVEL,
            department=self.department,
            is_active=True,
        ).order_by("priority", "id").first()
        self.assertIsNotNone(travel_rule)

        step = travel_rule.steps.order_by("step_no", "id").first()
        self.assertIsNotNone(step)

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

        tr = TravelRequest.objects.create(
            purpose="Reclaim Travel",
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

        task = tr.get_current_task()
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

        task.reject(self.manager, comment="Reject after reclaim")
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.REJECTED)

    def test_travel_second_candidate_claim_after_release_regression(self):
        other_approver = User.objects.create_user(
            username="alt_travel_approver",
            password="testpass123",
            email="alt_travel_approver@example.com",
        )

        travel_rule = ApprovalRule.objects.filter(
            request_type=RequestType.TRAVEL,
            department=self.department,
            is_active=True,
        ).order_by("priority", "id").first()
        self.assertIsNotNone(travel_rule)

        step = travel_rule.steps.order_by("step_no", "id").first()
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

        tr = TravelRequest.objects.create(
            purpose="Second Candidate Travel",
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

        task = tr.get_current_task()
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
            task.reject(self.manager, comment="Old assignee should fail")

        task.reject(other_approver, comment="New assignee rejects")
        tr.refresh_from_db()

        self.assertEqual(tr.status, TravelRequestStatus.REJECTED)

    def test_travel_detail_shows_matched_rule_and_task_assignment_label(self):
        tr = TravelRequest.objects.create(
            purpose="Explainability Travel",
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
        tr.refresh_from_db()

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matched Approval Rule")
        self.assertContains(response, "Current Task Ownership")
        self.assertContains(response, "Current Approval Action")

    def test_travel_detail_shows_project_budget_snapshot(self):
        tr = TravelRequest.objects.create(
            purpose="Budget Snapshot Travel",
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

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Budget Snapshot")
        self.assertContains(response, "Budget Meaning")
        self.assertContains(response, "Reserved Remaining for This Request")

    def test_travel_detail_shows_remaining_after_request(self):
        tr = TravelRequest.objects.create(
            purpose="Remaining Travel",
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

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remaining After This Request")

    def test_travel_submit_notification_contains_matched_rule_and_open_request_text(self):
        self.requester.email = "req_travel@example.com"
        self.requester.save(update_fields=["email"])

        self.manager.email = "mgr_travel@example.com"
        self.manager.save(update_fields=["email"])

        tr = TravelRequest.objects.create(
            purpose="Notification Travel",
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

        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            tr.submit(acting_user=self.requester)

        self.assertGreaterEqual(len(mail.outbox), 1)

        joined_body = "\n".join(message.body for message in mail.outbox)
        self.assertIn("Matched Approval Rule:", joined_body)
        self.assertIn("Next step:", joined_body)

    def test_travel_list_can_filter_by_status(self):
        draft_tr = TravelRequest.objects.create(
            purpose="Draft Travel Filter",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.DRAFT,
        )

        approved_tr = TravelRequest.objects.create(
            purpose="Approved Travel Filter",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Portland",
            currency="USD",
            status=TravelRequestStatus.APPROVED,
        )

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_list"), {"status": TravelRequestStatus.DRAFT})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, draft_tr.purpose)
        self.assertNotContains(response, approved_tr.purpose)

    def test_travel_list_can_filter_by_keyword(self):
        match_tr = TravelRequest.objects.create(
            purpose="Seattle Customer Visit",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=5),
            origin_city="San Jose",
            destination_city="Seattle",
            currency="USD",
            status=TravelRequestStatus.DRAFT,
        )

        other_tr = TravelRequest.objects.create(
            purpose="Internal Training",
            requester=self.requester,
            request_department=self.department,
            project=self.project,
            request_date=date.today(),
            start_date=date.today() + timedelta(days=4),
            end_date=date.today() + timedelta(days=6),
            origin_city="San Jose",
            destination_city="Austin",
            currency="USD",
            status=TravelRequestStatus.DRAFT,
        )

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_list"), {"keyword": "Seattle"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, match_tr.purpose)
        self.assertNotContains(response, other_tr.purpose)

    def test_travel_list_pagination_preserves_filter_query(self):
        for i in range(15):
            TravelRequest.objects.create(
                purpose=f"Draft Travel Page {i}",
                requester=self.requester,
                request_department=self.department,
                project=self.project,
                request_date=date.today(),
                start_date=date.today() + timedelta(days=3),
                end_date=date.today() + timedelta(days=5),
                origin_city="San Jose",
                destination_city="Seattle",
                currency="USD",
                status=TravelRequestStatus.DRAFT,
            )

        self.client.login(username="req_travel", password="testpass123")
        response = self.client.get(reverse("travel:tr_list"), {"status": TravelRequestStatus.DRAFT})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "status=DRAFT")

    def test_travel_detail_uses_neutral_action_labels(self):
        tr = TravelRequest.objects.create(
            purpose="Neutral Action Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to List")
        self.assertContains(response, "Edit Request")

    def test_travel_detail_still_shows_current_approval_action_section(self):
        tr = TravelRequest.objects.create(
            purpose="Shared Current Task Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Approval Action")
        self.assertContains(response, "Current Task Ownership")

    def test_travel_detail_still_shows_budget_meaning_section(self):
        tr = TravelRequest.objects.create(
            purpose="Shared Budget Meaning Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budget Meaning")
        self.assertContains(response, "Reserved Remaining for This Request")

    def test_travel_detail_still_shows_project_budget_snapshot_section(self):
        tr = TravelRequest.objects.create(
            purpose="Shared Budget Snapshot Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Budget Snapshot")
        self.assertContains(response, "This Request Total")
        self.assertContains(response, "Reserved Remaining")

    def test_travel_detail_uses_unified_bottom_section_titles(self):
        tr = TravelRequest.objects.create(
            purpose="Unified Section Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Estimated Expenses")
        self.assertContains(response, "Actual Expenses")
        self.assertContains(response, "Request History")

    def test_travel_detail_still_shows_attachments_section(self):
        tr = TravelRequest.objects.create(
            purpose="Shared Attachment Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attachments")
        self.assertContains(response, "Upload Attachment")

    def test_travel_detail_now_shows_approval_workflow_section(self):
        tr = TravelRequest.objects.create(
            purpose="Shared Workflow Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval Workflow")

    def test_travel_task_return_uses_generic_request_object_lookup(self):
        tr = TravelRequest.objects.create(
            purpose="Generic Lookup Return Travel",
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
        self.assertEqual(task.assigned_user, self.manager)

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("travel:task_return", args=[tr.id, task.id]),
            {"comment": "Return for update"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        tr.refresh_from_db()

        self.assertEqual(task.status, ApprovalTaskStatus.RETURNED)
        self.assertEqual(tr.status, TravelRequestStatus.RETURNED)

    def test_travel_detail_current_task_shows_due_fields(self):
        tr = TravelRequest.objects.create(
            purpose="Due Field Travel",
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

        task, viewer = self._get_travel_task_and_viewer(tr)

        self.client.force_login(viewer)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Approval Action")
        self.assertContains(response, "Due At")
        self.assertContains(response, "Due Status")
        self.assertContains(response, "On Time")

    def test_travel_detail_approval_workflow_shows_due_fields(self):
        tr = TravelRequest.objects.create(
            purpose="Workflow Due Travel",
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

        task, viewer = self._get_travel_task_and_viewer(tr)

        self.client.force_login(viewer)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval Workflow")
        self.assertContains(response, "Due At")
        self.assertContains(response, "Due Status")

    def test_travel_detail_current_task_shows_overdue_status(self):
        tr = TravelRequest.objects.create(
            purpose="Overdue Travel",
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

        task, viewer = self._get_travel_task_and_viewer(tr)
        task.due_at = timezone.now() - timedelta(days=2)
        task.save(update_fields=["due_at"])

        self.client.force_login(viewer)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due Status")
        self.assertContains(response, "Overdue by")

    def test_travel_submit_creates_first_task_with_due_at(self):
        tr = TravelRequest.objects.create(
            purpose="Travel Task Due At Test",
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
        self.assertIsNotNone(task.due_at)

    def test_travel_detail_shows_notification_activity_section(self):
        tr = TravelRequest.objects.create(
            purpose="Notification Activity Travel",
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

        self.client.force_login(self.requester)
        response = self.client.get(reverse("travel:tr_detail", args=[tr.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Activity")