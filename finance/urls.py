from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("policies/over-budget/", views.over_budget_policy_list, name="over_budget_policy_list"),
    path("policies/over-budget/create/", views.over_budget_policy_create, name="over_budget_policy_create"),
    path("policies/over-budget/<int:pk>/edit/", views.over_budget_policy_edit, name="over_budget_policy_edit"),
    path("policies/receipt/", views.receipt_policy_list, name="receipt_policy_list"),
    path("policies/receipt/create/", views.receipt_policy_create, name="receipt_policy_create"),
    path("policies/receipt/<int:pk>/edit/", views.receipt_policy_edit, name="receipt_policy_edit"),
    path("accounting-periods/", views.accounting_period_list, name="accounting_period_list"),
    path("accounting-periods/create/", views.accounting_period_create, name="accounting_period_create"),
    path("accounting-periods/<int:pk>/", views.accounting_period_detail, name="accounting_period_detail"),
    path("accounting-periods/<int:pk>/close/", views.accounting_period_close, name="accounting_period_close"),
    path("accounting-periods/<int:pk>/reopen/", views.accounting_period_reopen, name="accounting_period_reopen"),
    path("reports/", views.finance_reports, name="finance_reports"),
    path("accounting-review/", views.accounting_review_queue, name="accounting_review_queue"),
    path("accounting-review/<int:pk>/", views.accounting_review_detail, name="accounting_review_detail"),
    path("accounting-review/<int:pk>/decide/", views.accounting_review_decide, name="accounting_review_decide"),
    path("card-transactions/", views.card_transaction_list, name="card_transaction_list"),
    path("card-transactions/create/", views.card_transaction_create, name="card_transaction_create"),
    path("card-transactions/<int:pk>/", views.card_transaction_detail, name="card_transaction_detail"),
    path("card-transactions/<int:pk>/allocate/", views.card_transaction_allocate, name="card_transaction_allocate"),
    path("card-transactions/<int:pk>/mark-reviewed/", views.card_transaction_mark_reviewed, name="card_transaction_mark_reviewed"),
]
