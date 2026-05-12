from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("create/", views.project_create, name="project_create"),
    path("department-general/", views.department_general_project_list, name="department_general_project_list"),
    path("department-general/create/", views.department_general_project_create, name="department_general_project_create"),
    path("department-general/<int:pk>/edit/", views.department_general_project_edit, name="department_general_project_edit"),
    path("<int:pk>/", views.project_detail, name="project_detail"),
    path("<int:pk>/submit-budget/", views.project_submit_budget, name="project_submit_budget"),
    path("<int:pk>/budget/", views.project_budget_ledger, name="project_budget_ledger"),
    path("<int:pk>/budget/adjust/", views.project_add_budget_adjustment, name="project_add_budget_adjustment"),
    path("<int:pk>/budget/adjust/<int:adjustment_id>/approve/", views.project_approve_budget_adjustment, name="project_approve_budget_adjustment"),
    path("<int:pk>/budget/adjust/<int:adjustment_id>/reject/", views.project_reject_budget_adjustment, name="project_reject_budget_adjustment"),
    path("<int:pk>/members/", views.project_members, name="project_members"),
    path("<int:pk>/members/add/", views.project_add_member, name="project_add_member"),
    path("<int:pk>/members/<int:member_id>/remove/", views.project_remove_member, name="project_remove_member"),
]
