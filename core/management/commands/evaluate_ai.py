import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.ai.evaluation import DATASET, run_evaluation


class Command(BaseCommand):
    help = "Evaluate synthetic retrieval/citation regressions; use --live only to call the configured AI provider."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default=str(DATASET))
        parser.add_argument("--output", help="Write the full JSON evidence artifact to this file.")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fail on citation regressions or ranked retrieval below the leading-excerpt baseline.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Call the configured AI provider using synthetic benchmark contexts; never downloads models.",
        )

    def handle(self, *args, **options):
        try:
            result = run_evaluation(options["dataset"], live=options["live"])
        except Exception as exc:
            raise CommandError(f"Evaluation failed: {exc}") from exc
        content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if options["output"]:
            Path(options["output"]).write_text(content)
            self.stdout.write(f"Evaluation written to {options['output']}")
        else:
            self.stdout.write(content)
        metrics = result["retrieval_metrics"]["all"]
        if options["check"] and (
            result["citation_cases_passed"] != result["citation_cases_total"]
            or result["retrieval_regressions"]
            or metrics["ranked_hit_rate"] < metrics["leading_hit_rate"]
        ):
            raise CommandError("Evaluation regression; inspect the per-case evidence.")
