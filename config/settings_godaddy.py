from .settings import *

DEBUG = False

ALLOWED_HOSTS = [
    "4z8.d4d.mytemp.website",
    "132.148.219.49",
]

CSRF_TRUSTED_ORIGINS = [
    "https://4z8.d4d.mytemp.website",
]

FORCE_SCRIPT_NAME = "/oa-test"

STATIC_URL = "/oa-test/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/oa-test/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "/oa-test/accounts/login/"
LOGIN_REDIRECT_URL = "/oa-test/"
LOGOUT_REDIRECT_URL = "/oa-test/accounts/login/"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *[
        middleware
        for middleware in MIDDLEWARE
        if middleware != "django.middleware.security.SecurityMiddleware"
    ],
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}