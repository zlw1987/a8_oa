from approvals.models import ApprovalTask, ApprovalTaskStatus


def get_approval_summary_for_user(user):
    assigned_tasks = list(
        ApprovalTask.objects.filter(
            assigned_user=user,
            status=ApprovalTaskStatus.PENDING,
        ).select_related("request_content_type")
    )

    pool_tasks = list(
        ApprovalTask.objects.filter(
            status=ApprovalTaskStatus.POOL,
            candidates__user=user,
            candidates__is_active=True,
        )
        .select_related("request_content_type")
        .prefetch_related("candidates")
        .distinct()
    )

    assigned_overdue = sum(1 for task in assigned_tasks if task.is_overdue)
    pool_overdue = sum(1 for task in pool_tasks if task.is_overdue)

    return {
        "assigned_count": len(assigned_tasks),
        "assigned_overdue_count": assigned_overdue,
        "pool_count": len(pool_tasks),
        "pool_overdue_count": pool_overdue,
        "total_overdue_count": assigned_overdue + pool_overdue,
    }