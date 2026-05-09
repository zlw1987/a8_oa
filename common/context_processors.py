from .navigation import build_navigation_for_user


def top_navigation(request):
    return {
        "top_navigation": build_navigation_for_user(request.user, request),
    }
