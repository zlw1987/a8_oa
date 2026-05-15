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
    path("policies/direct-project-cost/", views.direct_project_cost_policy_list, name="direct_project_cost_policy_list"),
    path("policies/direct-project-cost/create/", views.direct_project_cost_policy_create, name="direct_project_cost_policy_create"),
    path("policies/direct-project-cost/<int:pk>/edit/", views.direct_project_cost_policy_edit, name="direct_project_cost_policy_edit"),
    path("policies/fx-variance/", views.fx_variance_policy_list, name="fx_variance_policy_list"),
    path("policies/fx-variance/create/", views.fx_variance_policy_create, name="fx_variance_policy_create"),
    path("policies/fx-variance/<int:pk>/edit/", views.fx_variance_policy_edit, name="fx_variance_policy_edit"),
    path("currencies/", views.currency_list, name="currency_list"),
    path("currencies/create/", views.currency_create, name="currency_create"),
    path("currencies/<int:pk>/edit/", views.currency_edit, name="currency_edit"),
    path("exchange-rates/", views.exchange_rate_list, name="exchange_rate_list"),
    path("exchange-rates/create/", views.exchange_rate_create, name="exchange_rate_create"),
    path("exchange-rates/<int:pk>/edit/", views.exchange_rate_edit, name="exchange_rate_edit"),
    path("accounting-periods/", views.accounting_period_list, name="accounting_period_list"),
    path("accounting-periods/create/", views.accounting_period_create, name="accounting_period_create"),
    path("accounting-periods/<int:pk>/", views.accounting_period_detail, name="accounting_period_detail"),
    path("accounting-periods/<int:pk>/close/", views.accounting_period_close, name="accounting_period_close"),
    path("accounting-periods/<int:pk>/reopen/", views.accounting_period_reopen, name="accounting_period_reopen"),
    path("reports/", views.finance_reports, name="finance_reports"),
    path("reports/departments/<int:department_id>/", views.department_spending_drilldown, name="department_spending_drilldown"),
    path("accounting-review/", views.accounting_review_queue, name="accounting_review_queue"),
    path("accounting-review/<int:pk>/", views.accounting_review_detail, name="accounting_review_detail"),
    path("accounting-review/<int:pk>/decide/", views.accounting_review_decide, name="accounting_review_decide"),
    path("card-transactions/", views.card_transaction_list, name="card_transaction_list"),
    path("card-transactions/create/", views.card_transaction_create, name="card_transaction_create"),
    path("card-transactions/<int:pk>/", views.card_transaction_detail, name="card_transaction_detail"),
    path("card-transactions/<int:pk>/allocate/", views.card_transaction_allocate, name="card_transaction_allocate"),
    path("card-transactions/<int:pk>/mark-reviewed/", views.card_transaction_mark_reviewed, name="card_transaction_mark_reviewed"),
]
