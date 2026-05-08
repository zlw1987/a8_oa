# Current Version

## Status

The current version includes the V0.4 finance controls milestone and the latest regression fixes.

## Latest Fixes

- Replaced invalid per diem policy ordering by `department__isnull` with an annotated department-specific rank.
- Kept department-specific travel per diem policies ahead of global policies.
- Moved travel actual expense finance-policy application into the correct actual-expense recording path.
- Updated actual review tests to use a non-requester reviewer.
- Updated normal closeout regression cases so they do not accidentally trigger the over-budget review path.

## Verification

Latest full-suite verification:

```text
python manage.py test --keepdb -v 1
Ran 221 tests in 568.710s
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

