# A8 OA User Guide

## 1. What The System Does

A8 OA manages internal purchase requests, travel requests, approval workflows, project budgets, actual expenses, company card transactions, and accounting reviews.

The main goals are:

- Check budget before requests move forward.
- Match approval rules when a request is submitted.
- Reserve budget after submission or amendment approval.
- Consume budget when actual expenses are recorded.
- Route over-budget, missing receipt, duplicate card, and other exceptions to accounting review.
- Prevent closeout until budget, attachment, approval, and accounting review items are complete.

## 2. Common Roles

| Role | Main Work |
| --- | --- |
| Requester | Create PR/TR, submit for approval, upload attachments, handle returned requests |
| Approver | Approve, return, reject, claim, or release approval tasks |
| Manager | Approve department requests and review team activity |
| Accounting | Record actual expenses, handle accounting reviews, allocate card transactions |
| Finance Admin | Maintain over-budget policies, receipt policies, and review finance reports |
| System Admin | Maintain users, departments, projects, approval rules, and setup data |

## 3. Login And Home Page

1. Open the system URL.
2. Sign in with your username and password.
3. The system opens the Dashboard.

The Dashboard is organized by priority:

- My Work Today: urgent items such as pending approvals, returned requests, missing receipts, pending accounting reviews, unmatched card transactions, and open blockers.
- Approval Summary: approval task counts and recent approval activity.
- My Requests / My Recent Activity: drafts, pending approval, approved-not-closed items, create request shortcuts, and recent request tables.
- Team / Department / Finance Oversight: finance and manager-level exception cards when permitted.
- Admin / Setup Shortcuts: lower-priority setup links, usually collapsed or visually de-emphasized.

The Dashboard is permission-aware. Normal requesters do not see finance/admin work cards.

Top navigation is grouped into dropdown menus:

- Dashboard.
- Work: Purchase Requests, Travel Requests, My Tasks, My Approval History.
- Finance: Accounting Review Queue, Card Transactions, Accounting Periods, Finance Reports, Variance Report.
- Setup: Projects, Create Project when permitted, Departments, Approval Rules, Over-Budget Policies, Receipt Policies.
- Admin: Django Admin and system setup links.

Visible menus depend on your permissions. Empty menu groups are hidden.

On desktop, hover over Work, Finance, Setup, or Admin to open the dropdown. You can also click the menu group. Click outside the menu or press Escape to close it.

Language switcher:

- The top navigation includes English and 中文 buttons.
- English is the default language.
- 中文 switches supported shell pages and high-traffic workbench pages into Simplified Chinese.
- The first translated batch includes top navigation, Dashboard shell/cards, Finance Reports, Department Spending drill-down, Accounting Review Queue/Detail key labels, and System Setup key labels.
- This is not full product-wide localization yet. Full PR/TR detail pages, most setup forms, many Python validation/messages, and Django Admin may still show English.
- Database codes, status values, enum values, and user-entered text are not translated or changed.

List and setup pages follow a consistent layout:

1. Page title and primary action, such as Create Rule or New Project.
2. Optional summary cards.
3. Filters with only filter-related controls.
4. Data table.
5. Pagination when needed.

Create, New, Add, and Import actions are page-level actions. They are not part of the Filters panel.

## 3.1 System Setup

System Setup is a business setup hub. It is separate from Django Admin.

System Setup shows:

- Base currency and active currencies.
- Departments, projects, approval rules, and finance policy status.
- Currency, exchange-rate, and FX variance policy shortcuts.
- Current version and setup health notes.
- Role / permission matrix.

Normal requesters cannot access System Setup.

Finance/Admin users can use System Setup to navigate setup areas without treating Django Admin as the main business UI.

## 4. Purchase Request Flow

### 4.1 Create A Purchase Request

1. Open Purchase Requests.
2. Create a new purchase request.
3. Enter header details:
   - Title.
   - Request department.
   - Project.
   - Currency.
   - Request date.
   - Business justification.
4. Add purchase lines:
   - Item name.
   - Quantity.
   - Unit price.
   - Amount.
   - Description.
5. Save the draft.

### 4.2 Upload Attachments

Upload supporting files on the request detail page, such as:

- Vendor quote.
- Supplier information.
- Contract draft.
- Receipt or invoice.
- Other supporting files.

Attachment upload and deletion are written to content audit history.

### 4.3 Submit For Approval

1. Review the request and budget.
2. Click Submit.
3. The system will:
   - Check that the project is open.
   - Check available budget.
   - Match an approval rule.
   - Create approval tasks.
   - Reserve budget.

Submission fails if no active approval rule is available.

### 4.4 Approval

Approvers use My Tasks.

Available actions can include:

- Approve.
- Return.
- Reject.
- Claim from pool.
- Release back to pool.

Approval history records each action.

### 4.5 Record Actual Purchase Spend

After the PR is fully approved, accounting or an authorized user can record actual spend.

Enter:

- Spend date.
- Amount.
- Vendor.
- Reference or invoice number.
- Notes.

The system will:

- Apply over-budget policy.
- Apply receipt / invoice policy.
- Create the actual spend record.
- Consume project budget.
- Release the related reserved budget.
- Create accounting review items when needed.

### 4.6 Close A Purchase Request

A PR can close only when:

- The request is approved.
- No unresolved accounting review item exists.
- No open approval task exists.
- No open amendment / supplemental request exists.
- Related card transactions are reconciled.

Closing releases any remaining reserved budget.

The PR detail page shows the closeout checklist near the top. If Close Request is disabled, read the disabled reason and the checklist before asking for help.

## 5. Travel Request Flow

### 5.1 Create A Travel Request

1. Open Travel Requests.
2. Create a travel request.
3. Enter:
   - Purpose.
   - Request department.
   - Project.
   - Origin city and destination city.
   - Start date and end date.
   - Currency.
4. Add itinerary lines:
   - Date.
   - From city.
   - To city.
   - Transport type.
5. Add estimated expense lines:
   - Transportation.
   - Hotel.
   - Meals.
   - Visa.
   - Registration.
   - Miscellaneous.

### 5.2 Per Diem

If per diem policies are enabled, the system calculates:

- Allowed per diem.
- Claimed per diem.
- Whether claimed per diem exceeds the allowed amount.

Review per diem totals before submission.

### 5.3 Submit And Approve

When a TR is submitted, the system will:

- Check that itinerary lines exist.
- Check that estimated expense lines exist.
- Calculate estimated total.
- Check project budget.
- Match an approval rule.
- Create approval tasks.
- Reserve budget.

The approval process is similar to purchase requests.

### 5.4 Record Actual Travel Expense

After approval, actual travel expenses can be recorded.

Enter:

- Expense type.
- Expense date.
- Actual amount.
- Currency.
- Vendor.
- Reference.
- Location.
- Notes.

The system will:

- Keep estimates and actual expenses separate.
- Apply over-budget policy.
- Apply receipt / invoice policy.
- Consume project budget.
- Release related reserved budget.
- Create accounting review items when needed.

### 5.5 Close A Travel Request

Before closeout, confirm:

- Actual expenses are recorded.
- Accounting review items are resolved.
- Receipt / invoice requirements are satisfied or exceptions are approved.
- Company card transactions are matched.
- No amendment remains open.

Closing releases remaining reserved budget.

The TR detail page uses the same layout as PR detail. Review the financial summary, closeout checklist, available actions, and open issues first.

## 6. Over-Budget Policy

The system supports four main actions:

| Action | Result |
| --- | --- |
| WARNING | Show a warning, but allow actual expense recording |
| REVIEW | Create an accounting review item and block closeout until resolved |
| AMENDMENT_REQUIRED | Require supplemental request or accounting exception before closeout |
| BLOCK | Block actual expense posting and prevent incorrect budget consumption |

### 6.1 Warning

Used for small variances.

Result:

- Actual expense can be saved.
- Warning is recorded.
- The request can close if no other unresolved item exists.

### 6.2 Review

Used when accounting review is required.

Result:

- Actual expense can be saved.
- Accounting Review Item is created.
- Request closeout is blocked until accounting resolves it.

### 6.3 Amendment Required

Used when the approved amount needs a formal increase.

Result:

- Actual expense may be recorded, but it is not fully cleared.
- Accounting Review Item is created.
- Closeout is blocked.
- A supplemental request or approved accounting exception is required.

### 6.4 Block

Used for severe over-budget cases.

Result:

- Actual expense cannot be posted.
- A clear error is shown.
- Budget is not consumed.

## 7. Amendment / Supplemental Request

Approved requests should not be directly edited to increase budget.

If more budget is needed:

1. Create a supplemental request from the original request.
2. The supplemental request carries only the additional amount.
3. The original request remains unchanged.
4. The supplemental request goes through approval.
5. Additional budget is reserved only after supplemental approval.
6. The original request shows linked supplemental requests.

The original request cannot close while linked supplemental requests are still open.

## 8. Receipt / Invoice Policy

Finance can configure rules such as:

- Receipt optional below a threshold.
- Receipt required above a threshold.
- Invoice required above a higher threshold.
- Company card transaction requires receipt unless an exception is approved.

If a required attachment is missing:

- The system creates a MISSING_RECEIPT accounting review item.
- Request closeout is blocked.
- The user should upload the attachment, or accounting should approve an exception / resolve the review item.

Request-level attachments still exist for quotes, contracts, and general support. Receipt and invoice evidence can now be linked to the exact actual expense line from the PR/TR detail page. Missing receipt reviews point accounting users to the specific actual expense line that needs support.

## 9. Accounting Review Queue

Open Accounting Review Queue.

Use the quick tabs first:

- All Pending.
- Over-Budget.
- Missing Receipt.
- Amendment Required.
- Duplicate Card.
- Returned.
- Resolved.

You can filter by:

- Keyword.
- Status.
- Reason.
- Source type.
- Policy action.

Advanced filters are collapsed by default. Open Show Advanced Filters when you need:

- Requester.
- Department.
- Project.
- Minimum aging days.

Filter only applies the current filters. Reset clears filters while keeping the selected quick tab.

Each review item shows:

- Source request or card transaction.
- Requester, department, and project.
- Reason.
- Amount.
- Over-budget amount.
- Policy action.
- Aging badge.
- Severity badge.
- Required action.
- Status.

Accounting can choose:

- Approve Exception.
- Return.
- Reject.
- Resolve.

Use View to open the Accounting Review Detail page before making complex decisions. The detail page shows the issue summary, source links, financial impact, receipt / attachment status, decision history, and action panel.

Requesters cannot review their own accounting review items.

## 10. Company Card Transactions

### 10.1 Create Or Import A Transaction

Open Card Transactions and create a transaction.

Enter:

- Statement date.
- Transaction date.
- Merchant.
- Amount.
- Currency.
- Cardholder.
- Reference.

The system checks for possible duplicate transactions.

### 10.2 One-To-One Allocation

On the card transaction detail page, add an allocation.

The detail page is organized for reconciliation. Review the summary cards first:

- Transaction Amount.
- Allocated Amount.
- Unallocated Amount.
- Match Status.
- Open Reviews.
- Duplicate Warning.

Unallocated Amount is the key number. It shows how much is still not allocated.

Choose one target:

- Purchase Request.
- Travel Request.
- Project direct cost.

Enter the allocation amount.

The system will:

- Prevent allocation above the unallocated amount.
- Show a front-end warning if the entered allocation amount exceeds the remaining unallocated amount.
- Apply actual expense logic for PR or TR targets.
- Apply company card finance policy.
- Update match status.

### 10.3 Split Allocation

One card transaction can be split across multiple targets.

Example:

- Allocation 1: PR001, 1000.
- Allocation 2: TR002, 500.

Total allocations cannot exceed the transaction amount.

### 10.4 Match Status

| Status | Meaning |
| --- | --- |
| Unmatched | No allocation exists |
| Partially Matched | Some amount has been allocated |
| Matched | Fully allocated |
| Reviewed | Accounting has confirmed the matched transaction |

A transaction can be marked Reviewed only when it is Matched and has no unresolved review items.

The Mark Reviewed button remains visible. If it is disabled, the page shows the reason.

### 10.5 Duplicate Transactions

If the system finds the same transaction date, merchant, amount, and reference, it creates a duplicate review item.

The system does not automatically block the transaction because legitimate duplicate transactions can happen.

If a duplicate warning exists, open the linked review item from the card transaction detail page.

## 11. Finance Reports

Open Finance Reports.

Available reports include:

- Project budget summary.
- Department spending summary.
- Reserved vs consumed budget.
- Open requests with remaining reserve.
- Over-budget exception report.
- Company card unmatched transaction report.
- Accounting review aging report.

Use Export CSV to download a finance report extract. The export includes base currency amount columns and original transaction currency columns where available.

These reports are operational tables for daily use and UAT, not advanced BI dashboards.

Department Spending Summary rows can be opened to view department-level source records. The drill-down page shows related projects, PRs, TRs, purchase actual spend, and travel actual expenses for that department.

Money values on Finance Reports always show:

- Currency code.
- Thousand separators.
- Two decimal places.

Example: USD 12,710.00.

Current Finance Reports are base-currency reports. The company base currency is USD.

For foreign-currency activity, the system preserves the original transaction currency and amount on source records, accounting review items, and company card transactions. Budget control, consumed amount, released amount, and management report totals use the USD base amount.

Company card foreign transactions use the card statement posted USD amount as the authoritative base amount when it is available.

PR/TR detail pages show actual expenses with both base amount and original transaction amount when foreign-currency data is available.

If a foreign-currency actual expense exceeds the approved USD base amount only because the exchange rate changed, the system can classify it as FX Variance instead of ordinary spending overrun. If the original transaction amount also increased, it is treated as spending overrun.

## 11.1 Financial Integrity Controls

Accounting periods are available from Finance > Accounting Periods and System Setup > Accounting Periods.

Accounting periods can be configured as Open, Closing, or Closed. The period detail page shows a Period Close Checklist for open reviews, missing receipts, unmatched card transactions, open requests with remaining reserve, and open correction workflows.

When a period is Closed, ordinary financial changes in that period are blocked, including actual expense posting and card allocation changes. Finance/Admin adjustment handling is controlled separately.

Finance/Admin users can close a period with close notes. Reopening a closed period requires a reason and is limited to finance setup users.

Accounting users can record Refund / Credit / Reversal entries from the PR/TR detail page. Refunds and credits are recorded as separate negative actual entries. The original actual expense remains visible, and the refund reduces consumed budget through a negative budget ledger entry.

Closed PR/TR records can only be reopened for correction by Finance/Admin users. Reopen requires a reason, writes history, and reclose runs the normal closeout validation again.

Line-level receipt matching is available on PR/TR detail pages. In the Actual Expenses section, users with permission can upload a receipt/invoice directly to a specific actual expense line or link an existing request-level attachment to that line.

Missing receipt review items now point accounting users to the specific actual expense line that needs support. Linking the required receipt or invoice can resolve the missing receipt review path instead of relying on a generic request-level attachment.

Direct project cost allocation from company card transactions is policy controlled. Finance can configure whether direct project cost is allowed, reviewed, requires project owner approval, or blocked.

Direct Project Cost Policies are available under Setup > Direct Project Cost Policies and System Setup. When accounting allocates a company card transaction directly to a project, the card detail page shows the policy result and project owner review status when applicable.

Approval delegation can be configured from Work > My Delegations. Approvers can create date-range delegations, and finance/admin users can view active delegations or reassign stuck approval tasks with a reason. Delegation does not allow requester self-approval.

## 12. Finance Policy Setup

System Setup is the recommended business setup hub for Finance/Admin users. It now links to business UI pages for currencies, exchange rates, FX variance policies, accounting periods, and finance policies instead of requiring normal setup work in Django Admin.

Company base currency is currently USD. This is shown in System Setup and Finance Reports. It is not freely editable in the UI because changing base currency would require a controlled conversion and migration plan for budget ledger, actual expense, company card, and reporting history.

### 12.0 Currency And Exchange Rate Setup

Open Currencies to maintain active transaction currencies such as USD, TWD, EUR, and JPY.

Open Exchange Rates to maintain company exchange rates by effective date. Exchange rates are snapshotted when actual expenses are posted, so historical transactions are not silently recalculated when later rates change.

Open FX Variance Policies to control exchange-rate-driven variance separately from true spending overrun.

### 12.1 Over-Budget Policies

Open Over-Budget Policies.

You can configure:

- Request type.
- Department.
- Project type.
- Payment method.
- Currency.
- Over-budget amount range.
- Over-budget percentage range.
- Action: Warning / Review / Amendment Required / Block.
- Priority.
- Active flag.

### 12.2 Receipt Policies

Open Receipt Policies.

You can configure:

- Request type.
- Department.
- Project type.
- Expense type.
- Payment method.
- Currency.
- Amount range.
- Receipt required.
- Invoice required.
- Exception allowed.
- Priority.
- Active flag.

Lower priority numbers match first.

## 13. Project Budget

### 13.1 Department General Budget Setup

Finance/Admin users can open Department General Budget Setup from System Setup or Setup > Department General Budgets.

Use this page to map each department and fiscal year to one Department General Budget project, such as `MIS-GENERAL-2026`.

Rules:

- The general project must belong to the selected department.
- The project type must be Department General Budget.
- System Setup shows a missing setup warning for active departments that do not have a current fiscal-year general project.
- General PR/TR spending should use the correct department general project.

If a Department General Budget project is selected for a PR/TR, the request department must match the project's owning department.

Project budget is affected by:

- RESERVE: budget reserved by request submission or amendment approval.
- CONSUME: budget consumed by actual expense posting.
- RELEASE: reserved budget released by close, return, cancel, reject, or actual conversion.
- ADJUST: approved budget adjustment posted from a Budget Adjustment Request.

Project detail and budget ledger show the full history.

### 13.2 Budget Adjustment Requests

Project managers can submit a Budget Adjustment Request from the project budget ledger.

Important rules:

- Submitting an adjustment request does not change the budget ledger.
- Finance/Admin must approve and post the request before an ADJUST ledger entry is created.
- Rejected adjustment requests do not affect the project budget.
- A reason is required for audit.

### 13.3 Approval Rule Snapshot

When a PR/TR/project budget request is submitted, the approval task stores the approval rule code, rule name, rule version, step name, step type, assigned user, and candidate pool snapshot.

If the approval rule is changed later, old request approval history still shows the rule snapshot that was used at submission time.

### 13.4 Duplicate Actual Expense / Invoice Review

When accounting records an actual expense, the system checks for possible duplicate actual expenses using vendor/merchant, expense date, amount, and reference number.

When receipts or invoices are linked to actual expense lines, the system also compares attachment file hashes. This helps detect the same receipt or invoice being reused on another actual expense line.

If a possible duplicate is found:

- The actual expense is not deleted automatically.
- An Accounting Review Item is created.
- Accounting can review and approve the exception or resolve the duplicate.
- Accounting Review Detail shows runtime-computed duplicate candidates with links back to the related PR/TR detail page when the candidate can be resolved.

Important limitation:

- Duplicate candidates are calculated from current records when the review detail page is opened. They are not stored as an immutable duplicate snapshot.

### 13.5 Attachment Retention

Attachments are audit evidence.

Current rules:

- Draft attachments can still be removed by authorized users.
- Attachments are soft-deleted so the audit trail can retain deletion information.
- Receipts or invoices linked to actual expense lines cannot be removed by normal requesters after posting.
- Accounting/Admin users can void posted or linked evidence only with a reason.
- PR/TR detail pages show Attachment History for soft-deleted or voided attachments.
- Closed request attachments are retained for audit and cannot be normally deleted.

Current limitation:

- This is a void-with-reason workflow. A full attachment replacement workflow is not implemented yet.

### 13.6 Finance Report Drill-Down

Finance Reports include link-based drill-down:

- Project Budget Summary opens the project budget ledger.
- Department Spending Summary opens department-level source records.
- Over-Budget Exceptions open Accounting Review Detail.
- Accounting Review Aging opens Accounting Review Detail.
- Open Reserve rows open the source PR/TR.
- Unmatched Card rows open the card transaction detail.

This is an operational drill-down pattern, not an advanced reporting or BI framework. Excel export, saved filters, and date/department/project report filters are not implemented yet.

## 14. FAQ

### Why can I not close a request?

Common reasons:

- Unresolved Accounting Review Item.
- Open approval task.
- Open amendment.
- Unmatched or partially matched card transaction.
- Actual review is still pending.

### Why can I not save an actual expense?

Common reasons:

- The request is not approved.
- Amount is zero or negative.
- Project budget is insufficient.
- Over-budget policy action is BLOCK.
- The expense date is inside a closed accounting period.

### Why can I not allocate a company card transaction?

Common reasons:

- The allocation amount exceeds the unallocated transaction amount.
- The transaction date is inside a closed accounting period.
- A direct project cost policy blocks the allocation.

### I uploaded an attachment. Why is there still a missing receipt review?

Receipt support should be linked to the exact actual expense line. Open the PR/TR detail page, find the actual expense line, then use Upload or Link Existing Attachment. If a review item already exists, the line-level receipt link can clear the missing receipt path; otherwise accounting can Resolve or Approve Exception from the Accounting Review Detail page.

### How do I delegate approvals while I am away?

Open Work > My Delegations, create a delegation, choose the delegate user, and set the start/end dates. The delegate can see delegated tasks in My Tasks during the active date range. They still cannot approve their own request.

### Why can a direct project cost allocation be blocked?

Finance can configure Direct Project Cost Policies. A policy may allow the allocation, create an accounting review, require project owner review, or block direct posting entirely. If blocked, allocate the card transaction to an approved PR/TR or ask Finance to review the policy.

### What should I do when a request is returned?

The requester should update the request and resubmit it. The approval workflow starts again.

## 15. Go-Live Recommendations

Before go-live:

- Confirm approval rules.
- Confirm project and department master data.
- Confirm over-budget policies.
- Confirm receipt policies.
- Create test users.
- Run one purchase flow UAT.
- Run one travel flow UAT.
- Run one card allocation UAT.
- Run one accounting review UAT.
