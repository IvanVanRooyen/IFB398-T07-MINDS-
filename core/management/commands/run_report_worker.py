import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections

from core.ai.jobs import run_next

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Process durable report-generation jobs. Run a separate worker alongside the web service."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")
        parser.add_argument("--poll-interval", type=float, default=2)

    def handle(self, *args, **options):
        if options["poll_interval"] <= 0:
            raise CommandError("Poll interval must be positive.")
        try:
            while True:
                close_old_connections()
                try:
                    claimed = run_next()
                except DatabaseError:
                    if options["once"]:
                        raise
                    log.exception("Report worker is waiting for the database/schema")
                    time.sleep(max(options["poll_interval"], 5))
                    continue
                if claimed:
                    self.stdout.write(f"Processed report job {claimed[0]}")
                if options["once"]:
                    break
                if not claimed:
                    time.sleep(options["poll_interval"])
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped; expired running jobs can be retried.")
        finally:
            close_old_connections()
