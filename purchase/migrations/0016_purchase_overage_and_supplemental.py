from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0015_purchaserequest_actual_review_comment_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="pending_overage_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="pending_overage_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="parent_request",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplemental_requests",
                to="purchase.purchaserequest",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="supplemental_reason",
            field=models.TextField(blank=True, default=""),
        ),
    ]
