from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("my-tasks/", views.my_tasks, name="my_tasks"),

    path("tasks/<int:task_id>/claim/", views.task_claim, name="task_claim"),
    path("tasks/<int:task_id>/release/", views.task_release, name="task_release"),
    path("tasks/<int:task_id>/approve/", views.task_approve, name="task_approve"),
    path("tasks/<int:task_id>/return/", views.task_return, name="task_return"),
    path("tasks/<int:task_id>/reject/", views.task_reject, name="task_reject"),
    path("my-history/", views.my_history, name="my_history"),
    path("accounting-review/", views.accounting_review_queue, name="accounting_review_queue"),
    path("variance-report/", views.variance_exception_report, name="variance_exception_report"),
    path("rules/", views.rule_list, name="rule_list"),
    path("rules/create/", views.rule_create, name="rule_create"),
    path("rules/<int:pk>/edit/", views.rule_edit, name="rule_edit"),
]