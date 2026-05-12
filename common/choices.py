from django.db import models


class ApprovalLevel(models.TextChoices):
    STAFF = "STAFF", "Staff"
    MANAGER = "MANAGER", "Manager"
    DIRECTOR = "DIRECTOR", "Director"
    VP = "VP", "VP"
    C_LEVEL = "C_LEVEL", "C-Level"


class RequestType(models.TextChoices):
    PURCHASE = "PURCHASE", "Purchase Request"
    TRAVEL = "TRAVEL", "Travel Request"
    PROJECT = "PROJECT", "Project"


class RequestStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    PENDING = "PENDING", "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    CANCELLED = "CANCELLED", "Cancelled"
    CLOSED = "CLOSED", "Closed"


class BudgetEntryType(models.TextChoices):
    RESERVE = "RESERVE", "Reserve"
    CONSUME = "CONSUME", "Consume"
    RELEASE = "RELEASE", "Release"
    ADJUST = "ADJUST", "Adjust"


class ActualExpenseEntryType(models.TextChoices):
    ACTUAL_SPEND = "ACTUAL_SPEND", "Actual Spend"
    REFUND = "REFUND", "Refund"
    CREDIT_MEMO = "CREDIT_MEMO", "Credit Memo"
    REVERSAL = "REVERSAL", "Reversal"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class ApprovalTaskStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting"
    POOL = "POOL", "Pool"
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    SKIPPED = "SKIPPED", "Skipped"
    CANCELLED = "CANCELLED", "Cancelled"


class PurchaseRequestHistoryActionType(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    CANCELLED = "CANCELLED", "Cancelled"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    TASK_CLAIMED = "TASK_CLAIMED", "Task Claimed"
    TASK_RELEASED_TO_POOL = "TASK_RELEASED_TO_POOL", "Task Released to Pool"
    TASK_APPROVED = "TASK_APPROVED", "Task Approved"
    TASK_REJECTED = "TASK_REJECTED", "Task Rejected"
    TASK_RETURNED = "TASK_RETURNED", "Task Returned"

class ApproverType(models.TextChoices):
    REQUESTER_MANAGER = "REQUESTER_MANAGER", "Requester Manager"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER", "Department Manager"
    SPECIFIC_USER = "SPECIFIC_USER", "Specific User"
    DEPARTMENT_APPROVER = "DEPARTMENT_APPROVER", "Department Approver"
    FINANCE = "FINANCE", "Finance"
    PURCHASING = "PURCHASING", "Purchasing"
    HR = "HR", "HR"
    GLOBAL_APPROVER = "GLOBAL_APPROVER", "Global Approver"

class DepartmentType(models.TextChoices):
    GENERAL = "GENERAL", "General"
    IT = "IT", "IT"
    FIN = "FIN", "Finance"
    HR = "HR", "HR"
    PUR = "PUR", "Purchasing"
    OPS = "OPS", "Operations"
    EXEC = "EXEC", "Executive"

class UnitOfMeasure(models.TextChoices):
    EA = "EA", "Each"
    SET = "SET", "Set"
    BOX = "BOX", "Box"
    PACK = "PACK", "Pack"
    PAIR = "PAIR", "Pair"
    LOT = "LOT", "Lot"
    KG = "KG", "Kilogram"
    LB = "LB", "Pound"
    M = "M", "Meter"
    FT = "FT", "Foot"
    HOUR = "HOUR", "Hour"
    DAY = "DAY", "Day"
    MONTH = "MONTH", "Month"
    OTHER = "OTHER", "Other"

class CurrencyCode(models.TextChoices):
    USD = "USD", "USD"
    EUR = "EUR", "EUR"
    CNY = "CNY", "CNY"
    HKD = "HKD", "HKD"
    TWD = "TWD", "TWD"
    JPY = "JPY", "JPY"
