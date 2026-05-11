import os
import sys

PROJECT_DIR = "/home/rsnwvvl103hc/a8_oa"

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_godaddy")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()