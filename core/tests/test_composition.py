"""Real authorization, context selection, generation persistence and form contracts."""

import hashlib
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.ai.composition import (
    MAX_PROMPT_BYTES,
    ReportCompositionForm,
    compose_report,
    persist_composition,
)
from core.ai.jobs import run_next
from core.models import (
    DocLink,
    Document,
    Drillhole,
    Organisation,
    Process,
    Prospect,
    ReportGenerationJob,
    SavedReport,
)


class CompositionTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Composition")
        self.other_org = Organisation.objects.create(name="Other")
        self.process = Process.objects.create(name="Copper project", organisation=self.org)
        self.other_project = Process.objects.create(
            name="Other local project", organisation=self.org
        )
        self.foreign = Process.objects.create(name="Foreign project", organisation=self.other_org)
        self.user = User.objects.create_user("composer", password="test-only")
        self.user.profile.organisation = self.org
        self.user.profile.role = "GEOLOGIST_EXPL"
        self.user.profile.clearance_level = "CONFIDENTIAL"
        self.user.profile.save()
        self.doc = self.document("Selected evidence", "SELECTED_EVIDENCE copper observations")
        self.unselected = self.document("Unselected evidence", "UNSELECTED_SECRET copper results")
        self.prospect = Prospect.objects.create(
            name="Copper target",
            process=self.process,
            organisation=self.org,
            geom=Point(153, -27, srid=4326),
            hypothesis="HYPOTHESIS copper near fault",
            objective="OBJECTIVE sample fault zone",
        )
        DocLink.objects.create(
            document=self.doc,
            content_type=ContentType.objects.get_for_model(Prospect),
            object_id=self.prospect.pk,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def document(self, title, text, **kwargs):
        values = dict(
            process=self.process,
            organisation=self.org,
            confidentiality="internal",
            title=title,
            extracted_text=text,
            checksum_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        values.update(kwargs)
        return Document.objects.create(**values)

    def payload(self, **kwargs):
        data = {
            "composer_version": "1",
            "process_id": str(self.process.pk),
            "report_title": "Evidence report",
            "report_type": "risk",
            "tone": "technical",
            "instructions": "Focus on uncertainty",
            "source_mode": "selected",
            "document_ids": [str(self.doc.pk)],
            "include_findings": "on",
            "include_references": "on",
        }
        data.update(kwargs)
        return data

    def form(self, **kwargs):
        form = ReportCompositionForm(self.payload(**kwargs), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def generate(self, form=None):
        with patch("core.ai.composition.GraniteClient.complete", return_value="# Draft") as call:
            result = compose_report(form or self.form())
        return result, call.call_args.args[0]

    def test_selected_files_are_the_entire_document_scope_and_manifest(self):
        result, prompt = self.generate()
        self.assertIn("SELECTED_EVIDENCE", prompt)
        self.assertNotIn("UNSELECTED_SECRET", prompt)
        self.assertEqual(result["doc_ids"], [str(self.doc.pk)])
        self.assertEqual(result["manifest"]["sources"][0]["id"], str(self.doc.pk))
        self.assertEqual(
            result["manifest"]["prompt_sha256"], hashlib.sha256(prompt.encode()).hexdigest()
        )
        self.assertEqual(result["manifest"]["prompt"], prompt)
        self.assertLessEqual(len(prompt.encode()), MAX_PROMPT_BYTES)

    def test_type_tone_instructions_and_each_layout_option_affect_input(self):
        result, prompt = self.generate(
            self.form(include_metadata="on", include_recommendations="on")
        )
        self.assertIn("Risk / Findings Summary", prompt)
        self.assertIn("Tone: Technical", prompt)
        self.assertIn("Focus on uncertainty", prompt)
        self.assertIn("Key findings", prompt)
        self.assertIn("Recommendations", prompt)
        self.assertIn("Document metadata", prompt)
        self.assertIn("Use [D1]", prompt)
        self.assertIn("## Sources", result["md"])
        result, prompt = self.generate(
            self.form(
                report_type="project_update",
                tone="executive",
                include_findings="",
                include_metadata="",
                include_recommendations="",
                include_references="",
            )
        )
        self.assertIn("Progress and milestones", prompt)
        self.assertIn("Tone: Executive Summary", prompt)
        self.assertNotIn("Key findings", prompt)
        self.assertNotIn("## Sources", result["md"])
        self.assertEqual(result["doc_ids"], [str(self.doc.pk)])

    def test_every_type_has_a_distinct_outline(self):
        prompts = []
        for kind in ["exploration", "project_update", "documents", "tenement", "risk", "custom"]:
            _, prompt = self.generate(self.form(report_type=kind))
            prompts.append(prompt)
        self.assertEqual(len(set(prompts)), 6)

    def test_selected_source_scope_rejects_foreign_hidden_old_and_wrong_project_files(self):
        docs = [
            self.document("Foreign", "FOREIGN", process=self.foreign, organisation=self.other_org),
            self.document("Hidden", "HIDDEN", confidentiality="jorc_restricted"),
            self.document("Old", "OLD", is_latest=False),
            self.document("Other project", "OTHER", process=self.other_project),
        ]
        for doc in docs:
            form = ReportCompositionForm(self.payload(document_ids=[str(doc.pk)]), user=self.user)
            self.assertFalse(form.is_valid())
        for process_id in [str(self.foreign.pk), "bad-uuid"]:
            form = ReportCompositionForm(self.payload(process_id=process_id), user=self.user)
            self.assertFalse(form.is_valid())

    def test_invalid_options_empty_or_excessive_selection_never_calls_model(self):
        for changes in [
            {"report_type": "invented"},
            {"tone": "invented"},
            {"source_mode": "invented"},
            {"document_ids": []},
            {"instructions": "x" * 1001},
            {"source_mode": "project", "document_ids": [str(self.doc.pk)]},
        ]:
            with patch("core.ai.composition.GraniteClient.complete") as call:
                response = self.client.post(reverse("generate_report"), self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                call.assert_not_called()
        docs = [self.doc] + [self.document(f"Doc {i}", f"Data {i}") for i in range(10)]
        response = self.client.post(
            reverse("generate_report"), self.payload(document_ids=[str(d.pk) for d in docs])
        )
        self.assertEqual(response.status_code, 400)

    def test_project_mode_is_limited_and_records_actual_subset(self):
        for i in range(12):
            self.document(f"Latest {i}", f"Text {i}")
        result, _ = self.generate(self.form(source_mode="project", document_ids=[]))
        self.assertEqual(len(result["doc_ids"]), 10)
        self.assertEqual(result["manifest"]["eligible_document_count"], 14)

    def test_prospect_uses_linked_evidence_hypothesis_objective_and_drillholes(self):
        Drillhole.objects.create(
            name="LINKED_HOLE",
            process=self.process,
            organisation=self.org,
            prospect=self.prospect,
            depth=80,
        )
        Drillhole.objects.create(
            name="UNRELATED_HOLE", process=self.process, organisation=self.org, depth=90
        )
        form = ReportCompositionForm({}, user=self.user, prospect=self.prospect)
        self.assertTrue(form.is_valid(), form.errors)
        result, prompt = self.generate(form)
        for value in ["HYPOTHESIS", "OBJECTIVE", "LINKED_HOLE", "SELECTED_EVIDENCE"]:
            self.assertIn(value, prompt)
        for value in ["UNRELATED_HOLE", "UNSELECTED_SECRET"]:
            self.assertNotIn(value, prompt)
        self.assertEqual(result["manifest"]["scope"], "prospect")
        self.assertEqual(result["doc_ids"], [str(self.doc.pk)])

    def test_prospect_cannot_explicitly_select_unlinked_project_file(self):
        form = ReportCompositionForm(
            self.payload(document_ids=[str(self.unselected.pk)]),
            user=self.user,
            prospect=self.prospect,
        )
        self.assertFalse(form.is_valid())

    def test_prospect_without_files_records_data_gap_without_project_fallback(self):
        DocLink.objects.all().delete()
        result, prompt = self.generate(
            ReportCompositionForm({}, user=self.user, prospect=self.prospect)
        )
        self.assertEqual(result["doc_ids"], [])
        self.assertNotIn("UNSELECTED_SECRET", prompt)
        self.assertNotIn("SELECTED_EVIDENCE", prompt)
        self.assertIn("HYPOTHESIS", prompt)

    def test_bounded_unicode_excerpts_preserve_all_selected_sources(self):
        self.doc.extracted_text = "地质数据 copper " * 5000
        self.doc.save()
        result, prompt = self.generate()
        self.assertLessEqual(len(prompt.encode()), MAX_PROMPT_BYTES)
        self.assertIn("[truncated]", prompt)
        self.assertEqual(result["doc_ids"], [str(self.doc.pk)])

    def test_metadata_disabled_omits_extended_metadata_but_keeps_source_identity(self):
        self.doc.author_name = "EXCLUDED_AUTHOR"
        self.doc.save()
        result, prompt = self.generate()
        self.assertNotIn("EXCLUDED_AUTHOR", prompt)
        self.assertIn(str(self.doc.pk), prompt)
        self.assertEqual(result["manifest"]["sources"][0]["checksum"], self.doc.checksum_sha256)

    def test_empty_model_reply_creates_no_report(self):
        with patch("core.ai.composition.GraniteClient.complete", return_value=""):
            response = self.client.post(reverse("generate_report"), self.payload())
            run_next()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReportGenerationJob.objects.get().status, "FAILED")
        self.assertTrue(ReportGenerationJob.objects.get().retryable)
        self.assertFalse(SavedReport.objects.exists())

    def test_http_generation_saves_exact_manifest_sources_and_classification(self):
        with patch("core.ai.composition.GraniteClient.complete", return_value="# Draft"):
            response = self.client.post(reverse("generate_report"), self.payload())
            run_next()
        self.assertEqual(response.status_code, 302)
        report = SavedReport.objects.get()
        self.assertEqual(report.source_documents.get(), self.doc)
        self.assertEqual(report.clearance_level, "CONFIDENTIAL")
        self.assertEqual(report.generation_manifest["options"]["tone"], "technical")
        self.assertIn("SELECTED_EVIDENCE", report.generation_manifest["prompt"])
        self.assertEqual(ReportGenerationJob.objects.get().result, report)

    def test_ai_failure_preserves_form_values_and_never_saves_partial_report(self):
        with patch("core.ai.composition.GraniteClient.complete", side_effect=RuntimeError("offline")):
            response = self.client.post(reverse("generate_report"), self.payload())
            run_next()
        self.assertEqual(response.status_code, 302)
        job = ReportGenerationJob.objects.get()
        self.assertEqual(job.status, "FAILED")
        restored = self.client.get(reverse("report_list"), {"resume": job.pk})
        self.assertContains(restored, "Focus on uncertainty")
        self.assertEqual(restored.context["selected_document_ids"], [str(self.doc.pk)])
        self.assertFalse(SavedReport.objects.exists())

    def test_source_edit_reclassification_or_new_version_during_generation_rejects_save(self):
        for field, value in [
            ("extracted_text", "Changed"),
            ("confidentiality", "jorc_restricted"),
            ("is_latest", False),
        ]:
            with self.subTest(field=field):
                result, _ = self.generate()
                original = getattr(self.doc, field)
                Document.objects.filter(pk=self.doc.pk).update(**{field: value})
                with self.assertRaises(ValidationError):
                    persist_composition(self.user, self.process, result, "Stale report")
                Document.objects.filter(pk=self.doc.pk).update(**{field: original})
        self.assertFalse(SavedReport.objects.exists())

    def test_generation_audit_failure_rolls_back_report_and_source_relations(self):
        result, _ = self.generate()
        with patch("core.ai.composition.log_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                persist_composition(self.user, self.process, result, "Report")
        self.assertFalse(SavedReport.objects.exists())

    def test_manual_revision_inherits_generation_manifest(self):
        result, _ = self.generate()
        report = persist_composition(self.user, self.process, result, "Report")
        revision = SavedReport.create_version(report, "# Edited", self.user, "MANUAL_EDIT")
        self.assertEqual(revision.generation_manifest, report.generation_manifest)
        self.assertEqual(revision.source_documents.get(), self.doc)

    def test_prospect_route_uses_new_composition_service(self):
        with patch("core.ai.composition.GraniteClient.complete", return_value="# Prospect draft"):
            response = self.client.post(reverse("generate_prospect_report", args=[self.prospect.pk]))
            run_next()
        self.assertEqual(response.status_code, 302)
        report = SavedReport.objects.get()
        self.assertEqual(report.prospect, self.prospect)
        self.assertEqual(report.source_documents.get(), self.doc)
        self.assertIn("HYPOTHESIS", report.generation_manifest["prompt"])

    def test_viewer_cannot_generate_and_foreign_project_is_rejected(self):
        self.user.profile.role = "VIEWER"
        self.user.profile.save()
        with patch("core.ai.composition.GraniteClient.complete") as call:
            self.assertEqual(
                self.client.post(reverse("generate_report"), self.payload()).status_code, 403
            )
            call.assert_not_called()

    def test_get_generation_route_redirects(self):
        self.assertRedirects(self.client.get(reverse("generate_report")), reverse("report_list"))

    def test_access_change_after_form_validation_stops_before_model_call(self):
        form = self.form()
        Document.objects.filter(pk=self.doc.pk).update(confidentiality="jorc_restricted")
        with patch("core.ai.composition.GraniteClient.complete") as call:
            with self.assertRaises(ValidationError):
                compose_report(form)
            call.assert_not_called()

    def test_oversized_metadata_fails_without_silently_dropping_selected_files(self):
        docs = [
            self.document("地" * 64, f"Observation {i}", author_name="地" * 128) for i in range(10)
        ]
        form = self.form(document_ids=[str(doc.pk) for doc in docs], include_metadata="on")
        with patch("core.ai.composition.GraniteClient.complete") as call:
            with self.assertRaises(ValidationError):
                compose_report(form)
            call.assert_not_called()

    def test_multibyte_instructions_have_a_byte_limit(self):
        form = ReportCompositionForm(self.payload(instructions="地" * 800), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("instructions", form.errors)

    def test_invalid_foreign_project_post_never_calls_provider(self):
        with patch("core.ai.composition.GraniteClient.complete") as call:
            response = self.client.post(
                reverse("generate_report"), self.payload(process_id=str(self.foreign.pk))
            )
        self.assertEqual(response.status_code, 400)
        call.assert_not_called()

    def test_prospect_link_with_wrong_project_document_is_not_used(self):
        doc = self.document("Wrong linked project", "WRONG_LINK_MARKER", process=self.other_project)
        DocLink.objects.create(
            document=doc,
            content_type=ContentType.objects.get_for_model(Prospect),
            object_id=self.prospect.pk,
        )
        result, prompt = self.generate(
            ReportCompositionForm({}, user=self.user, prospect=self.prospect)
        )
        self.assertNotIn("WRONG_LINK_MARKER", prompt)
        self.assertEqual(result["doc_ids"], [str(self.doc.pk)])

    def test_unlinked_source_during_generation_prevents_prospect_persistence(self):
        result, _ = self.generate(ReportCompositionForm({}, user=self.user, prospect=self.prospect))
        DocLink.objects.all().delete()
        with self.assertRaises(ValidationError):
            persist_composition(
                self.user, self.process, result, "Stale prospect report", self.prospect
            )
        self.assertFalse(SavedReport.objects.exists())
