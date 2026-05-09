# GoDaddy cPanel Git Version Control Deployment Guide

## 0. Important Compatibility Check

Your current GoDaddy Python App screenshot shows:

```text
Python version: 3.11.14
Application root: a8_oa
Application URL: 4z8.d4d.mytemp.website/oa-test
Startup file: passenger_wsgi.py
Entry point: application
Home directory: /home/rsnwvvl103hc
App root: /home/rsnwvvl103hc/a8_oa
```

The current project uses:

```text
Django==6.0.3
```

Django 6.0 requires Python 3.12, 3.13, or 3.14. Python 3.11 is not supported by Django 6.0.

Before deployment, choose one:

1. Preferred: create or switch the GoDaddy Python App to Python 3.12+ if GoDaddy supports it.
2. Alternative: downgrade the project to Django 5.2 LTS, then run local regression tests before deploying.

Do not ignore this. If the server remains on Python 3.11, `pip install -r requirements.txt` may fail or the app may not start.

## 1. Recommended Directory Layout

Keep the Git repository and running Python app folder separate.

Recommended:

```text
/home/rsnwvvl103hc/repositories/a8_oa     # cPanel Git clone
/home/rsnwvvl103hc/a8_oa                  # Python App runtime folder
```

Why separate them:

- The Git repository stays clean.
- Runtime files such as `.env`, `db.sqlite3`, `media`, logs, and temporary files are not deleted.
- Deployment can copy only version-controlled code into the app root.
- You no longer need to delete files and upload zip packages.

## 2. Files Added To This Project

The project now includes:

```text
.cpanel.yml
requirements.txt
.env.example
config/settings_godaddy.py
deployment/passenger_wsgi.py.example
deployment/godaddy-git-version-control-guide.md
```

### `.cpanel.yml`

cPanel uses this file when you click Deploy HEAD Commit.

Current deployment target:

```text
/home/rsnwvvl103hc/a8_oa
```

It excludes runtime-only files:

```text
.git
.venv
.env
db.sqlite3
media
sent_emails
passenger.log
tmp
```

### `requirements.txt`

This is used by GoDaddy Run Pip Install or by `.cpanel.yml`.

Current contents:

```text
Django==6.0.3
tzdata==2025.3
```

### `config/settings_godaddy.py`

This keeps GoDaddy-specific settings separate from local development settings.

It contains:

```text
ALLOWED_HOSTS for 4z8.d4d.mytemp.website
CSRF_TRUSTED_ORIGINS
FORCE_SCRIPT_NAME = "/oa-test"
STATIC_URL = "/oa-test/static/"
WhiteNoise static file middleware
DEBUG = False
```

### `.env.example`

This is a reference file. Do not put real secrets in Git.

Current `config/settings.py` does not fully read `.env` yet. Treat this as deployment documentation until production settings are added.

### `passenger_wsgi.py.example`

Use this as the reference startup file for cPanel Python App.

The real file on GoDaddy should be:

```text
/home/rsnwvvl103hc/a8_oa/passenger_wsgi.py
```

## 3. Create Repository In GoDaddy Git Version Control

Open cPanel:

```text
cPanel -> Files -> Git Version Control
```

You are on the Create Repository screen.

Use these values:

### Clone a Repository

Keep this enabled.

### Clone URL

Use your GitHub repository clone URL.

If the GitHub repo is public:

```text
https://github.com/zlw1987/a8_oa.git
```

If the GitHub repo is private, use SSH instead:

```text
git@github.com:zlw1987/a8_oa.git
```

Private repo requires SSH key setup first.

### Repository Path

Use:

```text
/home/rsnwvvl103hc/repositories/a8_oa
```

If the UI already shows `/home/rsnwvvl103hc/` as the prefix, type only:

```text
repositories/a8_oa
```

Do not use:

```text
a8_oa
```

That is your Python App runtime directory.

### Repository Name

Use:

```text
a8_oa_github
```

Then click:

```text
Create
```

## 4. Deploy From cPanel

After the repository is created:

1. Go back to Git Version Control repository list.
2. Find `a8_oa_github`.
3. Click `Manage`.
4. Confirm the checked-out branch is `master`.
5. Click `Update from Remote`.
6. Click `Deploy HEAD Commit`.

cPanel will read:

```text
.cpanel.yml
```

and copy files into:

```text
/home/rsnwvvl103hc/a8_oa
```

## 5. Verify Python Path In `.cpanel.yml`

The generated `.cpanel.yml` contains:

```text
export PYTHON=/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python
```

This path may differ on GoDaddy.

To confirm it:

1. Open cPanel Terminal if available.
2. Run:

```bash
ls -la /home/rsnwvvl103hc/virtualenv/a8_oa
find /home/rsnwvvl103hc/virtualenv -path '*bin/python' -type f
```

If the path is different, edit `.cpanel.yml` in Git and push the correction.

If you switch the Python App to 3.12+, the path may become something like:

```text
/home/rsnwvvl103hc/virtualenv/a8_oa/3.12/bin/python
```

## 6. Passenger Startup File

Your cPanel Python App screen shows:

```text
Application startup file: passenger_wsgi.py
Application Entry point: application
```

Make sure the deployed app root contains:

```text
/home/rsnwvvl103hc/a8_oa/passenger_wsgi.py
```

Use this content:

```python
import os
import sys

PROJECT_ROOT = "/home/rsnwvvl103hc/a8_oa"

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
```

The repo includes this as:

```text
deployment/passenger_wsgi.py.example
```

Copy it to:

```text
passenger_wsgi.py
```

inside the GoDaddy app root if needed.

## 7. Static Files

The project now has:

```text
static/css/app.css
staticfiles/
```

`.cpanel.yml` runs:

```bash
python manage.py collectstatic --noinput
```

The Django settings include:

```python
STATIC_ROOT = BASE_DIR / "staticfiles"
```

For the current testing setup, Django may still serve static files in DEBUG mode. For production-like testing, configure static files properly.

## 8. Database Notes

Current local project uses SQLite:

```text
db.sqlite3
```

`.cpanel.yml` intentionally excludes `db.sqlite3` so deployment will not overwrite the server database.

For testing, SQLite may be acceptable.

For real multi-user testing, consider GoDaddy MySQL because SQLite can have concurrency and file-locking limitations on shared hosting.

## 9. Normal Deployment Workflow After Setup

After Git Version Control is configured, your normal workflow becomes:

```text
Local development
-> git add / commit
-> git push GitHub
-> GoDaddy cPanel Git Version Control
-> Update from Remote
-> Deploy HEAD Commit
-> Open the app URL and test
```

You no longer need to:

- Delete all GoDaddy files.
- Upload a zip.
- Extract manually.

## 10. If Requirements Change

If `requirements.txt` changes:

1. Push to GitHub.
2. In GoDaddy Git Version Control, update and deploy.
3. Or in Python App page, click `Run Pip Install`.

The `.cpanel.yml` already runs:

```bash
python -m pip install -r requirements.txt
```

## 11. If Migrations Change

The `.cpanel.yml` already runs:

```bash
python manage.py migrate
```

If migration fails, check:

```text
/home/rsnwvvl103hc/a8_oa/passenger.log
```

or cPanel deployment output.

## 12. Restarting The Python App

The deployment creates:

```text
/home/rsnwvvl103hc/a8_oa/tmp/restart.txt
```

Passenger watches this file and restarts the app when it changes.

You can also restart from the cPanel Python App screen if needed.

## 13. Troubleshooting

### Problem: Deploy fails on pip install

Most likely cause:

- Python version mismatch.
- Django 6.0 on Python 3.11.

Fix:

- Use Python 3.12+ in cPanel, or downgrade Django after local testing.

### Problem: Git clone fails

If repo is private:

- Set up SSH access in cPanel.
- Add cPanel public SSH key to GitHub deploy keys.
- Use SSH clone URL.

If repo is public:

- Use HTTPS clone URL.

### Problem: App shows 500 error

Check:

```text
/home/rsnwvvl103hc/a8_oa/passenger.log
```

Common causes:

- Wrong Python version.
- Missing dependency.
- Wrong `passenger_wsgi.py`.
- Migration failure.
- Static file setting issue.
- `ALLOWED_HOSTS` does not include `4z8.d4d.mytemp.website`.

### Problem: Static CSS not loading

Check:

- `static/css/app.css` exists in app root.
- `STATIC_URL = 'static/'`.
- If `DEBUG=False`, configure `STATIC_ROOT` and static file serving.

### Problem: Deployment deletes uploaded files

The generated `.cpanel.yml` excludes:

```text
media
```

so uploaded files should not be deleted.

Do not remove this exclude.

## 14. Recommended Next Improvement

For safer GoDaddy testing, add a production/testing settings layer later:

```text
config/settings_base.py
config/settings_local.py
config/settings_godaddy.py
```

This would allow:

- Separate `DEBUG`.
- Separate `ALLOWED_HOSTS`.
- Separate database config.
- Server-only secret key.
- Safer static/media configuration.
