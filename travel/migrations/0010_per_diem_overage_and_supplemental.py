from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_delete_departmentapprovalconfig"),
        ("travel", "0009_travelrequest_actual_review_comment_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TravelPerDiemPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_code", models.CharField(max_length=30, unique=True)),
                ("policy_name", models.CharField(max_length=100)),
                ("currency", models.CharField(choices=[("USD", "USD"), ("EUR", "EUR"), ("CNY", "CNY"), ("HKD", "HKD"), ("TWD", "TWD"), ("JPY", "JPY")], default="USD", max_length=10)),
                ("daily_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="travel_per_diem_policies", to="accounts.department")),
            ],
            options={
                "db_table": "PS_A8_TR_PER_DIEM",
                "ordering": ["department", "-effective_from", "policy_code"],
            },
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="per_diem_days",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="per_diem_daily_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="per_diem_allowed_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="per_diem_claim_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="pending_overage_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="pending_overage_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="parent_request",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplemental_requests", to="travel.travelrequest"),
        ),
        migrations.AddField(
            model_name="travelrequest",
            name="supplemental_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="travelestimatedexpenseline",
            name="is_per_diem",
            field=models.BooleanField(default=False),
        ),
    ]
