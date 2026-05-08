from django.db.models import Q
from django.contrib.contenttypes.models import ContentType

from accounts.models import Department
from .models import Project


def get_visible_projects_queryset_for_user(user):
    qs = Project.objects.select_related("project_manager", "owning_department", "created_by")

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    content_type = ContentType.objects.get_for_model(Project)

    return qs.filter(
        Q(created_by=user)
        | Q(project_manager=user)
        | Q(owning_department__manager=user)
        | Q(members__user=user, members__is_active=True)
        | Q(approval_tasks__request_content_type=content_type, approval_tasks__assigned_user=user)
        | Q(
            approval_tasks__request_content_type=content_type,
            approval_tasks__candidates__user=user,
            approval_tasks__candidates__is_active=True,
        )
        | Q(approval_tasks__request_content_type=content_type, approval_tasks__acted_by=user)
    ).distinct()


def get_usable_projects_queryset_for_user(user):
    return get_visible_projects_queryset_for_user(user).filter(status="OPEN", is_active=True)


def get_manageable_departments_queryset_for_user(user):
    if not user or not user.is_authenticated:
        return Department.objects.none()

    if user.is_superuser:
        return Department.objects.all()

    return Department.objects.filter(manager=user)


def user_can_create_project(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return get_manageable_departments_queryset_for_user(user).exists()


def user_can_manage_project_members(user, project):
    return project.can_user_manage_members(user)


def user_can_manage_project_budget(user, project):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if project.project_manager_id == user.id:
        return True

    if getattr(project.owning_department, "manager_id", None) == user.id:
        return True

    return False


def user_can_use_project_for_request(user, project):
    return project.can_user_use_for_request(user)
