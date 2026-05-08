# Pilot Hardening Business-Control Gap Review

## Purpose

V0.5 completed the main business-control milestone:

- PR/TR supplemental requests.
- Receipt policy.
- Missing receipt review.
- Company card controls.
- Duplicate card review.
- Accounting workbench filters.
- Finance reports.
- Production readiness checklist.
- Finance default seed command.

Passing UAT means the core workflows are usable for pilot. It does not mean the system is fully safe for broad production rollout.

This document captures business-control gaps that should be reviewed before or during a limited pilot. The intent is to protect budget accuracy, audit trail integrity, accounting trust, and user adoption.

## Recommended Decision Labels

Each item should be reviewed with business, accounting, and finance, then assigned one label:

| Label | Meaning |
| --- | --- |
| Go-Live Blocker | Must be resolved before broad rollout |
| Pilot Required | Must be monitored during limited pilot |
| V0.6 | Strong candidate for next development milestone |
| Post-Go-Live | Useful enhancement after core controls are stable |
| Not Needed | Business confirms this is not required |

## 1. Period Close / Financial Locking

### Current Risk

The system can close requests, but accounting period close rules are not yet defined.

Questions:

- After month-end close, can users edit actual expenses?
- Can users upload or delete receipts?
- Can users change company card allocations?
- Can users resolve accounting review items?
- Can users reopen a closed request?
- Can users change project budget entries?

Without period locks, historical financial numbers can keep changing, which makes reports unreliable.

### Business Rule Needed

After a period is closed:

- Financial records in that period should not be modified directly.
- Corrections should use adjustment entries, not overwrite original data.
- Only finance/admin users should perform post-close adjustments.
- All post-close changes must require reason and audit history.

### Recommended Development

Add `AccountingPeriod`.

Possible fields:

- `period_code`
- `start_date`
- `end_date`
- `status`: `OPEN`, `CLOSING`, `CLOSED`
- `closed_by`
- `closed_at`
- `notes`

Required controls:

- Block actual expense edits in closed periods.
- Block card allocation changes in closed periods.
- Block budget ledger modifications in closed periods.
- Allow adjustment entries only with finance/admin permission.
- Show a clear message when a user tries to modify closed-period data.

### Priority

High. This is a go-live control gap.

## 2. Refund / Credit / Return Handling

### Current Risk

Current core flow is:

Request -> Approval -> Actual Expense -> Budget Consume -> Close

Real business also has:

- Refund.
- Vendor credit.
- Product return.
- Hotel refund.
- Flight cancellation refund.
- Negative company card transaction.
- Reimbursement correction.

If credits are not handled correctly, project budget and actual spend reports become wrong.

### Business Rule Needed

Refunds and credits should not delete original actual expenses. They should create reversing or credit entries.

Example:

- Original actual expense: 1000.
- Refund received: -300.
- Net actual spend: 700.
- Original transaction remains visible.
- Refund transaction is separately recorded.

### Recommended Development

Add actual expense entry types:

- `ACTUAL_SPEND`
- `REFUND`
- `CREDIT_MEMO`
- `REVERSAL`
- `ADJUSTMENT`

Required controls:

- Refund reduces consumed budget.
- Refund does not erase original spend.
- Refund links to original request or card transaction.
- Refund after request close either reopens the request or creates post-close adjustment.
- Refund after period close requires finance/admin adjustment.

### Priority

High. This is a likely real-world scenario.

## 3. Reopen / Correction Workflow

### Current Risk

After a request is closed, accounting may find:

- Wrong amount.
- Wrong project.
- Wrong vendor.
- Wrong card allocation.
- Duplicate actual expense.
- Missing refund.
- Wrong attachment.
- Wrong expense category.

Without controlled reopen, users may request manual data fixes, and accounting trust will erode.

### Business Rule Needed

Closed requests should not be freely editable.

Recommended rule:

- Only authorized finance/admin users can reopen.
- Reopen requires reason.
- Reopen writes audit history.
- If accounting period is closed, use adjustment instead of direct edit.

### Recommended Development

Add controlled reopen/correction workflow.

Possible fields:

- `reopened_by`
- `reopened_at`
- `reopen_reason`
- `reclosed_by`
- `reclosed_at`
- `correction_reference`

Required controls:

- Only finance/admin can reopen.
- Requester cannot reopen their own closed request.
- Reopen does not delete existing budget ledger entries.
- Financial corrections create new ledger entries.
- Re-close reruns closeout validation.

### Priority

High. Needed for real accounting operations.

## 4. Line-Level Receipt Matching

### Current Risk

V0.5 checks request-level non-accounting attachments. It does not link receipts to individual actual expense lines.

Example:

- Expense 1: 100, receipt uploaded.
- Expense 2: 800, no invoice.
- Expense 3: 50, receipt uploaded.

Request-level checking may incorrectly treat all expenses as supported.

### Business Rule Needed

Receipt/invoice should be linked to the actual expense or card allocation it supports.

### Recommended Development

Add `ActualExpenseAttachment`.

Possible fields:

- `actual_expense`
- `attachment`
- `attachment_type`: `RECEIPT`, `INVOICE`, `QUOTE`, `OTHER`
- `uploaded_by`
- `uploaded_at`

For card transactions, add `CardAllocationAttachment`.

Required controls:

- Receipt policy checks attachments linked to the actual expense.
- Invoice policy checks invoice-type attachment.
- Request-level attachments remain available for quote/general support.
- Missing receipt review resolves automatically or semi-automatically after the correct attachment is linked.

### Priority

Medium-High. Acceptable for pilot, likely needed before broad rollout if accounting requires strict receipt control.

## 5. Material Change Policy Beyond Amount Increase

### Current Risk

V0.5 supports supplemental increase requests. It does not provide full redline review for non-amount material changes.

Example:

- Original approval: 3000 for trade show booth material.
- Later actual use: 3000 for customer dinner.

Amount is unchanged, but business purpose changed.

### Business Rule Needed

Some changes should require re-approval even when amount does not increase.

Material fields may include:

- Vendor.
- Project.
- Department.
- Expense category.
- Business purpose.
- Travel destination.
- Travel dates.
- Payment method.
- Cost object.

### Recommended Development

Add Material Change Policy.

Actions:

- `WARNING`
- `REVIEW`
- `REAPPROVAL`
- `BLOCK`

Required controls:

- Track before/after values.
- If material change happens before approval, allow normal edit.
- If material change happens after approval, require amendment/reapproval.
- Store change history.
- Block closeout if material-change review is unresolved.

### Priority

Medium.

## 6. Approval Delegation / Escalation

### Current Risk

Approvers may be unavailable due to vacation, travel, transfer, sickness, resignation, or ignored tasks.

### Business Rule Needed

The system needs controlled backup approval.

Recommended rules:

- Approver can delegate for a date range.
- Admin can reassign stuck tasks.
- Tasks overdue after configured days can escalate.
- Delegation cannot allow requester self-approval.
- Delegation is auditable.

### Recommended Development

Add `ApprovalDelegation`.

Possible fields:

- `original_approver`
- `delegate_user`
- `start_date`
- `end_date`
- `department`
- `request_type`
- `is_active`
- `created_by`

Add `ApprovalEscalationPolicy`.

Possible fields:

- `request_type`
- `step_type`
- `overdue_days`
- `escalate_to_role`
- `escalate_to_user`

Required controls:

- Prevent delegation to requester.
- Show delegated approval in approval history.
- Allow admin reassignment with reason.
- Add overdue task report.

### Priority

Medium-High.

## 7. Emergency / After-The-Fact Purchase

### Current Risk

Ideal process is:

Request -> Approval -> Spend

Real business may have urgent cases:

- Customer emergency.
- Repair emergency.
- Trade show onsite purchase.
- Executive instruction.
- Deadline-driven purchase.
- Travel disruption.

If the system does not support after-the-fact requests, users may bypass it.

### Business Rule Needed

Allow emergency / after-the-fact request, but make it controlled.

Suggested rule:

- Emergency purchase must be flagged.
- Requester must explain why pre-approval was not obtained.
- Emergency request requires stronger review.
- Emergency requests appear in exception report.
- Repeated emergency requests are visible to management.

### Recommended Development

Add fields:

- `is_emergency`
- `is_after_the_fact`
- `emergency_reason`
- `purchase_already_made_date`

Add policy:

- After-the-fact requests require finance review.
- After-the-fact requests may require department head approval even under normal threshold.

### Priority

Medium-High.

## 8. Direct Project Cost Controls

### Current Risk

Company card allocation can post directly to Project direct cost. This is useful, but it may bypass PR/TR approval.

### Business Rule Needed

Define when direct project cost is allowed.

Questions:

- Who can post direct project cost?
- Is there a dollar limit?
- Does project owner need to approve?
- Does finance need to review?
- Does it require receipt?
- Does it appear in exception reports?

### Recommended Development

Add Direct Project Cost Policy.

Actions:

- `ALLOW`
- `REVIEW`
- `REQUIRE_PROJECT_OWNER_APPROVAL`
- `BLOCK`

Required controls:

- Only accounting/finance can post direct project cost.
- Direct cost above threshold requires review.
- Direct cost is visible in finance reports.
- Project owner can review direct cost if required.

### Priority

High if Project Direct Cost is used in production. Medium if not used yet.

## 9. Department General Budget Handling

### Current Risk

The current system uses Project as the main budget container. Department recurring general spending needs a clean structure.

### Business Rule Needed

Choose one option:

| Option | Description |
| --- | --- |
| A | Create annual department general projects, such as `MIS-GENERAL-2026` |
| B | Add separate Department Budget container |

Recommendation: use Option A for now. It is simpler and fits the current project budget model.

### Required Controls

- Each department should have one active general spending project per fiscal year.
- General PR/TR must link to that project.
- Finance can report department general spending through project reports.
- Prevent users from selecting the wrong department general project.

### Priority

High before broad rollout.

## 10. Multi-Currency / Exchange Rate Rules

### Current Risk

Currency fields exist, but exchange rate rules are not yet defined.

Questions:

- What is project budget currency?
- What is request currency?
- What is actual expense currency?
- What is company card statement currency?
- Which exchange rate date is used?
- Can accounting override exchange rate?

### Business Rule Needed

Recommended:

- Project budget has base currency.
- Actual expense can be entered in transaction currency.
- System stores transaction amount and base currency amount.
- Exchange rate date defaults to transaction date.
- Accounting can override rate with reason.

### Recommended Development

Add `ExchangeRate`.

Possible fields:

- `from_currency`
- `to_currency`
- `rate`
- `effective_date`
- `source`

Actual expense should store:

- `transaction_currency`
- `transaction_amount`
- `base_currency`
- `exchange_rate`
- `base_amount`

### Priority

Medium. Move to High if international travel/card transactions are common.

## 11. Tax / Shipping / Tip / Fee Treatment

### Current Risk

Approved amount versus actual amount may differ because of tax, shipping, service fee, hotel fee, tip, or foreign transaction fee.

If every difference is treated as over-budget, accounting may get too many false review items.

### Business Rule Needed

Define whether approved amount includes tax, shipping, tip, and fees.

Possible approach:

- Request estimated amount should include expected tax, shipping, and fees.
- Actual expense can break out tax/shipping/tip/fee.
- Over-budget policy compares total actual against approved total.
- Small tax/shipping variance can fall under warning threshold.

### Recommended Development

Add optional actual expense fields:

- `item_amount`
- `tax_amount`
- `shipping_amount`
- `tip_amount`
- `fee_amount`
- `total_amount`

### Priority

Medium.

## 12. Sales Order / Service Order Costing

### Current Risk

The business may later need customer profitability and service order cost tracking.

Potential needs:

- Service order.
- Sales order.
- Customer.
- Billable versus non-billable.
- Reimbursable versus internal cost.

### Business Rule Needed

Define whether a project can link to:

- Sales Order.
- Service Order.
- Customer.

Also define:

- Is the expense billable to customer?
- Should it affect project margin?
- Should it be reported separately from internal expense?

### Recommended Development

Reserve model fields:

- `customer`
- `sales_order_no`
- `service_order_no`
- `billable_flag`
- `reimbursable_flag`

### Priority

Medium / Future.

## 13. Approval Rule Versioning / Snapshot

### Current Risk

Approval rules can change over time. Historical approvals should not be reinterpreted under new rules.

### Business Rule Needed

When a request is submitted, preserve approval decision context.

At minimum, store:

- Matched approval rule.
- Approval steps created at submission time.
- Actual approvers / candidate approvers.
- Approval timestamps.

### Recommended Development

Confirm whether approval task instances already preserve enough data.

If not, add snapshot fields:

- `approval_rule_code`
- `approval_rule_name`
- `approval_rule_version`
- `step_name`
- `step_type`
- `assigned_user`
- `assigned_role`

### Priority

High for audit confidence.

## 14. Budget Adjustment Approval

### Current Risk

Budget ledger supports adjustment, but manual budget adjustment is powerful.

If adjustments can be posted by admin without approval, project budget can be manipulated.

### Business Rule Needed

Budget adjustment should require authorization.

Suggested rule:

- Small adjustment: finance manager approval.
- Large adjustment: department head / executive approval.
- All adjustments require reason.
- All adjustments appear in audit report.

### Recommended Development

Add Budget Adjustment Request.

Possible fields:

- `project`
- `adjustment_amount`
- `reason`
- `requested_by`
- `approved_by`
- `approved_at`
- `status`

### Priority

Medium-High.

## 15. Duplicate Reimbursement / Same Receipt Detection

### Current Risk

V0.5 detects duplicate card transactions. Reimbursement duplicate risk is different.

Examples:

- Same receipt submitted twice.
- Same invoice submitted under PR and TR.
- Employee submits reimbursement after company card already paid.
- Same vendor invoice recorded twice.

### Business Rule Needed

Detect possible duplicate reimbursement / invoice.

Suggested matching fields:

- Requester.
- Vendor.
- Amount.
- Expense date.
- Invoice number.
- Receipt file hash.
- Reference number.

### Recommended Development

Add duplicate check for actual expenses, not just card transactions.

### Priority

Medium.

## 16. Role / Permission Granularity

### Current Risk

Accounting workbench is currently staff-permission based. This is too broad for production.

### Business Rule Needed

Separate roles:

- Accounting Clerk.
- Accounting Manager.
- Finance Admin.
- System Admin.
- Requester.
- Approver.
- Project Owner.
- Department Manager.

Example permission matrix:

| Action | Accounting Clerk | Accounting Manager | Finance Admin | System Admin |
| --- | --- | --- | --- | --- |
| Record actual expense | Yes | Yes | Yes | Maybe |
| Resolve review item | Limited | Yes | Yes | Maybe |
| Approve exception | No | Yes | Yes | No |
| Configure finance policy | No | No | Yes | Maybe |
| Reopen closed request | No | Yes | Yes | No |
| Adjust budget | No | Limited | Yes | No |

### Recommended Development

Create role/permission matrix and replace broad staff checks with explicit permissions.

### Priority

High before broad production rollout.

## 17. Report Export / Period Reporting

### Current Risk

V0.5 reports are simple operational tables without export or scheduled delivery.

### Business Rule Needed

Define monthly reporting set:

- Project budget summary.
- Department spending summary.
- Open commitments.
- Actual spend detail.
- Over-budget exceptions.
- Missing receipt report.
- Unmatched card transactions.
- Accounting review aging.
- Closed request list.

### Recommended Development

Add CSV/Excel export for finance reports.

Do not build an advanced dashboard yet.

### Priority

Medium.

## 18. Notification / Reminder / Aging Escalation

### Current Risk

Queues and task lists exist, but work can get stuck if users do not check them.

### Business Rule Needed

Define reminders:

- Approval task pending more than 2 business days.
- Accounting review pending more than 3 business days.
- Unmatched card transaction older than 7 days.
- Missing receipt older than 7 days.

### Recommended Development

Add reminder emails or dashboard alerts.

### Priority

Medium.

## 19. Attachment Retention / Deletion Control

### Current Risk

Attachments are auditable on upload/delete, but production policy should define whether users can delete receipts after actual expense is recorded.

### Business Rule Needed

Suggested:

- Before submission: requester can delete own attachment.
- After approval or actual posting: deletion requires accounting/admin permission.
- Deleted attachment should remain recoverable or at least audit logged.

### Recommended Development

Review attachment deletion permission and retention behavior.

### Priority

Medium.

## Recommended V0.6 Priority

### Must Review Before Pilot / Go-Live

1. Period Close / Financial Locking.
2. Refund / Credit / Return Handling.
3. Reopen / Correction Workflow.
4. Direct Project Cost Controls.
5. Department General Budget Handling.
6. Role / Permission Granularity.
7. Approval Rule Snapshot / Versioning Confirmation.

### Strong V0.6 Candidates

1. Approval Delegation / Escalation.
2. Line-Level Receipt Matching.
3. Emergency / After-the-Fact Purchase.
4. Budget Adjustment Approval.
5. Duplicate Reimbursement / Invoice Detection.

### Post-Go-Live Enhancements

1. Multi-Currency / Exchange Rate.
2. Tax / Shipping / Tip / Fee Breakdown.
3. Sales Order / Service Order Costing.
4. Report Export.
5. Notification / Reminder Automation.
6. Richer Amendment Redline Compare.

## Suggested Next Step

1. Review this gap list with business/accounting/finance.
2. Mark each item as `Go-Live Blocker`, `V0.6`, or `Post-Go-Live Enhancement`.
3. Run a limited pilot with one department.
4. Log real pilot issues.
5. Finalize V0.6 scope based on real control risk and pilot feedback.

## Current Position

The system is functional enough to pilot. The larger risk is no longer missing basic features. The larger risk is that real accounting edge cases could damage budget accuracy, audit trail integrity, or user trust if they are not controlled.
