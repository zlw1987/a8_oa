from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0014_approvaltask_generic_request_step_constraint"),
        ("projects", "0004_alter_project_currency"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="project_type",
            field=models.CharField(
                choices=[
                    ("INTERNAL", "Internal Project"),
                    ("TRADE_SHOW", "Trade Show"),
                    ("DEPARTMENT_GENERAL", "Department General Budget"),
                    ("CUSTOMER_SERVICE", "Customer Service"),
                    ("SALES_ORDER", "Sales Order"),
                ],
                default="INTERNAL",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="budget_approval_status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING_APPROVAL", "Pending Approval"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("RETURNED", "Returned"),
                    ("NOT_REQUIRED", "Not Required"),
                ],
                default="APPROVED",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="matched_rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_requests",
                to="approvals.approvalrule",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="budget_period_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="budget_period_end",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="external_order_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "-"),
                    ("SALES_ORDER", "Sales Order"),
                    ("SERVICE_ORDER", "Service Order"),
                    ("CUSTOMER_VISIT", "Customer Visit"),
                ],
                default="",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="external_order_no",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="project",
            name="customer_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
