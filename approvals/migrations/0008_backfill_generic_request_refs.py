from django.db import migrations


def forwards(apps, schema_editor):
    ApprovalTask = apps.get_model("approvals", "ApprovalTask")
    ContentType = apps.get_model("contenttypes", "ContentType")

    purchase_request_ct, _ = ContentType.objects.get_or_create(
        app_label="purchase",
        model="purchaserequest",
    )

    tasks = ApprovalTask.objects.exclude(purchase_request_id__isnull=True)

    for task in tasks:
        if not task.request_content_type_id:
            task.request_content_type_id = purchase_request_ct.id

        if not task.request_object_id:
            task.request_object_id = task.purchase_request_id

        task.save(update_fields=["request_content_type", "request_object_id"])


def backwards(apps, schema_editor):
    ApprovalTask = apps.get_model("approvals", "ApprovalTask")

    tasks = ApprovalTask.objects.exclude(purchase_request_id__isnull=True)

    for task in tasks:
        task.request_content_type_id = None
        task.request_object_id = None
        task.save(update_fields=["request_content_type", "request_object_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("approvals", "0007_approvaltask_request_content_type_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]