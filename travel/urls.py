from django.urls import path

from . import views

app_name = "travel"

urlpatterns = [
    path("", views.tr_list, name="tr_list"),
    path("create/", views.tr_create, name="tr_create"),
    path("<int:pk>/edit/", views.tr_edit, name="tr_edit"),
    path("<int:pk>/submit/", views.tr_submit, name="tr_submit"),
    path("<int:pk>/cancel/", views.tr_cancel, name="tr_cancel"),
    path("<int:pk>/close/", views.tr_close, name="tr_close"),
    path("<int:pk>/attachments/upload/", views.tr_upload_attachment, name="tr_upload_attachment"),
    path("<int:pk>/attachments/<int:attachment_id>/delete/", views.tr_delete_attachment, name="tr_delete_attachment"),
    path("<int:pk>/actual-expense/record/", views.tr_record_actual_expense, name="tr_record_actual_expense"),
    path("<int:pk>/", views.tr_detail, name="tr_detail"),
    path("<int:pk>/tasks/<int:task_id>/claim/", views.task_claim, name="task_claim"),
    path("<int:pk>/tasks/<int:task_id>/release/", views.task_release, name="task_release"),
    path("<int:pk>/tasks/<int:task_id>/approve/", views.task_approve, name="task_approve"),
    path("<int:pk>/tasks/<int:task_id>/return/", views.task_return, name="task_return"),
    path("<int:pk>/tasks/<int:task_id>/reject/", views.task_reject, name="task_reject"),
    path("<int:pk>/actual-review/", views.tr_review_actual, name="tr_review_actual"),
    path("<int:pk>/actual-review/upload/", views.tr_upload_actual_review_attachment, name="tr_upload_actual_review_attachment"),
    ]