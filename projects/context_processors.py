from accounts.models import Department


def project_nav(request):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "nav_can_create_project": False,
        }

    can_create_project = user.is_superuser or Department.objects.filter(manager=user).exists()

    return {
        "nav_can_create_project": can_create_project,
    }