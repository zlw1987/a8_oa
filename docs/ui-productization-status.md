# UI Productization Status

Last updated: 2026-05-11

## Current Project Stage

A8 OA is past the core workflow-build stage and is now in UI/UX productization for pilot usability.

The core business-control foundation currently includes:

- Purchase Request workflow.
- Travel Request workflow.
- Approval routing and approval task handling.
- Project budget reserve, consume, release, and ledger.
- Actual expense recording for PR and TR.
- Over-budget policy handling.
- Receipt policy handling.
- Missing receipt accounting review.
- Supplemental PR/TR requests for amount increases.
- Company card transaction allocation and split allocation.
- Duplicate card transaction review.
- Accounting Review Queue.
- Finance reports.
- GoDaddy/cPanel Git deployment helper files.

The main remaining risk is no longer basic workflow coverage. The main risk is pilot usability: users need clearer navigation, clearer next actions, and safer accounting/card reconciliation screens.

## UI-1 Completed

UI-1 introduced the reusable UI foundation:

- Global stylesheet in `static/css/app.css`.
- Reusable include templates for badges, cards, form fields, action panels, and tables.
- Cleaner base layout foundation.
- Grouped navigation model started.

## UI-2 Completed: PR/TR Detail Productization

PR and TR detail pages were redesigned around operational clarity.

Changed areas:

- `purchase/templates/purchase/pr_detail.html`
- `travel/templates/travel/tr_detail.html`
- `templates/includes/request_detail_header.html`
- `templates/includes/financial_summary_cards.html`
- `templates/includes/closeout_checklist.html`
- `templates/includes/open_issues_panel.html`
- `templates/includes/action_panel.html`
- `purchase/presentation.py`
- `travel/presentation.py`
- `common/presentation.py`
- `purchase/views.py`
- `travel/views.py`
- `static/css/app.css`

Main behavior:

- Request header shows status, owner, progress, and key metadata.
- Financial summary cards show estimated/requested amount, approved amount, actual spend, remaining reserve, variance, and open issues.
- Closeout checklist makes blockers visible near the top of the page.
- Available actions stay visible even when disabled.
- Disabled actions show reasons.
- Open issues panel links to blockers where possible.
- Audit/history sections are available but visually secondary.

## UI-2.5 Completed: Dropdown Navigation

Top navigation was changed from a long flat list to grouped dropdown navigation.

Changed areas:

- `common/navigation.py`
- `common/context_processors.py`
- `templates/includes/top_nav.html`
- `templates/includes/dropdown_nav.html`
- `purchase/templates/purchase/base.html`
- `config/settings.py`
- `static/css/app.css`
- `static/js/navigation.js`

Navigation groups:

- Dashboard
- Work
  - Purchase Requests
  - Travel Requests
  - My Tasks
  - My Approval History
- Finance
  - Accounting Review Queue
  - Card Transactions
  - Finance Reports
  - Variance Report
- Setup
  - Projects
  - Departments
  - Approval Rules
  - Over-Budget Policies
  - Receipt Policies
- Admin
  - Django Admin
  - User / Department Setup
  - System Setup

Main behavior:

- Navigation is permission-aware.
- Empty dropdown groups are hidden.
- Active section and active item are highlighted.
- Dropdown works by click.
- Dropdown also opens on desktop hover.
- Click outside closes open dropdowns.
- Escape closes open dropdowns.
- Enter/Space can toggle focused dropdown buttons.
- Hover behavior is restricted to desktop pointer environments.

## UI-2.6 Completed: Hover Dropdown Fix

The first hover implementation relied on JavaScript pointer detection. In user testing, hover did not open the dropdown. A CSS hover fallback was added.

Changed area:

- `static/css/app.css`

Current hover behavior:

- `@media (hover: hover) and (pointer: fine)` opens the dropdown when hovering on `.nav-menu`.
- JavaScript click and keyboard behavior remain in place.
- This avoids making the menu hover-only.

If hover still does not appear after deployment, check whether the latest CSS file is loaded. On GoDaddy, this may require `collectstatic` and app restart, depending on the deployed static-file setup.

## UI-3 Completed: Accounting Workbench Productization

Accounting Review Queue was changed from a dense table with inline decision forms into a workbench-style queue.

Changed areas:

- `finance/presentation.py`
- `finance/views.py`
- `finance/urls.py`
- `finance/templates/finance/accounting_review_queue.html`
- `finance/templates/finance/accounting_review_detail.html`
- `static/css/app.css`

Main behavior:

- Quick tabs:
  - All Pending
  - Over-Budget
  - Missing Receipt
  - Amendment Required
  - Duplicate Card
  - Returned
  - Resolved
- Aging badges:
  - Aging 0-2 days
  - Aging 3-7 days
  - Aging 8+ days
- Severity badges:
  - Critical
  - High
  - Normal
- Required action is shown as a dedicated column.
- Source PR/TR/card links are visible.
- Queue rows no longer contain full decision forms.
- Decision handling moved to Accounting Review Detail.
- Requester self-review prevention remains enforced in the view.

## UI-3 Polish Completed: Accounting Queue Filter Cleanup

The Accounting Review Queue filter panel was cleaned up after user review.

Changed areas:

- `finance/forms.py`
- `finance/presentation.py`
- `finance/views.py`
- `finance/templates/finance/accounting_review_queue.html`
- `static/css/app.css`

Main behavior:

- Basic filters are visible and labeled.
- Advanced filters are collapsed by default.
- Filter and Reset actions are visually grouped.
- Reset clears filters while preserving the active quick tab.
- Quick tabs show item counts.
- Empty state explains whether no items exist for the tab or no items match current filters.

## UI-4 Completed: Card Transaction Reconciliation UI

Card Transaction Detail was redesigned around reconciliation.

Changed areas:

- `finance/templates/finance/card_transaction_detail.html`
- `finance/presentation.py`
- `finance/views.py`
- `static/js/card_reconciliation.js`
- `purchase/templates/purchase/base.html`
- `static/css/app.css`

Main behavior:

- Summary cards show:
  - Transaction Amount
  - Allocated Amount
  - Unallocated Amount
  - Match Status
  - Open Reviews
  - Duplicate Warning
- Unallocated Amount is visually prominent.
- Allocation panel shows remaining unallocated amount.
- Front-end validation prevents allocation amount above remaining unallocated amount.
- Back-end allocation validation remains unchanged.
- Mark Reviewed is always visible.
- Mark Reviewed shows disabled reason when unavailable.
- Duplicate warning links to related review item when available.
- Allocations clearly link to PR/TR/project.
- Review items link to Accounting Review Detail.

## Finance Reports Polish Completed: Base-Currency Money Display

Finance Reports now use consistent money formatting and show USD company base-currency totals.

Changed areas:

- `common/templatetags/money.py`
- `finance/reporting.py`
- `finance/templates/finance/reports.html`
- `finance/tests.py`

Main behavior:

- Money values show currency code, thousand separators, and two decimal places.
- Top Reserved / Released / Consumed totals are shown in company base currency.
- Project, department, open reserve, over-budget, and card amount fields use the shared money formatter.
- Foreign-currency source amounts are preserved on source records and shown where relevant, while report totals use base currency.

## UI-5 Completed: List Page Pattern And Role-Based Dashboard

UI-5 standardized key list/setup pages and turned the Dashboard into a role-aware operating screen.

Changed areas:

- `dashboard/views.py`
- `dashboard/templates/dashboard/home.html`
- `purchase/templates/purchase/pr_list.html`
- `travel/templates/travel/tr_list.html`
- `projects/templates/projects/project_list.html`
- `accounts/templates/accounts/department_list.html`
- `approvals/templates/approvals/rule_list.html`
- `finance/templates/finance/over_budget_policy_list.html`
- `finance/templates/finance/receipt_policy_list.html`
- `finance/templates/finance/card_transaction_list.html`
- `static/css/app.css`

Main list-page behavior:

- Page-level create actions are separated from filter panels.
- Filter panels contain only filter-related controls.
- Tables are wrapped for horizontal overflow.
- Money values in key list pages use the shared money formatter where applicable.

Main dashboard behavior:

- Dashboard cards are grouped by priority: My Work Today, Approval Summary, My Requests / Recent Activity, oversight, and setup shortcuts.
- Zero-count urgent cards are hidden from the top section to keep the page from becoming a wall of cards.
- Admin/setup shortcuts are visually lower priority and can be collapsed.
- Requesters see draft, returned, pending approval, approved-not-closed, missing receipt, and create request cards.
- Approvers see Approval Summary cards for pending tasks, pool tasks, recently approved items, and returned/rejected items.
- Accounting users see pending reviews, missing receipt, over-budget, amendment-required, unmatched card, duplicate card, and ready-to-close cards.
- Finance admins see aging, budget risk, exceptions, unmatched card, receipt issue, finance report, and policy setup shortcuts.
- System admins see setup shortcuts.
- Dashboard cards link to the relevant worklist or filtered queue where the user has permission.

## V1.1A Setup UX Completed

System Setup is now a real internal landing page instead of a duplicate Django Admin link.

Changed areas:

- `dashboard/views.py`
- `dashboard/urls.py`
- `dashboard/templates/dashboard/system_setup.html`
- `common/navigation.py`
- `common/permissions.py`
- `static/css/app.css`

Main behavior:

- Admin dropdown separates Django Admin from System Setup.
- System Setup shows setup shortcuts, status cards, current version, and role/permission matrix.
- Setup visibility uses shared permission helpers.
- Approval Rule Step Editor uses step cards/accordion instead of a wide editable table.
- Finance Reports include CSV export.

## User Guide Maintenance Rule

When UI or workflow behavior changes, update the formal user guides directly:

- `docs/user-guide-zh.md`
- `docs/user-guide-en.md`

Do not create a separate temporary instruction-update document unless it is specifically requested. The user guides are the source of truth for end users.

## Current Verification

Latest targeted checks run by Codex:

```text
python manage.py check
Result: passed

Django template loader check:
includes/top_nav.html
finance/accounting_review_queue.html
finance/accounting_review_detail.html
finance/card_transaction_detail.html
Result: passed
```

Full test suite was not run because full test execution is reserved for the user.

## Current Known Limitations

- Screenshots were not captured in Codex because the local browser connection was blocked in this environment.
- The UI is still not a full mobile-first redesign.
- Finance reports are still table-oriented.
- Finance reports are currency-grouped, not exchange-rate converted.
- Accounting Review Detail does not yet show line-level receipt attachment matching because line-level receipt matching is not implemented as a business feature.
- Card allocation front-end validation is convenience validation only. Server-side validation remains the source of truth.

## Recommended Next Review

Before adding new business-control features:

1. User tests navigation hover/click behavior locally.
2. Accounting user reviews Accounting Review Queue and Detail page.
3. Accounting user reviews Card Transaction Detail reconciliation flow.
4. Run full regression tests locally.
5. Only then decide whether to continue with UI polish or pilot-hardening business controls.
