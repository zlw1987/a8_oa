from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from approvals.models import (
    ApprovalNotificationLog,
    ApprovalNotificationType,
    ApprovalNotificationStatus,
    ApprovalTask,
    ApprovalTaskStatus,
)


class Command(BaseCommand):
    help = "Send escalation emails for seriously overdue approval tasks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without actually sending emails.",
        )

    def _log_notification(
        self,
        *,
        task_id,
        notification_type,
        recipient_email,
        subject,
        body,
        status,
        command_name,
        error_message="",
    ):
        ApprovalNotificationLog.objects.create(
            task_id=task_id,
            notification_type=notification_type,
            recipient_email=recipient_email,
            subject=subject,
            body_preview=body[:1000],
            status=status,
            error_message=error_message,
            triggered_by_command=command_name,
        )

    def _build_task_payload(self, task, overdue_days):
        request_obj = task.get_request_object() if hasattr(task, "get_request_object") else None
        requester = getattr(request_obj, "requester", None) if request_obj else None

        request_no = getattr(task, "request_no", None)
        if not request_no and request_obj is not None:
            request_no = (
                getattr(request_obj, "pr_no", None)
                or getattr(request_obj, "travel_no", None)
                or str(task.request_object_id)
            )

        request_title = getattr(task, "request_title", None)
        if not request_title and request_obj is not None:
            request_title = (
                getattr(request_obj, "title", None)
                or getattr(request_obj, "purpose", None)
                or "-"
            )

        return {
            "task_id": task.id,
            "request_type": getattr(task, "request_type_label", None)
            or ("Purchase" if task.purchase_request_id else "Travel"),
            "request_no": request_no or "-",
            "request_title": request_title or "-",
            "requester": str(requester) if requester else "-",
            "step_name": task.step_name,
            "due_at": task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "-",
            "due_status": task.due_status_label,
            "reason": f"Task has been overdue for {max(1, overdue_days)} day(s).",
        }

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        overdue_tasks = (
            ApprovalTask.objects.filter(
                status__in=[ApprovalTaskStatus.PENDING, ApprovalTaskStatus.POOL],
                completed_at__isnull=True,
                due_at__isnull=False,
                due_at__lt=now,
            )
            .select_related(
                "assigned_user",
                "purchase_request",
                "request_content_type",
                "step",
            )
            .prefetch_related("candidates__user")
            .order_by("due_at", "id")
        )

        recipient_map = defaultdict(dict)

        for task in overdue_tasks:
            if not task.can_send_escalation(now=now):
                continue

            overdue_days = (now - task.due_at).days if task.due_at else 0
            request_obj = task.get_request_object() if hasattr(task, "get_request_object") else None
            requester = getattr(request_obj, "requester", None) if request_obj else None

            payload = self._build_task_payload(task, overdue_days)

            if requester and requester.email:
                recipient_map[requester.email][task.id] = payload

            if task.status == ApprovalTaskStatus.PENDING:
                if task.assigned_user and task.assigned_user.email:
                    recipient_map[task.assigned_user.email][task.id] = payload

            elif task.status == ApprovalTaskStatus.POOL:
                for candidate in task.candidates.filter(is_active=True).select_related("user"):
                    if candidate.user and candidate.user.email:
                        recipient_map[candidate.user.email][task.id] = payload

        if not recipient_map:
            self.stdout.write(self.style.SUCCESS("No escalated overdue approval tasks found."))
            return

        sent_count = 0
        sent_task_ids = set()

        for email, item_map in recipient_map.items():
            items = list(item_map.values())

            lines = [
                "The following approval tasks are seriously overdue:",
                "",
            ]

            for item in items:
                lines.extend(
                    [
                        f"- {item['request_type']} | {item['request_no']} | {item['request_title']}",
                        f"  Requester: {item['requester']}",
                        f"  Step: {item['step_name']}",
                        f"  Due At: {item['due_at']}",
                        f"  Due Status: {item['due_status']}",
                        f"  Escalation Reason: {item['reason']}",
                        "",
                    ]
                )

            body = "\n".join(lines)

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would send escalation to {email}")
                self.stdout.write(body)
                self.stdout.write("-" * 60)

                for item in items:
                    self._log_notification(
                        task_id=item["task_id"],
                        notification_type=ApprovalNotificationType.ESCALATION,
                        recipient_email=email,
                        subject="Escalated overdue approval tasks",
                        body=body,
                        status=ApprovalNotificationStatus.DRY_RUN,
                        command_name="send_approval_escalations",
                    )
            else:
                try:
                    send_mail(
                        subject="Escalated overdue approval tasks",
                        message=body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[email],
                        fail_silently=False,
                    )
                    sent_count += 1
                    sent_task_ids.update(item_map.keys())

                    for item in items:
                        self._log_notification(
                            task_id=item["task_id"],
                            notification_type=ApprovalNotificationType.ESCALATION,
                            recipient_email=email,
                            subject="Escalated overdue approval tasks",
                            body=body,
                            status=ApprovalNotificationStatus.SUCCESS,
                            command_name="send_approval_escalations",
                        )
                except Exception as exc:
                    for item in items:
                        self._log_notification(
                            task_id=item["task_id"],
                            notification_type=ApprovalNotificationType.ESCALATION,
                            recipient_email=email,
                            subject="Escalated overdue approval tasks",
                            body=body,
                            status=ApprovalNotificationStatus.FAILED,
                            command_name="send_approval_escalations",
                            error_message=str(exc),
                        )
                    raise

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed."))
        else:
            for task in ApprovalTask.objects.filter(id__in=sent_task_ids):
                task.last_escalation_sent_at = now
                task.escalation_count = (task.escalation_count or 0) + 1
                task.save(update_fields=["last_escalation_sent_at", "escalation_count"])

            self.stdout.write(self.style.SUCCESS(f"Escalation emails sent: {sent_count}"))