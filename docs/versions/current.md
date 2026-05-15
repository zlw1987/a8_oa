# Current Version

## Status

The current version includes V1.2B Chinese UI Mode foundation and V1.2A Finance Reports drill-down enhancement on top of V1.1 Phase 3 completed and closed, the V0.5 business-control milestone, V0.6 multi-currency foundation, V1.1 Phase 1 financial-integrity workflows, and V1.1 Phase 2 expense-control workflows.

## Latest Fixes

- Cleaned up Accounting Review Queue filters with visible labels, Basic/Advanced sections, tab counts, preserved-tab reset behavior, and clearer empty states.
- Added V1.2B Chinese UI Mode foundation: Django i18n infrastructure, English / 中文 switcher, and first translation batch for top navigation, Dashboard shell/cards, Finance Reports, Department Spending drill-down, Accounting Review Queue/Detail key labels, and System Setup key labels.
- Added V1.2A Finance Reports Department Spending drill-down. Department Spending Summary rows now open a department detail page with related projects, PRs, TRs, purchase actual spend, and travel actual expenses.
- Stabilized Dashboard information hierarchy with My Work Today, Approval Summary, My Requests, oversight, and collapsible setup sections.
- Added V1.1A System Setup landing page, shared role/permission helpers, and Admin dropdown cleanup.
- Added V1.1B/V1.1C foundation models for accounting periods, refund/correction, line-level receipt links, direct project cost policy, and approval delegation/escalation.
- Implemented V1.1 Phase 1 operational workflows: Accounting Period list/detail/create/close/reopen UI, period close checklist, PR/TR refund-credit-reversal entry forms, and PR/TR reopen-for-correction forms.
- Added closed-period validation to card transaction creation, card allocation, PR actual spend, TR actual expense, and refund/credit entry paths.
- Closed V1.1 Phase 1 as completed after full test, UAT, and accounting validation.
- Prepared V1.1 Phase 2 technical design for line-level receipt matching UI, direct project cost policy workflow, approval delegation UI, and overdue approval handling.
- Implemented V1.1 Phase 2 expense-control and approval-operations workflows: line-level receipt/invoice linking on PR/TR actual expense lines, Direct Project Cost Policy setup and card allocation enforcement, approval delegation UI, admin task reassignment, and `process_approval_escalations` command alias.
- Closed V1.1 Phase 2 as completed after required tests and business/accounting/manager validation.
- Prepared V1.1 Phase 3 technical design for remaining go-live control closure: department general budget, approval rule snapshots, budget adjustment approval, duplicate reimbursement/invoice detection, attachment retention, and optional report drill-down.
- Started V1.1 Phase 3 implementation with System Setup / Currency Setup hardening and Department General Budget Setup.
- Added business UI pages for Currencies, Exchange Rates, and FX Variance Policies so normal finance setup no longer depends on Django Admin pages.
- Added Department General Budget Setup with current-year System Setup warning for departments missing annual general projects.
- Added PR/TR validation so Department General Budget projects must match the request department.
- Added approval rule snapshot fields on approval tasks so historical request approval context remains visible after approval rules change.
- Changed manual project budget adjustment into a controlled Budget Adjustment Request workflow; budget ledger `ADJUST` entries are posted only after Finance approval.
- Added duplicate actual expense / invoice review detection based on vendor, date, amount, and reference matching.
- Extended duplicate actual expense detection to compare linked receipt/invoice file hashes.
- Added runtime duplicate candidate traceability on Accounting Review Detail. Candidate links are computed from current records and are not persisted as an immutable duplicate snapshot.
- Added attachment retention controls: request attachments are soft-deleted for audit visibility, linked receipt/invoice evidence cannot be removed by normal requesters after posting/approval, Accounting/Admin void requires reason, closed request attachments are retained, and PR/TR detail pages show Attachment History.
- Added Finance Reports link-based drill-down from project summaries to budget ledgers, review rows to Accounting Review Detail, open reserves to PR/TR detail, and unmatched card rows to card transaction detail. This is not an advanced reporting framework.
- Removed tracked runtime media upload artifacts from the repository and kept `media/` ignored for future local uploads.
- Hardened GoDaddy cPanel Git deployment script so deploy logs initialize correctly, Python virtualenv path is auto-detected, same-path rsync is skipped, migrations run during Deploy HEAD Commit, and Passenger is restarted.
- Added Finance Reports CSV export with base and transaction currency columns.
- Converted Approval Rule Step Editor from a wide table into step cards/accordion sections.
- Restored the Dashboard `Approval Summary` section title for regression compatibility.
- Unified Create Project visibility through `projects.access.user_can_create_project` and added a permission-aware Create Project link under Setup navigation.
- Added horizontal containment for the Approval Steps editor so wide formsets no longer overflow the card.
- Added V0.6 multi-currency foundation: USD company base currency, transaction/base amount snapshots, exchange-rate snapshots, FX variance classification, and base-currency Finance Reports.
- Added Currency, ExchangeRate, and FXVariancePolicy models for finance control setup.
- Updated PR/TR actual expense recording and company card allocation paths to preserve original transaction currency while consuming budget in USD base currency.
- Moved Approval Rules `Create Rule` out of the Filters panel into a page-level primary action area.
- Added a reusable `money` template filter and updated Finance Reports to show currency code, thousand separators, and two decimal places.
- Updated Finance Reports to show company base-currency totals and original transaction currency detail where relevant.
- Standardized key list/setup pages so primary creation actions sit outside filter panels.
- Added role-based Dashboard cards for requester, approver, accounting, finance admin, and system admin work.
- Updated English and Chinese user guides for the latest navigation, accounting workbench, and card reconciliation UI.
- Added UI productization status documentation.
- Added desktop hover fallback for dropdown navigation.
- Productized PR/TR detail pages with financial summary cards, closeout checklist, available actions, and open issues.
- Productized top navigation as permission-aware dropdown groups with active states.
- Productized Accounting Review Queue with quick tabs, aging badges, severity badges, required action, and a detail page.
- Productized Card Transaction Detail as a reconciliation page with allocated/unallocated summary, disabled review reason, duplicate review link, and allocation guardrail.
- Added V0.5 amendment / supplemental request baseline for PR and TR increases.
- Added receipt and invoice policy setup.
- Added missing receipt accounting review item creation and closeout blocking.
- Added company card over-allocation protection and reviewed status workflow.
- Added duplicate card transaction review items.
- Expanded Accounting Review Queue filters and required-action visibility.
- Added basic finance reports for budget, reserve, spend, card, and review aging.
- Added production readiness documentation and `seed_finance_defaults`.
- Replaced invalid per diem policy ordering by `department__isnull` with an annotated department-specific rank.
- Kept department-specific travel per diem policies ahead of global policies.
- Moved travel actual expense finance-policy application into the correct actual-expense recording path.
- Updated actual review tests to use a non-requester reviewer.
- Updated normal closeout regression cases so they do not accidentally trigger the over-budget review path.

## Verification

Latest verification for the V1.2B Chinese UI Mode foundation:

```text
python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected.

python manage.py test dashboard.tests finance.tests --keepdb -v 1
Found 48 test(s).
Ran 48 tests in 87.548s
OK
```

V1.2A targeted verification:

```text
python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected.

python manage.py test finance.tests --keepdb -v 1
Found 35 test(s).
Ran 35 tests in 57.308s
OK
```

V1.1 Phase 3 setup and control verification:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test finance.tests.DuplicateActualExpenseReviewTest purchase.tests travel.tests --keepdb -v 1
Ran 138 tests
OK
```

Full regression:

```text
python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py test --keepdb -v 1
Found 281 test(s).
System check identified no issues (0 silenced).
Ran 281 tests in 683.732s
OK
```

Phase 3 UAT / accounting validation:

```text
Result: passed, reported by user. Detailed validation notes were not provided in the closeout request.
```

## Recommended Pre-Push Checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb -v 1
```

## Stabilization Gate

Before V0.5 feature development, V0.4 should pass business UAT:

- [V0.4 Business UAT Checklist](../uat/v0.4-business-uat.md)
- [V0.4 Demo Script](../uat/v0.4-demo-script.md)
- [V0.4 UAT Result Matrix](../uat/v0.4-result-matrix.md)
- [V0.4 Current Behavior And Limitations](../uat/v0.4-current-behavior-and-limitations.md)

## V0.5 Progress

V0.5 is implemented as a business-control milestone:

- PR/TR amendments use linked supplemental requests.
- Amendment budget reserve happens after amendment approval, not on submit.
- Detail pages show original amount, amendment delta, and revised amount.
- Original request closeout blocks while linked amendments are open.
- Receipt policy can create unresolved accounting review items.
- Company card allocation cannot exceed transaction amount.
- Accounting workbench and finance reports are available for UAT.

See [V0.5 Business Control Completion](v0.5-business-control-complete.md).

## V0.6 Progress

V0.6 multi-currency foundation is implemented at model/service/UI-documentation level:

- Company base currency is USD.
- Actual expense records preserve transaction currency and base currency snapshots.
- Exchange-rate-sensitive review data is snapshotted on accounting review items.
- Budget ledger remains base-currency controlled.
- Company card posted USD amount is the authoritative base amount when available.
- Finance Reports are base-currency reports.

See [V0.6 Multi-Currency Foundation](v0.6-multi-currency-foundation.md).

## V1.1 Roadmap Progress

The selected production-control roadmap has started. V1.1 Phase 1, Phase 2, and Phase 3 are completed and closed.

See [V1.1 Production Control Roadmap](v1.1-production-control-roadmap.md).

Phase 1 completion checkpoint:

- [V1.1 Phase 1 Completion Checkpoint](v1.1-phase1-completion.md)

Phase 1 technical design:

- [V1.1 Phase 1 Technical Design](v1.1-phase1-technical-design.md)

Phase 2 technical design:

- [V1.1 Phase 2 Technical Design](v1.1-phase2-technical-design.md)

Phase 2 implementation status:

- [V1.1 Phase 2 Implementation Status](v1.1-phase2-implementation.md)

Phase 2 completion checkpoint:

- [V1.1 Phase 2 Completion Checkpoint](v1.1-phase2-completion.md)

Phase 3 technical design:

- [V1.1 Phase 3 Technical Design](v1.1-phase3-technical-design.md)

Phase 3 completion checkpoint:

- [V1.1 Phase 3 Completion Checkpoint](v1.1-phase3-completion.md)

V1.2A completion note:

- [V1.2A Finance Report Drill-Down](v1.2a-finance-report-drilldown.md)

V1.2B completion note:

- [V1.2B Chinese UI Mode Foundation](v1.2b-chinese-ui-mode.md)

## Current Accepted Limitations

- Duplicate candidate links are runtime-computed from current records, not persisted immutable snapshots.
- There is no dedicated invoice number field yet; reference number remains the invoice/reference proxy.
- Duplicate detection creates review items but does not implement a duplicate `BLOCK` policy.
- Department General Budget does not yet include a PR/TR "general spend" flag or auto-default behavior.
- Attachment Retention supports void-with-reason and Attachment History, but not a full replacement workflow.
- Finance Report drill-down is link/detail based only; advanced reporting, Excel export, saved filters, and date/department/project report filters remain future work.
- Chinese UI Mode is a foundation and first translation batch only. Full PR/TR detail pages, most setup forms, many validation/messages in Python, and Django Admin are not fully translated yet.
