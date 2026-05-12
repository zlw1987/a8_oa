from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("system-setup/", views.system_setup, name="system_setup"),
]
