"""Disposable PostGIS/Redis tests with isolated file storage and no dotenv reads."""

import atexit
import os
import shutil
import tempfile

# Test configuration never reads a developer's .env or requires an object store.
os.environ["DJANGO_READ_ENV"] = "0"
os.environ["DOCUMENT_STORAGE"] = "filesystem"
os.environ["GRANITE_BACKEND"] = "ollama"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:1"
os.environ["GRANITE_TIMEOUT"] = "1"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
for name, value in {
    "SECRET_KEY": "test-only-not-a-deployment-secret",
    "DB_NAME": "minds_dev",
    "DB_USER": "minds",
    "DB_PASS": "local-tests-only",
    "DB_HOST": "db",
    "DB_PORT": "5432",
    "GF_PG_READER_USER": "minds_grafana",
    "GF_PG_READER_PASS": "local-reader-only",
}.items():
    os.environ.setdefault(name, value)

from .settings import *  # noqa: E402,F403

DEBUG = False
ALLOW_DEMO_SEED = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
DATABASES["default"]["TEST"] = {"NAME": os.environ.get("TEST_DB_NAME", "test_minds")}  # noqa: F405
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("TEST_REDIS_URL", "redis://redis:6379/1"),
        "KEY_PREFIX": "minds-tests",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = tempfile.mkdtemp(prefix="minds-tests-")
TEST_MEDIA_ROOT = MEDIA_ROOT
atexit.register(shutil.rmtree, MEDIA_ROOT, ignore_errors=True)
