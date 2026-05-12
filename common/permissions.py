ROLE_REQUESTER = "Requester"
ROLE_APPROVER = "Approver"
ROLE_DEPARTMENT_MANAGER = "Department Manager"
ROLE_PROJECT_OWNER = "Project Owner"
ROLE_ACCOUNTING_CLERK = "Accounting Clerk"
ROLE_ACCOUNTING_MANAGER = "Accounting Manager"
ROLE_FINANCE_ADMIN = "Finance Admin"
ROLE_SYSTEM_ADMIN = "System Admin"
ROLE_AUDITOR = "Auditor"

ACCOUNTING_ROLES = {
    ROLE_ACCOUNTING_CLERK,
    ROLE_ACCOUNTING_MANAGER,
    ROLE_FINANCE_ADMIN,
}

FINANCE_SETUP_ROLES = {
    ROLE_FINANCE_ADMIN,
}

SYSTEM_SETUP_ROLES = {
    ROLE_FINANCE_ADMIN,
    ROLE_SYSTEM_ADMIN,
}


def user_has_role(user, role_name):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=role_name).exists()


def user_has_any_role(user, role_names):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=role_names).exists()


def can_perform_accounting_work(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user_has_any_role(user, ACCOUNTING_ROLES))
    )


def can_manage_finance_setup(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user_has_any_role(user, FINANCE_SETUP_ROLES))
    )


def can_view_system_setup(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.is_staff or user_has_any_role(user, SYSTEM_SETUP_ROLES))
    )


def can_use_django_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


ROLE_PERMISSION_MATRIX = [
    {
        "action": "Create PR/TR",
        "requester": "Yes",
        "approver": "Yes",
        "accounting_clerk": "Yes",
        "accounting_manager": "Yes",
        "finance_admin": "Yes",
        "system_admin": "Yes",
    },
    {
        "action": "Approve request",
        "requester": "No self-approval",
        "approver": "Assigned only",
        "accounting_clerk": "No",
        "accounting_manager": "Maybe",
        "finance_admin": "Maybe",
        "system_admin": "Maybe",
    },
    {
        "action": "Record actual expense",
        "requester": "No / Limited",
        "approver": "No",
        "accounting_clerk": "Yes",
        "accounting_manager": "Yes",
        "finance_admin": "Yes",
        "system_admin": "Maybe",
    },
    {
        "action": "Resolve review item",
        "requester": "No self-review",
        "approver": "No",
        "accounting_clerk": "Limited",
        "accounting_manager": "Yes",
        "finance_admin": "Yes",
        "system_admin": "Maybe",
    },
    {
        "action": "Configure finance policy",
        "requester": "No",
        "approver": "No",
        "accounting_clerk": "No",
        "accounting_manager": "No",
        "finance_admin": "Yes",
        "system_admin": "Maybe",
    },
    {
        "action": "Close accounting period",
        "requester": "No",
        "approver": "No",
        "accounting_clerk": "No",
        "accounting_manager": "Limited",
        "finance_admin": "Yes",
        "system_admin": "Maybe",
    },
]
