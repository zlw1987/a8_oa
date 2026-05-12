# A8 OA Documentation

This folder contains project documentation for A8 OA.

## Documents

- [Version Index](versions/README.md)
- [Current Version](versions/current.md)
- [V1.1 Phase 2 Implementation Status](versions/v1.1-phase2-implementation.md)
- [用户使用手册 中文](user-guide-zh.md)
- [User Guide English](user-guide-en.md)
- [UI Productization Status](ui-productization-status.md)
- [Pilot Hardening Business-Control Gap Review](pilot-hardening-gap-review.md)
- [Pilot Hardening Priority Matrix](pilot-hardening-priority-matrix.md)
- [V0.4 Business UAT Checklist](uat/v0.4-business-uat.md)
- [V0.4 Demo Script](uat/v0.4-demo-script.md)
- [V0.4 UAT Result Matrix](uat/v0.4-result-matrix.md)
- [V0.4 Current Behavior And Limitations](uat/v0.4-current-behavior-and-limitations.md)
- [V0.5 Proposed Technical Design](versions/v0.5-proposed-technical-design.md)
- [V0.5 Business Control Completion](versions/v0.5-business-control-complete.md)
- [Production Readiness Checklist](production-readiness.md)
- [V0.1 Foundation](versions/v0.1-foundation.md)
- [V0.2 Purchase, Travel, And Approval](versions/v0.2-purchase-travel-approval.md)
- [V0.3 Budget And Project Ledger](versions/v0.3-budget-project-ledger.md)
- [V0.4 Finance Controls](versions/v0.4-finance-controls.md)

## Development Notes

The project is a modular Django app. Business workflows are kept close to their owning apps, while reusable cross-request logic lives in shared modules:

- Approval routing and task permissions live under `approvals`.
- Budget ledger models and helpers live under `projects`.
- Cross-request financial controls live under `finance`.
- Request-specific lifecycle rules remain in `purchase` and `travel`.

Before pushing a change, run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb -v 1
```
