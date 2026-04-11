import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # avoid re-calling the setup handler if we are the watcher (i.e. parent) process;
        # reloader only sets RUN_MAIN=true in child process
        if os.environ.get("RUN_MAIN") == "true":
            from core.telemetry import Telemetry

            Telemetry().setup()
