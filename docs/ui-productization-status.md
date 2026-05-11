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
- Accounting Review Detail does not yet show line-level receipt attachment matching because line-level receipt matching is not implemented as a business feature.
- Card allocation front-end validation is convenience validation only. Server-side validation remains the source of truth.

## Recommended Next Review

Before adding new business-control features:

1. User tests navigation hover/click behavior locally.
2. Accounting user reviews Accounting Review Queue and Detail page.
3. Accounting user reviews Card Transaction Detail reconciliation flow.
4. Run full regression tests locally.
5. Only then decide whether to continue with UI polish or pilot-hardening business controls.
