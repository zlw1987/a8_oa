from decimal import Decimal


def build_project_budget_summary(project, request_total):
    if not project:
        return None

    request_total = request_total or Decimal("0.00")
    budget_amount = project.budget_amount or Decimal("0.00")
    adjustment_amount = project.get_adjustment_amount()
    effective_budget_amount = project.get_effective_budget_amount()
    reserved_amount = project.get_reserved_amount()
    consumed_amount = project.get_consumed_amount()
    available_amount = project.get_available_amount()
    remaining_after_request = available_amount - request_total

    return {
        "project_code": project.project_code,
        "project_name": project.project_name,
        "budget_amount": budget_amount,
        "adjustment_amount": adjustment_amount,
        "effective_budget_amount": effective_budget_amount,
        "reserved_amount": reserved_amount,
        "consumed_amount": consumed_amount,
        "available_amount": available_amount,
        "request_total": request_total,
        "remaining_after_request": remaining_after_request,
        "over_available": request_total > available_amount,
    }