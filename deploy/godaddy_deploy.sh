#!/bin/bash
set -euo pipefail

DEPLOYPATH=/home/rsnwvvl103hc/a8_oa
PYTHON=/home/rsnwvvl103hc/virtualenv/a8_oa/3.11/bin/python3.11_bin
LOGFILE=$DEPLOYPATH/deploy.log

echo "===== DEPLOY START $(date) =====" | tee $LOGFILE
echo "Current repo path: $(pwd)" | tee -a $LOGFILE
echo "Deploy path: $DEPLOYPATH" | tee -a $LOGFILE
echo "Python executable: $PYTHON" | tee -a $LOGFILE

mkdir -p $DEPLOYPATH

echo "Rsync files..." | tee -a $LOGFILE
/bin/rsync -av --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='db.sqlite3' \
  --exclude='media/' \
  --exclude='staticfiles/' \
  --exclude='sent_emails/' \
  --exclude='passenger.log' \
  --exclude='deploy.log' \
  --exclude='tmp/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  ./ $DEPLOYPATH/ 2>&1 | tee -a $LOGFILE

cd $DEPLOYPATH

echo "Python version..." | tee -a $LOGFILE
$PYTHON --version 2>&1 | tee -a $LOGFILE

echo "Django check..." | tee -a $LOGFILE
$PYTHON manage.py check --settings=config.settings_godaddy 2>&1 | tee -a $LOGFILE

echo "Show migrations..." | tee -a $LOGFILE
$PYTHON manage.py showmigrations --settings=config.settings_godaddy 2>&1 | tee -a $LOGFILE

echo "Run migrate..." | tee -a $LOGFILE
$PYTHON manage.py migrate --settings=config.settings_godaddy --noinput 2>&1 | tee -a $LOGFILE

echo "Run collectstatic..." | tee -a $LOGFILE
$PYTHON manage.py collectstatic --settings=config.settings_godaddy --noinput 2>&1 | tee -a $LOGFILE

echo "Restart Passenger..." | tee -a $LOGFILE
mkdir -p $DEPLOYPATH/tmp
touch $DEPLOYPATH/tmp/restart.txt

echo "===== DEPLOY DONE $(date) =====" | tee -a $LOGFILE