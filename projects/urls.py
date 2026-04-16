from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("<int:pk>/budget/", views.project_budget_ledger, name="project_budget_ledger"),
]