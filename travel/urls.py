from django.urls import path

from . import views

app_name = "travel"

urlpatterns = [
    path("", views.tr_list, name="tr_list"),
    path("create/", views.tr_create, name="tr_create"),
    path("<int:pk>/edit/", views.tr_edit, name="tr_edit"),
    path("<int:pk>/submit/", views.tr_submit, name="tr_submit"),
    path("<int:pk>/cancel/", views.tr_cancel, name="tr_cancel"),
    path("<int:pk>/attachments/upload/", views.tr_upload_attachment, name="tr_upload_attachment"),
    path("<int:pk>/attachments/<int:attachment_id>/delete/", views.tr_delete_attachment, name="tr_delete_attachment"),
    path("<int:pk>/actual-expense/record/", views.tr_record_actual_expense, name="tr_record_actual_expense"),
    path("<int:pk>/", views.tr_detail, name="tr_detail"),
]