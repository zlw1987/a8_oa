from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0012_approvalnotificationlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalrule",
            name="is_general_fallback",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="approvalrule",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True, is_general_fallback=True),
                fields=("request_type",),
                name="uq_active_general_fallback_per_request_type",
            ),
        ),
    ]
