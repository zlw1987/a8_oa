# A8 OA

A8 OA is a Django-based internal office automation system for request, approval, budget, travel, purchase, and finance-control workflows.

## What Is Included

- User, department, role, and access control foundations.
- Purchase request lifecycle with line items, approval tasks, budget reservation, actual spend, and closeout.
- Travel request lifecycle with itinerary, estimated expenses, per diem calculation, approval tasks, actual expenses, and closeout.
- Unified approval workbench for assigned tasks, pool tasks, history, due state, reminders, and escalation.
- Project budget ledger that combines purchase and travel reservations, releases, and actual consumption.
- Finance controls for over-budget policies, accounting review items, company card transactions, and allocation matching.

## Tech Stack

- Python 3.14
- Django 6.0
- SQLite for local development
- Django template UI
- Django test runner

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install django
python manage.py migrate
python manage.py runserver
```

The development app runs at `http://127.0.0.1:8000/`.

## Useful Commands

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb -v 1
```

## Main Modules

- `accounts`: users, departments, and department-user responsibility links.
- `approvals`: reusable approval rules, approval tasks, task pools, claiming, releasing, reminders, and history.
- `purchase`: purchase requests, lines, attachments, actual spending, and purchase closeout.
- `travel`: travel requests, itinerary, estimated expenses, per diem, actual expenses, and travel closeout.
- `projects`: project master data and budget ledger entries.
- `finance`: over-budget policies, accounting review queue, company card transactions, and allocations.
- `dashboard`: cross-request dashboard views.

## Documentation

Project documentation lives in [docs/README.md](docs/README.md).

Version notes live in [docs/versions/README.md](docs/versions/README.md).

