from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import DepartmentForm, UserDepartmentForm
from .models import Department, UserDepartment


def _user_can_manage_departments(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def _enforce_department_admin(user):
    if not _user_can_manage_departments(user):
        raise PermissionDenied("You do not have permission to manage departments.")


def _decorate_department(department):
    department.detail_url = reverse("accounts:department_detail", args=[department.id])
    department.edit_url = reverse("accounts:department_edit", args=[department.id])
    return department


@login_required
def department_list(request):
    _enforce_department_admin(request.user)

    departments = (
        Department.objects.select_related("manager", "parent_department")
        .annotate(
            active_user_count=Count(
                "user_links",
                filter=Q(user_links__is_active=True),
                distinct=True,
            ),
            child_department_count=Count(
                "child_departments",
                filter=Q(child_departments__is_active=True),
                distinct=True,
            ),
        )
        .order_by("sort_order", "dept_code")
    )

    q = (request.GET.get("q") or "").strip()
    dept_type = (request.GET.get("dept_type") or "").strip()
    status = (request.GET.get("status") or "").strip()

    if q:
        departments = departments.filter(
            Q(dept_code__icontains=q)
            | Q(dept_name__icontains=q)
            | Q(cost_center__icontains=q)
            | Q(manager__username__icontains=q)
            | Q(manager__display_name__icontains=q)
        )

    if dept_type:
        departments = departments.filter(dept_type=dept_type)

    if status == "active":
        departments = departments.filter(is_active=True)
    elif status == "inactive":
        departments = departments.filter(is_active=False)

    department_list_items = [_decorate_department(department) for department in departments]

    context = {
        "departments": department_list_items,
        "department_create_url": reverse("accounts:department_create"),
        "q": q,
        "selected_dept_type": dept_type,
        "selected_status": status,
        "dept_type_choices": Department._meta.get_field("dept_type").choices,
    }
    return render(request, "accounts/department_list.html", context)


@login_required
def department_detail(request, pk):
    _enforce_department_admin(request.user)

    department = get_object_or_404(
        Department.objects.select_related("manager", "parent_department"),
        pk=pk,
    )
    _decorate_department(department)

    user_links = (
        UserDepartment.objects.filter(department=department)
        .select_related("user")
        .order_by("-is_active", "-can_approve", "user__username")
    )
    child_departments = department.child_departments.select_related("manager").order_by(
        "sort_order",
        "dept_code",
    )

    context = {
        "department": department,
        "user_links": user_links,
        "child_departments": child_departments,
        "user_link_create_url": reverse("accounts:department_user_link_create", args=[department.id]),
    }
    return render(request, "accounts/department_detail.html", context)


@login_required
def department_create(request):
    _enforce_department_admin(request.user)

    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            messages.success(request, f"Department {department.dept_code} created successfully.")
            return redirect("accounts:department_detail", pk=department.id)
    else:
        form = DepartmentForm(initial={"is_active": True})

    context = {
        "form": form,
        "page_mode": "create",
        "form_title": "Create Department",
        "submit_label": "Create Department",
    }
    return render(request, "accounts/department_form.html", context)


@login_required
def department_user_link_create(request, pk):
    _enforce_department_admin(request.user)

    department = get_object_or_404(Department, pk=pk)

    if request.method == "POST":
        form = UserDepartmentForm(request.POST, department=department)
        if form.is_valid():
            link = form.save()
            messages.success(request, f"{link.user} linked to {department.dept_code}.")
            return redirect("accounts:department_detail", pk=department.id)
    else:
        form = UserDepartmentForm(department=department, initial={"is_active": True})

    context = {
        "department": department,
        "form": form,
        "form_title": "Add Department User",
        "submit_label": "Add User",
    }
    return render(request, "accounts/user_department_form.html", context)


@login_required
def department_user_link_edit(request, pk, link_id):
    _enforce_department_admin(request.user)

    department = get_object_or_404(Department, pk=pk)
    link = get_object_or_404(UserDepartment.objects.select_related("user"), pk=link_id, department=department)

    if request.method == "POST":
        form = UserDepartmentForm(request.POST, instance=link, department=department)
        if form.is_valid():
            link = form.save()
            messages.success(request, f"{link.user} department access updated.")
            return redirect("accounts:department_detail", pk=department.id)
    else:
        form = UserDepartmentForm(instance=link, department=department)

    context = {
        "department": department,
        "link": link,
        "form": form,
        "form_title": "Edit Department User",
        "submit_label": "Save User Link",
    }
    return render(request, "accounts/user_department_form.html", context)


@login_required
def department_edit(request, pk):
    _enforce_department_admin(request.user)

    department = get_object_or_404(Department, pk=pk)

    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department = form.save()
            messages.success(request, f"Department {department.dept_code} updated successfully.")
            return redirect("accounts:department_detail", pk=department.id)
    else:
        form = DepartmentForm(instance=department)

    context = {
        "department": department,
        "form": form,
        "page_mode": "edit",
        "form_title": "Edit Department",
        "submit_label": "Save Department",
    }
    return render(request, "accounts/department_form.html", context)
