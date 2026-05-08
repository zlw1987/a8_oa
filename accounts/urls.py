from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("departments/", views.department_list, name="department_list"),
    path("departments/create/", views.department_create, name="department_create"),
    path("departments/<int:pk>/", views.department_detail, name="department_detail"),
    path("departments/<int:pk>/edit/", views.department_edit, name="department_edit"),
]
