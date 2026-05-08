from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from common.choices import DepartmentType
from .models import Department


User = get_user_model()


class DepartmentManagementPageTest(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="department_admin",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_department_user",
            password="testpass123",
        )
        self.manager = User.objects.create_user(
            username="dept_manager",
            password="testpass123",
            display_name="Dept Manager",
        )
        self.department = Department.objects.create(
            dept_code="OPS",
            dept_name="Operations",
            dept_type=DepartmentType.OPS,
            manager=self.manager,
            is_active=True,
        )

    def test_staff_user_can_open_department_list(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("accounts:department_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations")
        self.assertContains(response, "New Department")

    def test_regular_user_cannot_open_department_list(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("accounts:department_list"))

        self.assertEqual(response.status_code, 403)

    def test_department_create_normalizes_code(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("accounts:department_create"),
            {
                "dept_code": " fin ",
                "dept_name": "Finance",
                "dept_type": DepartmentType.FIN,
                "cost_center": "CC-FIN",
                "manager": self.manager.id,
                "parent_department": "",
                "is_active": "on",
                "sort_order": "20",
            },
        )

        department = Department.objects.get(dept_code="FIN")
        self.assertRedirects(
            response,
            reverse("accounts:department_detail", args=[department.id]),
        )
        self.assertEqual(department.dept_name, "Finance")

    def test_department_edit_rejects_child_as_parent(self):
        child = Department.objects.create(
            dept_code="OPS-CHILD",
            dept_name="Operations Child",
            dept_type=DepartmentType.OPS,
            parent_department=self.department,
            is_active=True,
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("accounts:department_edit", args=[self.department.id]),
            {
                "dept_code": self.department.dept_code,
                "dept_name": self.department.dept_name,
                "dept_type": self.department.dept_type,
                "cost_center": self.department.cost_center,
                "manager": self.manager.id,
                "parent_department": child.id,
                "is_active": "on",
                "sort_order": str(self.department.sort_order),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "child departments as parent")
