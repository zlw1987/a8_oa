# Production Readiness Checklist

## Permissions

- Review staff-only finance setup access.
- Confirm accounting users can access accounting review queue, card transactions, and finance reports.
- Confirm requesters cannot approve or resolve their own accounting review items.
- Confirm approvers have the correct department or global approval permissions.

## Seed Data

- Run `python manage.py seed_finance_defaults`.
- Create or verify default departments.
- Create or verify default approval rules for PR, TR, and amendments.
- Create test users for requester, manager, finance, accounting, and admin.

## Finance Policy Setup

- Confirm over-budget thresholds.
- Confirm AMENDMENT_REQUIRED thresholds.
- Confirm BLOCK threshold.
- Confirm receipt optional / required / invoice required thresholds.
- Confirm company card receipt requirement.

## UAT Data

- Prepare one normal PR.
- Prepare one normal TR with per diem.
- Prepare warning, review, amendment-required, and block actual expense cases.
- Prepare one one-to-one card allocation.
- Prepare one split card allocation.
- Prepare one duplicate card transaction candidate.

## Deployment

- Apply migrations.
- Run `python manage.py check`.
- Run automated tests.
- Run seed command in the target environment.
- Verify static files and media storage.
- Verify database backup before cutover.
- Verify restore procedure on a non-production database.

## Operations

- Review accounting queue daily.
- Review unmatched card transaction report daily.
- Review accounting review aging weekly.
- Review over-budget exception report weekly.
- Archive or resolve stale review items before period close.

## Training Notes

- Requesters should not edit approved requests directly for budget increases.
- Use amendment / supplemental request for approved amount increases.
- Missing receipt items block closeout until accounting resolves them.
- Duplicate card transaction warnings require human confirmation.
- Company card allocations can be split but cannot exceed the transaction total.
