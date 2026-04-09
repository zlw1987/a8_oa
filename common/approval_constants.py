from common.choices import ApproverType


POOL_APPROVER_TYPES = frozenset(
    {
        ApproverType.DEPARTMENT_APPROVER,
        ApproverType.FINANCE,
        ApproverType.PURCHASING,
        ApproverType.HR,
        ApproverType.GLOBAL_APPROVER,
    }
)