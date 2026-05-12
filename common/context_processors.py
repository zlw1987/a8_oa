from .navigation import build_navigation_for_user
from projects.access import user_can_create_project
from .permissions import can_view_system_setup


def top_navigation(request):
    can_create_project = False
    if request.user.is_authenticated:
        can_create_project = user_can_create_project(request.user)
    return {
        "top_navigation": build_navigation_for_user(request.user, request),
        "can_create_project": can_create_project,
        "can_view_system_setup": can_view_system_setup(request.user),
    }
