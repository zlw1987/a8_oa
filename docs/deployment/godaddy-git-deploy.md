# GoDaddy cPanel Git Deployment Notes

## Current Deployment Target

- cPanel user: `rsnwvvl103hc`
- App root: `/home/rsnwvvl103hc/a8_oa`
- Django settings: `config.settings_godaddy`
- Passenger restart file: `/home/rsnwvvl103hc/a8_oa/tmp/restart.txt`

## Expected Deployment Flow

cPanel Git Version Control should run `.cpanel.yml`, which calls:

```bash
/bin/bash deploy/godaddy_deploy.sh
```

The deploy script should:

1. Resolve the Python executable from the cPanel virtualenv.
2. Copy files to the app root when the repository path is different from app root.
3. Install requirements.
4. Run Django check.
5. Run migrations.
6. Run collectstatic.
7. Restart Passenger.

## Why Manual Migrate Was Still Needed

The previous script had several likely failure points:

1. It wrote to `deploy.log` before ensuring `/home/rsnwvvl103hc/a8_oa` existed.
2. The Python path used `python3.11_bin`, which is not the usual cPanel virtualenv executable name.
3. If the cPanel repository path and app root are both `/home/rsnwvvl103hc/a8_oa`, the script tried to `rsync` the app folder into itself.
4. If any of the above stopped the script before `manage.py migrate`, the deployed code could run against an old database schema and return HTTP 500.

## Current Script Hardening

`deploy/godaddy_deploy.sh` now:

- Uses `set -euo pipefail`.
- Creates the deploy directory before logging.
- Tries common cPanel Python executable paths:
  - `/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python`
  - `/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python3.11`
  - `/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python3`
- Skips `rsync` when repo path equals deploy path.
- Runs:

```bash
python manage.py migrate --settings=config.settings_godaddy --noinput
```

## What To Check In cPanel

After clicking Deploy HEAD Commit, open:

```text
/home/rsnwvvl103hc/a8_oa/deploy.log
```

Confirm these lines appear:

```text
Django check...
Run migrate...
Run collectstatic...
Restart Passenger...
DEPLOY DONE
```

If `Run migrate...` does not appear, cPanel did not complete the deployment script.

## Common cPanel Gotchas

- `.cpanel.yml` must be committed to the repository root.
- The deployment branch in cPanel must match the branch you deploy.
- If cPanel Git repository path is different from app root, `rsync` copies files into app root.
- If repository path is the app root, the script skips `rsync` and runs commands in place.
- The Python virtualenv path must match the Python App configured in cPanel.
- Passenger may keep stale code until `tmp/restart.txt` is touched.

## Manual Fallback

If automatic migration fails, run:

```bash
cd /home/rsnwvvl103hc/a8_oa
/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python manage.py migrate --settings=config.settings_godaddy --noinput
/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python manage.py collectstatic --settings=config.settings_godaddy --noinput
touch /home/rsnwvvl103hc/a8_oa/tmp/restart.txt
```

Use the actual Python executable path shown in `deploy.log`.
