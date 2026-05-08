from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("create/", views.project_create, name="project_create"),
    path("<int:pk>/", views.project_detail, name="project_detail"),
    path("<int:pk>/submit-budget/", views.project_submit_budget, name="project_submit_budget"),
    path("<int:pk>/budget/", views.project_budget_ledger, name="project_budget_ledger"),
    path("<int:pk>/budget/adjust/", views.project_add_budget_adjustment, name="project_add_budget_adjustment"),
    path("<int:pk>/members/", views.project_members, name="project_members"),
    path("<int:pk>/members/add/", views.project_add_member, name="project_add_member"),
    path("<int:pk>/members/<int:member_id>/remove/", views.project_remove_member, name="project_remove_member"),
]
