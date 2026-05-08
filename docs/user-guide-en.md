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

The Dashboard may show:

- Your approval tasks.
- Recent purchase requests.
- Recent travel requests.
- Request statuses related to you.

Top navigation may include:

- Dashboard
- Purchase Requests
- Travel Requests
- Projects
- My Tasks
- My Approval History
- Accounting Review Queue
- Card Transactions
- Finance Reports
- Variance Report
- Departments
- Approval Rules
- Over-Budget Policies
- Receipt Policies
- Admin

Visible menus depend on your permissions.

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

Current version checks request-level attachments. It does not yet match receipts to individual actual expense lines.

## 9. Accounting Review Queue

Open Accounting Review Queue.

You can filter by:

- Status.
- Reason.
- Source type.
- Policy action.
- Requester.
- Department.
- Project.
- Aging days.
- Keyword.

Each review item shows:

- Source request or card transaction.
- Requester, department, and project.
- Reason.
- Amount.
- Over-budget amount.
- Policy action.
- Required action.
- Comments.

Accounting can choose:

- Approve Exception.
- Return.
- Reject.
- Resolve.

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

Choose one target:

- Purchase Request.
- Travel Request.
- Project direct cost.

Enter the allocation amount.

The system will:

- Prevent allocation above the unallocated amount.
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

### 10.5 Duplicate Transactions

If the system finds the same transaction date, merchant, amount, and reference, it creates a duplicate review item.

The system does not automatically block the transaction because legitimate duplicate transactions can happen.

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

These reports are operational tables for daily use and UAT, not advanced BI dashboards.

## 12. Finance Policy Setup

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

Project budget is affected by:

- RESERVE: budget reserved by request submission or amendment approval.
- CONSUME: budget consumed by actual expense posting.
- RELEASE: reserved budget released by close, return, cancel, reject, or actual conversion.
- ADJUST: manual adjustment.

Project detail and budget ledger show the full history.

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

### I uploaded an attachment. Why is there still a missing receipt review?

The current version checks request-level attachments. If the review item already exists, accounting still needs to Resolve it or Approve Exception in the Accounting Review Queue.

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
