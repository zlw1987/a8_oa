from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from projects.access import user_can_create_project
from .permissions import (
    can_manage_finance_setup,
    can_perform_accounting_work,
    can_use_django_admin,
    can_view_system_setup,
)


def _can_work(user):
    return user.is_authenticated


def _can_accounting(user):
    return can_perform_accounting_work(user)


def _can_setup(user):
    return can_manage_finance_setup(user)


def _can_admin(user):
    return can_use_django_admin(user)


def _can_system_setup(user):
    return can_view_system_setup(user)


def _can_create_project(user):
    return user.is_authenticated and user_can_create_project(user)


def _item(label, route_name, *, permission=None, active_names=None):
    active_names = active_names or [route_name]
    return {
        "label": label,
        "url": reverse(route_name),
        "permission": permission or _can_work,
        "active_names": active_names,
        "active": False,
    }


def _group(label, items):
    return {
        "label": label,
        "items": items,
        "active": False,
    }


def _mark_active(items, current_route_name):
    for item in items:
        item["active"] = current_route_name in item["active_names"]
    return items


def build_navigation_for_user(user, request=None):
    if not user.is_authenticated:
        return {"dashboard": None, "groups": []}

    resolver_match = getattr(request, "resolver_match", None)
    current_route_name = (
        f"{resolver_match.namespace}:{resolver_match.url_name}"
        if resolver_match and resolver_match.namespace
        else getattr(resolver_match, "url_name", "")
    )

    dashboard = _item(_("Dashboard"), "dashboard:home", active_names=["dashboard:home"])

    groups = [
        _group(
            _("Work"),
            [
                _item(_("Purchase Requests"), "purchase:pr_list", active_names=["purchase:pr_list", "purchase:pr_detail", "purchase:pr_create", "purchase:pr_edit"]),
                _item(_("Travel Requests"), "travel:tr_list", active_names=["travel:tr_list", "travel:tr_detail", "travel:tr_create", "travel:tr_edit"]),
                _item(_("My Tasks"), "approvals:my_tasks"),
                _item(_("My Approval History"), "approvals:my_history"),
                _item(_("My Delegations"), "approvals:my_delegations", active_names=["approvals:my_delegations", "approvals:delegation_create", "approvals:delegation_edit"]),
            ],
        ),
        _group(
            _("Finance"),
            [
                _item(_("Accounting Review Queue"), "finance:accounting_review_queue", permission=_can_accounting, active_names=["finance:accounting_review_queue", "finance:accounting_review_detail"]),
                _item(_("Card Transactions"), "finance:card_transaction_list", permission=_can_accounting, active_names=["finance:card_transaction_list", "finance:card_transaction_detail", "finance:card_transaction_create"]),
                _item(_("Accounting Periods"), "finance:accounting_period_list", permission=_can_accounting, active_names=["finance:accounting_period_list", "finance:accounting_period_detail", "finance:accounting_period_create"]),
                _item(_("Finance Reports"), "finance:finance_reports", permission=_can_accounting),
                _item(_("Variance Report"), "approvals:variance_exception_report", permission=_can_accounting),
            ],
        ),
        _group(
            _("Setup"),
            [
                _item(_("Projects"), "projects:project_list", permission=_can_work, active_names=["projects:project_list", "projects:project_detail", "projects:project_budget_ledger", "projects:project_members"]),
                _item(_("Create Project"), "projects:project_create", permission=_can_create_project, active_names=["projects:project_create"]),
                _item(_("Department General Budgets"), "projects:department_general_project_list", permission=_can_setup, active_names=["projects:department_general_project_list", "projects:department_general_project_create", "projects:department_general_project_edit"]),
                _item(_("Departments"), "accounts:department_list", permission=_can_setup),
                _item(_("Approval Rules"), "approvals:rule_list", permission=_can_setup),
                _item(_("Over-Budget Policies"), "finance:over_budget_policy_list", permission=_can_setup),
                _item(_("Receipt Policies"), "finance:receipt_policy_list", permission=_can_setup),
                _item(_("Direct Project Cost Policies"), "finance:direct_project_cost_policy_list", permission=_can_setup),
                _item(_("FX Variance Policies"), "finance:fx_variance_policy_list", permission=_can_setup),
                _item(_("Currencies"), "finance:currency_list", permission=_can_setup),
                _item(_("Exchange Rates"), "finance:exchange_rate_list", permission=_can_setup),
            ],
        ),
        _group(
            _("Admin"),
            [
                _item(_("Django Admin"), "admin:index", permission=_can_admin),
                _item(_("User / Department Setup"), "accounts:department_list", permission=_can_setup),
                _item(_("System Setup"), "dashboard:system_setup", permission=_can_system_setup, active_names=["dashboard:system_setup"]),
            ],
        ),
    ]

    filtered_groups = []
    for group in groups:
        visible_items = [
            item
            for item in group["items"]
            if item["permission"](user)
        ]
        _mark_active(visible_items, current_route_name)
        if visible_items:
            group["items"] = visible_items
            group["active"] = any(item["active"] for item in visible_items)
            filtered_groups.append(group)

    dashboard["active"] = current_route_name in dashboard["active_names"]
    return {
        "dashboard": dashboard if dashboard["permission"](user) else None,
        "groups": filtered_groups,
    }
