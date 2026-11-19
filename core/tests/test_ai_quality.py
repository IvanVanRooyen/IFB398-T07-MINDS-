"""Quality metrics, actual passage offsets, citation mechanics and scoped PostgreSQL ranking."""

import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.ai.citations import audit_citations
from core.ai.composition import compose_report, persist_composition
from core.ai.evaluation import DATASET, fixture_manifest, run_evaluation
from core.ai.passages import select_passage
from core.ai.retrieval import query_chunks
from core.models import DocumentChunk, Tenement
from core.tests import test_composition as composition_fixtures


class PassageTests(SimpleTestCase):
    def test_finds_later_evidence_with_exact_offsets(self):
        text = (
            "Vehicle servicing and payroll records. " * 120
            + " Copper assay returned 0.8% Cu over 12 m."
        )
        found = select_passage(text, "copper assay interval", 300)
        self.assertIn("0.8% Cu", found["text"])
        self.assertGreater(found["start"], 1000)
        self.assertEqual(
            text[found["start"] : found["end"]], found["text"].removesuffix(" [truncated]")
        )

    def test_ranked_window_fits_small_budget_without_cropping_away_match(self):
        text = "administrativebackground " * 60 + " copper assay evidence confirmed."
        found = select_passage(text, "copper assay", 90)
        self.assertIn("copper assay", found["text"])
        self.assertLessEqual(len(found["text"].encode()), 90)

    def test_no_match_is_an_explicit_leading_fallback(self):
        found = select_passage("Administrative records only.", "uranium", 100)
        self.assertEqual(found["method"], "leading_no_lexical_match")
        self.assertEqual(found["start"], 0)
        self.assertEqual(found["score"], 0)

    def test_unicode_boundaries_and_offsets(self):
        text = "背景 记录 " * 100 + "水样 含砷 检测结果 14 ppm。"
        found = select_passage(text, "含砷 水样", 100)
        self.assertLessEqual(len(found["text"].encode()), 100)
        self.assertIn("含砷", found["text"])
        self.assertEqual(
            text[found["start"] : found["end"]], found["text"].removesuffix(" [truncated]")
        )

    def test_ties_are_deterministic_and_empty_text_stays_empty(self):
        text = "Copper observations. " * 200
        self.assertEqual(select_passage(text, "copper", 300), select_passage(text, "copper", 300))
        self.assertEqual(select_passage("", "copper", 300)["method"], "no_text")


class CitationTests(SimpleTestCase):
    def manifest(self, **kwargs):
        return fixture_manifest(
            {
                "sources": [{"label": "D1", "text": "Copper assay returned 0.8% Cu over 12 m."}],
                **kwargs,
            }
        )

    def test_footer_cannot_credit_an_uncited_body(self):
        check = audit_citations(
            "Copper assay was recorded.\n\n## Sources\n\n- [D1] [Log](/documents/source-1/) — v1",
            self.manifest(),
        )
        self.assertEqual(check["cited_paragraph_count"], 0)
        self.assertEqual(check["status"], "issues_found")

    def test_source_definition_cannot_credit_an_uncited_body(self):
        check = audit_citations(
            "Copper assay was recorded.\n\n[D1]: /documents/source-1/", self.manifest()
        )
        self.assertEqual(check["cited_paragraph_count"], 0)
        self.assertEqual(len(check["uncited_paragraphs"]), 1)

    def test_fabricated_footer_and_definition_labels_are_detected(self):
        for tail in ["- [D9] [Fake](/documents/fake/) — v1", "[D9]: /documents/fake/"]:
            check = audit_citations("Known assay [D1].\n\n" + tail, self.manifest())
            self.assertEqual(check["unknown_labels"], ["D9"])

    def test_literal_quote_and_equivalent_decimal_format_are_supported(self):
        check = audit_citations(
            'The log states "0.8% Cu over 12 m" and the interval is 12.0 m [D1].', self.manifest()
        )
        self.assertEqual(check["status"], "no_structural_issues")
        self.assertEqual(check["unsupported_quantities"], [])
        self.assertEqual(check["quote_checks"][0]["status"], "matched_supplied_excerpt")

    def test_quote_outside_supplied_excerpt_is_flagged(self):
        check = audit_citations(
            'The log says "certified reserves are established" [D1].', self.manifest()
        )
        self.assertEqual(check["quote_checks"][0]["status"], "not_found_in_supplied_excerpt")

    def test_quantities_are_checked_against_cited_sources_not_other_sources(self):
        manifest = fixture_manifest(
            {
                "sources": [
                    {"label": "D1", "text": "Depth 12 m."},
                    {"label": "D2", "text": "Depth 90 m."},
                ]
            }
        )
        check = audit_citations("Depth is 90 m [D1].", manifest)
        self.assertEqual(check["unsupported_quantities"][0]["value"], "90")

    def test_wrong_link_destination_and_malformed_marker_are_reported(self):
        check = audit_citations("Assay [D1](https://example.invalid/other) [d1].", self.manifest())
        self.assertEqual(len(check["linked_citation_mismatches"]), 1)
        self.assertEqual(check["malformed_markers"], ["d1"])

    def test_uncited_list_items_are_separate_review_units(self):
        check = audit_citations("- Assay [D1].\n- A different finding.", self.manifest())
        self.assertEqual(check["cited_paragraph_count"], 1)
        self.assertEqual(len(check["uncited_paragraphs"]), 1)

    def test_code_markers_are_not_citations(self):
        check = audit_citations("Assay [D1].\n\n```text\n[D9]\n```", self.manifest())
        self.assertEqual(check["unknown_labels"], [])
        self.assertEqual(check["marker_count"], 1)

    def test_no_evidence_and_disabled_references_are_distinct(self):
        self.assertEqual(
            audit_citations("Overview.", self.manifest(sources=[]))["status"],
            "no_document_evidence",
        )
        self.assertEqual(
            audit_citations("Overview.", self.manifest(references_requested=False))["status"],
            "references_not_requested",
        )

    def test_missing_or_corrupt_generation_record_does_not_claim_success(self):
        for value in [
            {},
            None,
            {"schema_version": 2, "sources": "bad", "context": {}},
            {"schema_version": 2, "sources": [], "context": {"documents": [None]}, "options": {}},
        ]:
            self.assertEqual(audit_citations("Draft.", value)["status"], "unavailable")

    def test_literal_checks_do_not_detect_semantic_misrepresentation(self):
        # An intentionally preserved limit: the number exists, but Cu is misreported as gold.
        check = audit_citations("The gold assay returned 0.8% [D1].", self.manifest())
        self.assertEqual(check["status"], "no_structural_issues")
        self.assertIn("do not establish", check["limitation"])


class EvaluationTests(SimpleTestCase):
    def test_rank_regression_fails_recorded_partition_floor(self):
        data = json.loads(DATASET.read_text())
        data["retrieval_cases"][1]["query"] = "Where is auriferous mineralisation?"
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.json"
            output = Path(directory) / "regressed.json"
            dataset.write_text(json.dumps(data))
            with self.assertRaises(CommandError):
                call_command(
                    "evaluate_ai",
                    dataset=str(dataset),
                    output=str(output),
                    check=True,
                    stdout=io.StringIO(),
                )
            self.assertTrue(json.loads(output.read_text())["retrieval_regressions"])

    def test_offline_dataset_is_repeatable_and_exposes_challenge_failures(self):
        with patch("core.ai.granite_client.GraniteClient.complete") as live:
            first = run_evaluation()
            second = run_evaluation()
        live.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(first["citation_cases_passed"], first["citation_cases_total"])
        metrics = first["retrieval_metrics"]["all"]
        self.assertGreater(metrics["ranked_hit_rate"], metrics["leading_hit_rate"])
        self.assertLess(first["retrieval_metrics"]["challenge"]["ranked_hit_rate"], 1)
        self.assertFalse(first["live_provider_used"])

    def test_command_writes_inspectable_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evaluation.json"
            call_command("evaluate_ai", output=str(target), check=True, stdout=io.StringIO())
            data = json.loads(target.read_text())
        self.assertEqual(data["dataset_version"], "quality-v1")
        self.assertEqual(len(data["dataset_sha256"]), 64)

    def test_regression_exits_nonzero_and_keeps_failed_artifact(self):
        data = json.loads(DATASET.read_text())
        data["citation_cases"][0]["expected"]["status"] = "an_intentional_mismatch"
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.json"
            dataset.write_text(json.dumps(data))
            output = Path(directory) / "failed.json"
            with self.assertRaises(CommandError):
                call_command(
                    "evaluate_ai",
                    dataset=str(dataset),
                    output=str(output),
                    check=True,
                    stdout=io.StringIO(),
                )
            self.assertFalse(json.loads(output.read_text())["citation_cases"][0]["passed"])

    def test_live_mode_is_explicit_and_keeps_semantic_review_unperformed(self):
        with patch(
            "core.ai.granite_client.GraniteClient.complete",
            return_value="Evidence is insufficient [D1].",
        ) as live:
            result = run_evaluation(live=True)
        self.assertEqual(live.call_count, 2)
        self.assertTrue(result["live_provider_used"])
        self.assertTrue(
            all(row["semantic_review"] == "not_performed" for row in result["live_generation_runs"])
        )


class RankedIntegrationTests(TestCase):
    def test_chunk_with_cross_organisation_tenement_is_excluded(self):
        tenement = Tenement.objects.create(
            name="Foreign tenement",
            organisation=self.fixture.other_org,
            process=self.fixture.foreign,
        )
        self.doc.tenement = tenement
        self.doc.save()
        DocumentChunk.objects.create(
            document=self.doc, process=self.process, chunk_index=0, text="Copper evidence"
        )
        self.assertEqual(
            query_chunks("copper", process=self.process, clearance_level="CONFIDENTIAL"), []
        )

    def setUp(self):
        # Reuse only fixture construction helpers; do not inherit the old test cases.
        self.fixture = composition_fixtures.CompositionTests(methodName="runTest")
        self.fixture.client = self.client
        self.fixture.setUp()
        self.user, self.doc, self.process = (
            self.fixture.user,
            self.fixture.doc,
            self.fixture.process,
        )

    def test_legacy_chunks_rank_broad_matches_before_single_keyword_matches(self):
        weak = DocumentChunk.objects.create(
            document=self.doc, process=self.process, chunk_index=0, text="Copper inventory."
        )
        strong = DocumentChunk.objects.create(
            document=self.doc,
            process=self.process,
            chunk_index=1,
            text="Copper fault quartz samples were mapped.",
        )
        rows = query_chunks(
            "copper fault quartz samples", process=self.process, clearance_level="CONFIDENTIAL"
        )
        self.assertEqual(rows[0].pk, strong.pk)
        self.assertIn(weak, rows)

    def test_chunk_scope_and_metadata_use_current_parent_values(self):
        DocumentChunk.objects.create(
            document=self.doc,
            process=self.process,
            chunk_index=0,
            text="Copper assay evidence.",
            doc_type="old",
            timestamp=date(1970, 1, 1),
        )
        self.doc.doc_type = "new"
        self.doc.timestamp = date(2026, 1, 1)
        self.doc.save()
        self.assertEqual(
            len(
                query_chunks(
                    "copper",
                    process=self.process,
                    date_from=date(2025, 1, 1),
                    clearance_level="CONFIDENTIAL",
                )
            ),
            1,
        )
        self.assertEqual(
            query_chunks(
                "copper",
                process=self.process,
                date_to=date(2025, 1, 1),
                clearance_level="CONFIDENTIAL",
            ),
            [],
        )
        self.assertEqual(
            len(
                query_chunks(
                    "copper", process=self.process, doc_type="new", clearance_level="CONFIDENTIAL"
                )
            ),
            1,
        )
        self.assertEqual(
            query_chunks(
                "copper", process=self.process, doc_type="old", clearance_level="CONFIDENTIAL"
            ),
            [],
        )
        self.assertEqual(query_chunks("copper", process=self.process, document_ids=[]), [])
        self.assertEqual(
            query_chunks("copper", process=self.process, document_ids=[self.fixture.unselected.pk]),
            [],
        )
        self.assertEqual(query_chunks("copper", process=self.fixture.foreign), [])
        self.assertEqual(
            query_chunks("copper", process=self.process, clearance_level="INVALID"), []
        )

    def test_composition_retrieves_late_evidence_and_retains_offsets(self):
        self.doc.extracted_text = (
            "Travel and payroll records. " * 150 + " Copper assay returned 0.8% Cu over 12 m."
        )
        self.doc.save()
        with patch(
            "core.ai.composition.GraniteClient.complete",
            return_value="Copper assay returned 0.8% over 12 m [D1].",
        ):
            bundle = compose_report(self.fixture.form(instructions="Focus on copper assay"))
        record = bundle["manifest"]["sources"][0]
        self.assertGreater(record["passage"]["start"], 500)
        self.assertIn("0.8%", bundle["manifest"]["context"]["documents"][0]["excerpt"])
        self.assertEqual(
            bundle["manifest"]["generation_citation_check"]["status"], "no_structural_issues"
        )
        self.assertEqual(bundle["doc_ids"], [str(self.doc.pk)])

    def test_current_saved_report_check_refreshes_after_manual_edit(self):
        with patch(
            "core.ai.composition.GraniteClient.complete", return_value="Copper observations [D1]."
        ):
            bundle = compose_report(self.fixture.form())
        report = persist_composition(self.user, self.process, bundle, "Checked draft")
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("update_saved_report", args=[report.pk]),
            {"title": report.title, "content_md": "Invented measurement 99 ppm [D99]."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citation_check"]["unknown_labels"], ["D99"])
        self.assertEqual(
            report.generation_manifest["generation_citation_check"]["unknown_labels"], []
        )
        current = self.client.get(response.json()["redirect_url"])
        self.assertContains(current, "Citation check for saved text")
        self.assertContains(current, "Unknown source labels: D99.")
