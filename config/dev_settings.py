"""Local-only profile; private filesystem storage and optional model access."""

import os

os.environ.setdefault("DOCUMENT_STORAGE", "filesystem")

from .settings import *  # noqa: E402,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
CSRF_TRUSTED_ORIGINS = []
ALLOW_DEMO_SEED = True
