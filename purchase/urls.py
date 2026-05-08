from django.urls import path

from . import views

app_name = "purchase"

urlpatterns = [
    path("", views.pr_list, name="pr_list"),
    path("create/", views.pr_create, name="pr_create"),
    path("<int:pk>/edit/", views.pr_edit, name="pr_edit"),
    path("<int:pk>/attachments/upload/", views.pr_upload_attachment, name="pr_upload_attachment"),
    path("<int:pk>/attachments/<int:attachment_id>/delete/", views.pr_delete_attachment, name="pr_delete_attachment"),
    path("<int:pk>/actual-spend/record/", views.pr_record_actual_spend, name="pr_record_actual_spend"),
    path("<int:pk>/supplemental/create/", views.pr_create_supplemental, name="pr_create_supplemental"),
    path("<int:pk>/submit/", views.pr_submit, name="pr_submit"),
    path("<int:pk>/cancel/", views.pr_cancel, name="pr_cancel"),
    path("<int:pk>/close/", views.pr_close, name="pr_close"),
    path("<int:pk>/tasks/<int:task_id>/claim/", views.task_claim, name="task_claim"),
    path("<int:pk>/tasks/<int:task_id>/release/", views.task_release, name="task_release"),
    path("<int:pk>/tasks/<int:task_id>/approve/", views.task_approve, name="task_approve"),
    path("<int:pk>/tasks/<int:task_id>/return/", views.task_return, name="task_return"),
    path("<int:pk>/tasks/<int:task_id>/reject/", views.task_reject, name="task_reject"),
    path("<int:pk>/", views.pr_detail, name="pr_detail"),
    path("<int:pk>/actual-review/", views.pr_review_actual, name="pr_review_actual"),
    path("<int:pk>/actual-review/upload/", views.pr_upload_actual_review_attachment, name="pr_upload_actual_review_attachment"),
]
