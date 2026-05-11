# Current Version

## Status

The current version includes V0.5 business-control completion on top of the V0.4 finance controls milestone.

## Latest Fixes

- Cleaned up Accounting Review Queue filters with visible labels, Basic/Advanced sections, tab counts, preserved-tab reset behavior, and clearer empty states.
- Moved Approval Rules `Create Rule` out of the Filters panel into a page-level primary action area.
- Added a reusable `money` template filter and updated Finance Reports to show currency code, thousand separators, and two decimal places.
- Updated Finance Reports to group top financial totals by currency instead of silently combining mixed currencies.
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

Latest full-suite verification:

```text
python manage.py test --keepdb -v 1
Ran 228 tests in 687.798s
OK
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
