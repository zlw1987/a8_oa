from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("policies/over-budget/", views.over_budget_policy_list, name="over_budget_policy_list"),
    path("policies/over-budget/create/", views.over_budget_policy_create, name="over_budget_policy_create"),
    path("policies/over-budget/<int:pk>/edit/", views.over_budget_policy_edit, name="over_budget_policy_edit"),
    path("accounting-review/", views.accounting_review_queue, name="accounting_review_queue"),
    path("accounting-review/<int:pk>/decide/", views.accounting_review_decide, name="accounting_review_decide"),
    path("card-transactions/", views.card_transaction_list, name="card_transaction_list"),
    path("card-transactions/create/", views.card_transaction_create, name="card_transaction_create"),
    path("card-transactions/<int:pk>/", views.card_transaction_detail, name="card_transaction_detail"),
    path("card-transactions/<int:pk>/allocate/", views.card_transaction_allocate, name="card_transaction_allocate"),
]
