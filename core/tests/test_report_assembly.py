"""Real persistence, scope, review and file-format checks for report assembly."""

import io
import json
import math
import zipfile
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pdfplumber
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.ai import jobs
from core.ai.composition import ReportCompositionForm
from core.models import ApprovalWorkflow, AssayResult, Drillhole, LithologyInterval, SavedReport
from core.reporting.appendix import MAX_HOLES, MAX_ROWS, capture, layout
from core.tests import test_composition as fixtures


class AssemblyTests(TestCase):
    def setUp(self):
        f = fixtures.CompositionTests(methodName="runTest")
        f.client = self.client
        f.setUp()
        self.f = f
        self.user = f.user
        self.hole = Drillhole.objects.create(
            name="DH01",
            process=f.process,
            organisation=f.org,
            prospect=f.prospect,
            collar_location=Point(153, -27, srid=4326),
            depth=100,
            dip=-60,
            azimuth=45,
        )
        self.assay = AssayResult.objects.create(
            drillhole=self.hole,
            from_depth=10,
            to_depth=12,
            sample_number="A01",
            au_ppm=-0.01,
            cu_ppm=8000,
        )
        self.lith = LithologyInterval.objects.create(
            drillhole=self.hole,
            from_depth=0,
            to_depth=20,
            lithology="Basalt",
            mineralisation="Chalcopyrite",
        )
        self.report = SavedReport.objects.create(
            title="Geological report",
            content_md="# Findings\nRecorded observations.",
            process=f.process,
            prospect=f.prospect,
            organisation=f.org,
            created_by=self.user,
            clearance_level="CONFIDENTIAL",
        )

    def capture(self, **kwargs):
        return capture(
            self.user,
            self.f.process,
            self.f.prospect,
            kwargs.get("tables", ["collars", "assays", "lithology"]),
            kwargs.get("plan", True),
        )

    def save(self, report=None, **kwargs):
        report = report or self.report
        data = {
            "title": report.title,
            "content_md": report.content_md,
            "appendix_action": "replace",
            "appendix_tables": ["collars", "assays", "lithology"],
            "appendix_plan": "on",
        }
        data.update(kwargs)
        return self.client.post(reverse("update_saved_report", args=[report.pk]), data)

    def latest(self):
        return (
            SavedReport.objects.filter(series_id=self.report.series_id)
            .order_by("-version_number")
            .first()
        )

    def test_scope_excludes_other_project_foreign_tenant_and_unlinked_holes(self):
        for process, org in [
            (self.f.other_project, self.f.org),
            (self.f.foreign, self.f.other_org),
            (self.f.process, self.f.org),
        ]:
            hole = Drillhole.objects.create(name="EXCLUDED", process=process, organisation=org)
            AssayResult.objects.create(drillhole=hole, from_depth=1, to_depth=2, cu_ppm=999)
        snapshot = self.capture()
        self.assertEqual([len(t["rows"]) for t in snapshot["tables"]], [1, 1, 1])
        self.assertNotIn("EXCLUDED", json.dumps(snapshot))
        self.assertEqual(snapshot["scope"]["prospect_id"], str(self.f.prospect.pk))

    def test_inconsistent_foreign_hole_with_local_prospect_is_excluded(self):
        Drillhole.objects.create(
            name="BAD",
            process=self.f.process,
            organisation=self.f.other_org,
            prospect=self.f.prospect,
        )
        self.assertNotIn("BAD", json.dumps(self.capture()))

    def test_assay_units_bdl_missing_values_and_record_ids_are_preserved(self):
        self.assay.cu_ppm = None
        self.assay.save()
        snapshot = self.capture()
        table = snapshot["tables"][1]
        self.assertEqual(table["rows"][0]["cells"][-2:], ["BDL (-0.01)", "—"])
        self.assertEqual(table["rows"][0]["id"], str(self.assay.pk))
        self.assertIn("Cu (ppm)", table["columns"])
        self.assertEqual(len(snapshot["sha256"]), 64)

    def test_empty_scope_retains_explicit_empty_tables_and_plan(self):
        self.hole.delete()
        snapshot = self.capture()
        self.assertTrue(all(not t["rows"] for t in snapshot["tables"]))
        self.assertEqual(snapshot["plan"]["points"], [])

    def test_missing_coordinates_are_counted_and_single_coincident_points_are_finite(self):
        missing = Drillhole.objects.create(
            name="Unmapped",
            process=self.f.process,
            organisation=self.f.org,
            prospect=self.f.prospect,
        )
        snapshot = self.capture()
        self.assertEqual(snapshot["plan"]["omitted"], 1)
        self.assertEqual(layout(snapshot["plan"]), [{"label": "1", "x": 300.0, "y": 165.0}])
        missing.collar_location = self.hole.collar_location
        missing.save()
        self.assertEqual(layout(self.capture()["plan"]), [{"label": "1,2", "x": 300.0, "y": 165.0}])
        self.assertTrue(
            all(
                math.isfinite(p["x"]) and math.isfinite(p["y"])
                for p in layout(self.capture()["plan"])
            )
        )

    def test_invalid_coordinates_or_intervals_are_rejected(self):
        self.hole.collar_location = Point(200, -27, srid=4326)
        self.hole.save()
        with self.assertRaises(ValidationError):
            self.capture()
        self.hole.collar_location = None
        self.hole.save()
        self.assay.to_depth = 101
        self.assay.save()
        with self.assertRaises(ValidationError):
            self.capture()

    def test_date_line_crossing_requires_omitting_schematic(self):
        self.hole.collar_location = Point(179, -27, srid=4326)
        self.hole.save()
        Drillhole.objects.create(
            name="West",
            process=self.f.process,
            organisation=self.f.org,
            prospect=self.f.prospect,
            collar_location=Point(-179, -27, srid=4326),
        )
        with self.assertRaises(ValidationError):
            self.capture()
        self.assertIsNone(self.capture(plan=False)["plan"])

    def test_limits_fail_without_silent_truncation(self):
        for i in range(MAX_HOLES):
            Drillhole.objects.create(
                name=f"Extra{i}",
                process=self.f.process,
                organisation=self.f.org,
                prospect=self.f.prospect,
            )
        with self.assertRaises(ValidationError):
            self.capture()
        Drillhole.objects.exclude(pk=self.hole.pk).delete()
        AssayResult.objects.bulk_create(
            [AssayResult(drillhole=self.hole, from_depth=1, to_depth=2) for _ in range(MAX_ROWS)]
        )
        with self.assertRaises(ValidationError):
            self.capture()
        self.assertEqual(len(self.capture(tables=["collars"])["tables"]), 1)

    def test_capture_is_versioned_with_current_narrative_and_old_revision_unchanged(self):
        response = self.save(title="Updated title", content_md="# Updated narrative")
        self.assertEqual(response.status_code, 200)
        current = self.latest()
        self.assertEqual(current.version_number, 2)
        self.assertEqual(current.content_md, "# Updated narrative")
        self.assertTrue(current.data_appendix)
        self.report.refresh_from_db()
        self.assertEqual(self.report.data_appendix, {})
        self.assertIn("Drillhole collars", response.json()["appendix_html"])

    def test_narrative_save_inherits_snapshot_after_database_change(self):
        self.save()
        snapshot = self.latest().data_appendix
        self.assay.cu_ppm = 1
        self.assay.save()
        response = self.save(
            self.latest(), appendix_action="preserve", content_md="Manual revision"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.latest().data_appendix, snapshot)

    def test_explicit_refresh_and_remove_create_revisions(self):
        self.save()
        before = self.latest().data_appendix
        self.assay.cu_ppm = 1
        self.assay.save()
        self.save(self.latest())
        self.assertNotEqual(before["sha256"], self.latest().data_appendix["sha256"])
        self.save(self.latest(), appendix_action="remove")
        self.assertEqual(self.latest().data_appendix, {})
        self.assertEqual(self.latest().version_number, 4)

    def test_invalid_selection_rolls_back_narrative_and_creates_no_revision(self):
        response = self.save(appendix_tables=["foreign"], content_md="Should not persist")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SavedReport.objects.count(), 1)
        self.assertEqual(self.latest().content_md, self.report.content_md)

    def test_stale_version_cannot_capture_or_change_appendix(self):
        self.save()
        before = self.latest().data_appendix
        self.assertEqual(self.save().status_code, 409)
        self.assertEqual(self.latest().data_appendix, before)
        self.assertEqual(SavedReport.objects.count(), 2)

    def test_capture_and_audit_failure_roll_back_together(self):
        with patch("core.views.log_audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.save()
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_review_captures_exact_narrative_and_appendix_then_locks_it(self):
        response = self.client.post(
            reverse("submit_report_for_review", args=[self.report.pk]),
            {
                "title": "Review snapshot",
                "content_md": "Final narrative",
                "workflow_type": "GENERAL",
                "appendix_action": "replace",
                "appendix_tables": ["assays"],
                "appendix_plan": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        report = self.latest()
        self.assertEqual(report.status, "UNDER_REVIEW")
        self.assertEqual(report.content_md, "Final narrative")
        self.assertEqual(ApprovalWorkflow.objects.get().object_id, report.pk)
        self.assertEqual(len(report.data_appendix["tables"]), 1)
        self.assertEqual(self.save(report).status_code, 403)

    def test_unauthorized_capture_and_export_are_denied(self):
        self.save()
        report = self.latest()
        self.user.profile.organisation = self.f.other_org
        self.user.profile.save()
        self.assertEqual(self.save(report).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("export_report"), {"report_id": str(report.pk), "format": "docx"}
            ).status_code,
            403,
        )

    def test_native_save_redirects_with_snapshot_and_narrative(self):
        response = self.client.post(
            reverse("update_saved_report", args=[self.report.pk]) + "?return=editor",
            {
                "title": "Native title",
                "content_md": "Native narrative",
                "appendix_action": "replace",
                "appendix_tables": ["collars"],
            },
        )
        self.assertRedirects(response, reverse("saved_report_editor", args=[self.latest().pk]))
        self.assertEqual(self.latest().content_md, "Native narrative")

    def test_html_renders_hostile_record_text_as_text(self):
        self.hole.name = "<script>alert(1)</script>"
        self.hole.save()
        self.save()
        response = self.client.get(reverse("saved_report_editor", args=[self.latest().pk]))
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def export(self, fmt, report=None, **kwargs):
        report = report or self.latest()
        data = {
            "report_id": str(report.pk),
            "format": fmt,
            "title": report.title,
            "content_md": report.content_md,
        }
        data.update(kwargs)
        return self.client.post(reverse("export_report"), data)

    def test_docx_contains_real_tables_figure_and_frozen_values_after_source_deletion(self):
        self.save()
        report = self.latest()
        self.hole.delete()
        response = self.export("docx", report)
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            xml = z.read("word/document.xml")
            tree = ET.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            self.assertEqual(len(tree.findall(".//w:tbl", ns)), 3)
            self.assertIn(b"8000", xml)
            self.assertIn(report.data_appendix["sha256"].encode(), xml)
            self.assertTrue(any(name.startswith("word/media/") for name in z.namelist()))

    def test_pdf_contains_frozen_tables_and_figure_without_markup_execution(self):
        self.lith.lithology = '<img src="http://127.0.0.1:1/secret"/>'
        self.lith.save()
        self.save()
        response = self.export("pdf")
        self.assertEqual(response.status_code, 200)
        pdf = pdfplumber.open(io.BytesIO(response.content))
        text = "\n".join(p.extract_text() for p in pdf.pages)
        self.assertIn("8000", text)
        self.assertIn("Geological evidence appendix", text)
        self.assertIn("Drillhole collar plan", text)
        self.assertIn('<img src="http://127.0.', text)
        self.assertIn('0.1:1/secret"/>', text)
        self.assertTrue(any(p.curves for p in pdf.pages))
        pdf.close()

    def test_unsaved_text_cannot_be_exported_with_saved_appendix(self):
        self.save()
        self.assertEqual(self.export("docx", content_md="Unsaved").status_code, 409)

    def test_native_export_newline_normalization_uses_the_saved_snapshot(self):
        self.save()
        report = self.latest()
        response = self.export("docx", content_md=report.content_md.replace("\n", "\r\n"))
        self.assertEqual(response.status_code, 200)

    def test_maximum_assay_table_exports_every_row_across_pdf_pages(self):
        self.assay.delete()
        AssayResult.objects.bulk_create(
            [
                AssayResult(
                    drillhole=self.hole,
                    from_depth=i / 2,
                    to_depth=(i + 1) / 2,
                    sample_number=f"SAMPLE{i:03d}",
                    cu_ppm=i,
                )
                for i in range(MAX_ROWS)
            ]
        )
        response = self.save(appendix_tables=["assays"], appendix_plan="")
        self.assertEqual(response.status_code, 200)
        with pdfplumber.open(io.BytesIO(self.export("pdf").content)) as pdf:
            text = "\n".join(page.extract_text() for page in pdf.pages)
            self.assertGreater(len(pdf.pages), 1)
            for i in range(MAX_ROWS):
                self.assertIn(f"SAMPLE{i:03d}", text)

    def test_manual_queue_does_not_instantiate_or_call_provider(self):
        form = ReportCompositionForm(self.f.payload(drafting_mode="manual"), user=self.user)
        with patch(
            "core.ai.composition.GraniteClient", side_effect=AssertionError("No model allowed")
        ):
            job = jobs.enqueue(form)
            jobs.run_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")
        self.assertEqual(job.result.generation_manifest["backend"], "manual")
        self.assertEqual(job.result.generation_manifest["prompt"], "")
        self.assertIn("## Risks and uncertainty", job.result.content_md)
        self.assertEqual(job.result.source_documents.count(), 1)
