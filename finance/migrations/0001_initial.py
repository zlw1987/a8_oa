from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0005_delete_departmentapprovalconfig"),
        ("projects", "0005_project_budget_approval_and_type"),
        ("purchase", "0016_purchase_overage_and_supplemental"),
        ("travel", "0010_per_diem_overage_and_supplemental"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="OverBudgetPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_code", models.CharField(max_length=30, unique=True)),
                ("policy_name", models.CharField(max_length=120)),
                ("request_type", models.CharField(choices=[("ALL", "All"), ("PURCHASE", "Purchase Request"), ("TRAVEL", "Travel Request")], default="ALL", max_length=20)),
                ("project_type", models.CharField(blank=True, choices=[("INTERNAL", "Internal Project"), ("TRADE_SHOW", "Trade Show"), ("DEPARTMENT_GENERAL", "Department General Budget"), ("CUSTOMER_SERVICE", "Customer Service"), ("SALES_ORDER", "Sales Order")], default="", max_length=30)),
                ("payment_method", models.CharField(choices=[("ALL", "All"), ("REIMBURSEMENT", "Reimbursement"), ("COMPANY_CARD", "Company Card"), ("AP_INVOICE", "AP Invoice"), ("MANUAL", "Manual Accounting Entry")], default="ALL", max_length=30)),
                ("currency", models.CharField(blank=True, choices=[("USD", "USD"), ("EUR", "EUR"), ("CNY", "CNY"), ("HKD", "HKD"), ("TWD", "TWD"), ("JPY", "JPY")], default="", max_length=10)),
                ("over_amount_from", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("over_amount_to", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("over_percent_from", models.DecimalField(blank=True, decimal_places=4, max_digits=7, null=True)),
                ("over_percent_to", models.DecimalField(blank=True, decimal_places=4, max_digits=7, null=True)),
                ("action", models.CharField(choices=[("ALLOW", "Allow"), ("WARNING", "Warning"), ("REVIEW", "Review"), ("AMENDMENT_REQUIRED", "Amendment Required"), ("BLOCK", "Block")], default="REVIEW", max_length=30)),
                ("requires_comment", models.BooleanField(default=False)),
                ("requires_attachment", models.BooleanField(default=False)),
                ("requires_manager_review", models.BooleanField(default=False)),
                ("requires_finance_review", models.BooleanField(default=True)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="over_budget_policies", to="accounts.department")),
            ],
            options={
                "verbose_name": "Over-Budget Policy",
                "verbose_name_plural": "Over-Budget Policies",
                "db_table": "PS_A8_FIN_OB_POL",
                "ordering": ["priority", "policy_code"],
            },
        ),
        migrations.CreateModel(
            name="CardTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("statement_date", models.DateField()),
                ("transaction_date", models.DateField()),
                ("merchant_name", models.CharField(max_length=150)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(choices=[("USD", "USD"), ("EUR", "EUR"), ("CNY", "CNY"), ("HKD", "HKD"), ("TWD", "TWD"), ("JPY", "JPY")], default="USD", max_length=10)),
                ("reference_no", models.CharField(max_length=100)),
                ("match_status", models.CharField(choices=[("UNMATCHED", "Unmatched"), ("PARTIALLY_MATCHED", "Partially Matched"), ("MATCHED", "Matched"), ("REVIEWED", "Reviewed")], default="UNMATCHED", max_length=30)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("cardholder", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="card_transactions", to=settings.AUTH_USER_MODEL)),
                ("imported_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imported_card_transactions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Card Transaction",
                "verbose_name_plural": "Card Transactions",
                "db_table": "PS_A8_FIN_CARD_TXN",
                "ordering": ["-statement_date", "-transaction_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="CardTransactionAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("policy_action", models.CharField(blank=True, choices=[("ALLOW", "Allow"), ("WARNING", "Warning"), ("REVIEW", "Review"), ("AMENDMENT_REQUIRED", "Amendment Required"), ("BLOCK", "Block")], default="", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("card_transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="finance.cardtransaction")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_card_allocations", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="card_allocations", to="finance.overbudgetpolicy")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="card_allocations", to="projects.project")),
                ("purchase_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="card_allocations", to="purchase.purchaserequest")),
                ("travel_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="card_allocations", to="travel.travelrequest")),
            ],
            options={
                "verbose_name": "Card Transaction Allocation",
                "verbose_name_plural": "Card Transaction Allocations",
                "db_table": "PS_A8_FIN_CARD_ALLOC",
                "ordering": ["card_transaction", "id"],
            },
        ),
        migrations.CreateModel(
            name="AccountingReviewItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(choices=[("PURCHASE", "Purchase Request"), ("TRAVEL", "Travel Request"), ("CARD_TRANSACTION", "Card Transaction"), ("CARD_ALLOCATION", "Card Allocation")], max_length=30)),
                ("source_object_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("reason", models.CharField(choices=[("OVER_BUDGET", "Over Budget"), ("MISSING_RECEIPT", "Missing Receipt"), ("UNMATCHED_CARD", "Unmatched Card Transaction"), ("DUPLICATE_CARD", "Duplicate Card Transaction"), ("POLICY_EXCEPTION", "Policy Exception"), ("MANUAL_FLAG", "Manual Flag")], max_length=30)),
                ("status", models.CharField(choices=[("PENDING_REVIEW", "Pending Review"), ("APPROVED_EXCEPTION", "Approved Exception"), ("RETURNED", "Returned"), ("REJECTED", "Rejected"), ("RESOLVED", "Resolved")], default="PENDING_REVIEW", max_length=30)),
                ("policy_action", models.CharField(blank=True, choices=[("ALLOW", "Allow"), ("WARNING", "Warning"), ("REVIEW", "Review"), ("AMENDMENT_REQUIRED", "Amendment Required"), ("BLOCK", "Block")], default="", max_length=30)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("over_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("over_percent", models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=7)),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("decision", models.CharField(blank=True, choices=[("", "-"), ("APPROVE_EXCEPTION", "Approve Exception"), ("RETURN", "Return"), ("REJECT", "Reject"), ("RESOLVE", "Resolve")], default="", max_length=30)),
                ("comment", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_accounting_review_items", to=settings.AUTH_USER_MODEL)),
                ("card_allocation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="review_items", to="finance.cardtransactionallocation")),
                ("card_transaction", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="review_items", to="finance.cardtransaction")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_accounting_review_items", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="review_items", to="finance.overbudgetpolicy")),
                ("purchase_actual_spend", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accounting_review_items", to="purchase.purchaseactualspend")),
                ("purchase_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="accounting_review_items", to="purchase.purchaserequest")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_accounting_review_items", to=settings.AUTH_USER_MODEL)),
                ("source_content_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finance_review_items", to="contenttypes.contenttype")),
                ("travel_actual_expense", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accounting_review_items", to="travel.travelactualexpenseline")),
                ("travel_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="accounting_review_items", to="travel.travelrequest")),
            ],
            options={
                "verbose_name": "Accounting Review Item",
                "verbose_name_plural": "Accounting Review Items",
                "db_table": "PS_A8_FIN_REV",
                "ordering": ["status", "-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="cardtransaction",
            index=models.Index(fields=["statement_date", "amount", "merchant_name", "reference_no"], name="PS_A8_FIN_C_stateme_713533_idx"),
        ),
    ]
