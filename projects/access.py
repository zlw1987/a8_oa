from django.db.models import Q

from .models import Project


def get_visible_projects_queryset_for_user(user):
    qs = Project.objects.select_related("project_manager", "owning_department", "created_by")

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    return qs.filter(
        Q(created_by=user)
        | Q(project_manager=user)
        | Q(owning_department__manager=user)
        | Q(members__user=user, members__is_active=True)
    ).distinct()


def get_usable_projects_queryset_for_user(user):
    return get_visible_projects_queryset_for_user(user).filter(status="OPEN", is_active=True)


def user_can_manage_project_members(user, project):
    return project.can_user_manage_members(user)


def user_can_use_project_for_request(user, project):
    return project.can_user_use_for_request(user)