from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0013_approvalrule_is_general_fallback"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="approvaltask",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    request_content_type__isnull=False,
                    request_object_id__isnull=False,
                ),
                fields=("request_content_type", "request_object_id", "step_no"),
                name="uq_generic_request_step",
            ),
        ),
    ]
