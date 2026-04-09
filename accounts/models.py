from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from common.choices import ApprovalLevel, DepartmentType


class User(AbstractUser):
    employee_id = models.CharField(max_length=30, blank=True, default="")
    display_name = models.CharField(max_length=150, blank=True, default="")
    job_title = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    approval_level = models.CharField(
        max_length=20,
        choices=ApprovalLevel,
        default=ApprovalLevel.STAFF,
    )
    primary_department = models.ForeignKey(
        "Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_users",
    )
    can_approve_all_departments = models.BooleanField(default=False)

    class Meta:
        db_table = "PS_A8_USER"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.display_name or self.username


class Department(models.Model):

    dept_code = models.CharField(max_length=30, unique=True)
    dept_name = models.CharField(max_length=100)
    dept_type = models.CharField(
    max_length=20,
    choices=DepartmentType,
    default=DepartmentType.GENERAL,
    )
    cost_center = models.CharField(max_length=30, blank=True, default="")
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_departments",
    )
    parent_department = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_departments",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "PS_A8_DEPT"
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["sort_order", "dept_code"]

    def __str__(self):
        return f"{self.dept_code} - {self.dept_name}"


class UserDepartment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="department_links",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="user_links",
    )
    dept_job_title = models.CharField(max_length=100, blank=True, default="")
    can_approve = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "PS_A8_USR_DEPT"
        verbose_name = "User Department"
        verbose_name_plural = "User Departments"
        ordering = ["user", "department"]
        unique_together = ("user", "department")

    def __str__(self):
        return f"{self.user} / {self.department}"