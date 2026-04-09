from django.db import migrations


def forwards(apps, schema_editor):
    ApprovalTask = apps.get_model("approvals", "ApprovalTask")
    ContentType = apps.get_model("contenttypes", "ContentType")

    purchase_request_ct = ContentType.objects.get(
        app_label="purchase",
        model="purchaserequest",
    )

    for task in ApprovalTask.objects.filter(
        purchase_request_id__isnull=False,
        request_content_type__isnull=True,
    ):
        task.request_content_type_id = purchase_request_ct.id
        task.request_object_id = task.purchase_request_id
        task.save(update_fields=["request_content_type", "request_object_id"])


def backwards(apps, schema_editor):
    ApprovalTask = apps.get_model("approvals", "ApprovalTask")

    ApprovalTask.objects.update(
        request_content_type_id=None,
        request_object_id=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("approvals", "0007_approvaltask_request_content_type_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]