"""Real workbook/database/storage regressions for ingestion and replacement failures."""

import io
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import openpyxl
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from core.geo_utils import projected_to_wgs84
from core.importers import run_drillhole_import
from core.models import (
    AssayResult,
    AuditLog,
    Document,
    DocumentChunk,
    Drillhole,
    DrillholeSurvey,
    LithologyInterval,
    Organisation,
    Process,
)


def workbook(collar=None, survey=None, litho=None, assay=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    data = [
        (
            "DH Collars",
            ["HOLEID", "GRID", "MGA94_EAST", "MGA94_NORTH", "TOTAL_DEPTH", "DIP", "AZIMUTH (TN)"],
            collar
            if collar is not None
            else [["DH1", "MGA94 zone 56", 500000, 7000000, 100, -60, 180]],
        ),
        (
            "DH DHSurvey",
            ["HOLEID", "DEPTH", "DIP", "AZIMUTH (TN)"],
            survey if survey is not None else [["DH1", 10, -60, 180]],
        ),
        (
            "DH_Lithology",
            ["HOLEID", "FROM", "TO", "LITHOLOGY"],
            litho if litho is not None else [["DH1", 0, 10, "granite"]],
        ),
        (
            "DH_Assays",
            ["HOLEID", "FROM", "TO", "AU_PPM"],
            assay if assay is not None else [["DH1", 0, 10, -0.01]],
        ),
    ]
    for name, headers, rows in data:
        ws = wb.create_sheet(name)
        ws.append(headers)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out


class ImportIntegrityTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Import test")
        self.process = Process.objects.create(name="Site", organisation=self.org)

    def run_import(self, source=None, **kwargs):
        return run_drillhole_import(source or workbook(), self.org, self.process, **kwargs)

    def counts(self):
        return tuple(
            m.objects.count() for m in (Drillhole, DrillholeSurvey, LithologyInterval, AssayResult)
        )

    def test_repeat_skip_preserves_all_rows(self):
        self.assertTrue(self.run_import()["applied"])
        original = list(DrillholeSurvey.objects.values_list("pk", flat=True))
        result = self.run_import()
        self.assertEqual(self.counts(), (1, 1, 1, 1))
        self.assertEqual(result["counters"]["collars_skipped"], 1)
        self.assertEqual(result["counters"]["surveys_created"], 0)
        self.assertEqual(list(DrillholeSurvey.objects.values_list("pk", flat=True)), original)
        hole = Drillhole.objects.get()
        self.assertEqual(hole.source_crs, "EPSG:28356")
        self.assertAlmostEqual(hole.collar_location.x, 153, places=4)
        self.assertEqual(AssayResult.objects.get().au_ppm, -0.01)

    def test_update_replaces_children_and_empty_sheets_clear(self):
        self.run_import()
        source = workbook(survey=[["DH1", 20, -45, 90]], litho=[], assay=[])
        result = self.run_import(source, update=True)
        self.assertTrue(result["applied"])
        self.assertEqual(self.counts(), (1, 1, 0, 0))
        self.assertEqual(DrillholeSurvey.objects.get().depth, 20)

    def test_dry_run_matches_validation_without_mutation(self):
        planned = self.run_import(dry_run=True)
        self.assertTrue(planned["valid"])
        self.assertFalse(planned["applied"])
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        actual = self.run_import()
        self.assertEqual(planned["counters"], actual["counters"])
        before = list(DrillholeSurvey.objects.values())
        self.run_import(workbook(survey=[], litho=[], assay=[]), dry_run=True, update=True)
        self.assertEqual(list(DrillholeSurvey.objects.values()), before)

    def test_invalid_intervals_reject_whole_workbook_and_preserve_old_data(self):
        self.run_import()
        original = list(LithologyInterval.objects.values())
        for interval in [(10, 5), (-1, 10), (10, 10), (0, 101), (None, 10), ("bad", 10)]:
            for dry_run in [False, True]:
                with self.subTest(interval=interval, dry_run=dry_run):
                    result = self.run_import(
                        workbook(litho=[["DH1", *interval, "new"]]), update=True, dry_run=dry_run
                    )
                    self.assertFalse(result["valid"])
                    self.assertFalse(result["applied"])
                    self.assertEqual(result["counters"]["collars_updated"], 0)
                    self.assertEqual(list(LithologyInterval.objects.values()), original)

    def test_bad_coordinates_and_numbers_reject_instead_of_becoming_null_or_zero(self):
        cases = [
            ["DH1", "unknown", 500000, 7000000, 100, -60, 180],
            ["DH1", "MGA94 zone 56", 500000, None, 100, -60, 180],
            ["DH1", "MGA94 zone 56", "nan", 7000000, 100, -60, 180],
            ["DH1", "MGA94 zone 56", 1e20, 7000000, 100, -60, 180],
            ["DH1", "", None, None, "bad", -60, 180],
            ["DH1", "", None, None, 100, -91, 180],
            ["DH1", "", None, None, 100, -60, 361],
        ]
        for row in cases:
            with self.subTest(row=row):
                self.assertFalse(self.run_import(workbook(collar=[row]))["valid"])
                self.assertEqual(self.counts(), (0, 0, 0, 0))
        for value in [float("nan"), float("inf"), -float("inf")]:
            with self.assertRaises(ValueError):
                projected_to_wgs84(value, 7000000, 28356)

    def test_missing_optional_coordinates_remain_allowed(self):
        result = self.run_import(workbook(collar=[["DH1", "", None, None, 100, -60, 180]]))
        self.assertTrue(result["valid"])
        self.assertIsNone(Drillhole.objects.get().collar_location)

    def test_missing_sheet_or_required_header_never_writes(self):
        for mode in ["sheet", "header"]:
            source = workbook()
            wb = openpyxl.load_workbook(source)
            if mode == "sheet":
                del wb["DH_Assays"]
            else:
                wb["DH_Assays"]["B1"] = "wrong"
            out = io.BytesIO()
            wb.save(out)
            with self.assertRaises(ValueError):
                self.run_import(out)
            self.assertEqual(self.counts(), (0, 0, 0, 0))

    def test_unknown_child_and_duplicate_collar_reject_all(self):
        self.assertFalse(self.run_import(workbook(survey=[["OTHER", 1, -60, 180]]))["valid"])
        row = ["DH1", "", None, None, 100, -60, 180]
        self.assertFalse(self.run_import(workbook(collar=[row, row]))["valid"])
        self.assertEqual(self.counts(), (0, 0, 0, 0))

    def test_database_failure_rolls_back_replacements(self):
        self.run_import()
        original = list(DrillholeSurvey.objects.values())
        with patch.object(AssayResult, "save", side_effect=RuntimeError("database failure")):
            with self.assertRaises(RuntimeError):
                self.run_import(update=True)
        self.assertEqual(self.counts(), (1, 1, 1, 1))
        self.assertEqual(list(DrillholeSurvey.objects.values()), original)

    def test_foreign_process_and_ambiguous_existing_holes_rejected(self):
        other = Organisation.objects.create(name="Other")
        with self.assertRaises(ValueError):
            run_drillhole_import(workbook(), other, self.process)
        for _ in range(2):
            Drillhole.objects.create(name="DH1", organisation=self.org, process=self.process)
        self.assertFalse(self.run_import(update=True)["valid"])
        self.assertEqual(self.counts(), (2, 0, 0, 0))

    def test_http_results_distinguish_rejection_and_audit_real_counts(self):
        user = User.objects.create_user(username="import-manager")
        user.profile.organisation = self.org
        user.profile.role = "DATA_MANAGER"
        user.profile.save()
        self.client.force_login(user)

        def submit(source):
            return self.client.post(
                reverse("drillhole_import"),
                {
                    "organisation": str(self.org.pk),
                    "process": str(self.process.pk),
                    "file": SimpleUploadedFile("holes.xlsx", source.getvalue()),
                },
            )

        response = submit(workbook(litho=[["DH1", 10, 0, "invalid"]]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Validation failed — no data written")
        self.assertFalse(AuditLog.objects.exists())
        with patch("core.views.log_audit", side_effect=RuntimeError("audit unavailable")):
            response = submit(workbook())
        self.assertContains(response, "audit unavailable")
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        response = submit(workbook())
        self.assertContains(response, "Import Complete")
        self.assertIn("1 created, 0 updated, 0 skipped", AuditLog.objects.get().description)

    def test_command_rejected_workbook_exits_with_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.xlsx"
            path.write_bytes(workbook(litho=[["DH1", 10, 0, "invalid"]]).getvalue())
            with self.assertRaises(CommandError):
                call_command(
                    "import_drillhole_excel",
                    file=str(path),
                    organisation=self.org.name,
                    process=self.process.name,
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
        self.assertEqual(self.counts(), (0, 0, 0, 0))


class DocumentVersionIntegrityTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = FileSystemStorage(location=self.temp.name)
        self.enterContext(patch.object(Document._meta.get_field("file"), "storage", self.storage))
        self.org = Organisation.objects.create(name="Documents")
        self.user = User.objects.create_user(username="version-author")
        self.parent = Document.objects.create(
            title="Evidence",
            organisation=self.org,
            file=ContentFile(b"original", name="old.txt"),
            confidentiality="confidential",
            created_by=self.user,
        )

    def upload(self, content=b"replacement"):
        return SimpleUploadedFile("old.txt", content)

    def assert_original_intact(self):
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.is_latest)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentChunk.objects.count(), 0)
        self.assertEqual(self.storage.open(self.parent.file.name).read(), b"original")
        self.assertEqual(len(list(Path(self.temp.name).rglob("*.txt"))), 1)

    def test_success_preserves_metadata_chunks_and_file_bytes(self):
        with patch("core.utils.extract_text", return_value="new geological evidence"):
            doc = Document.create_version(self.parent, self.upload(), self.user)
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.is_latest)
        self.assertTrue(doc.is_latest)
        self.assertEqual(doc.parent_document, self.parent)
        self.assertEqual(doc.version_number, 2)
        self.assertEqual(doc.confidentiality, "confidential")
        self.assertEqual(doc.chunks.get().text, "new geological evidence")
        self.assertEqual(doc.file.read(), b"replacement")
        self.assertNotEqual(doc.file.name, self.parent.file.name)
        self.assertEqual(self.storage.open(self.parent.file.name).read(), b"original")
        with self.assertRaises(ValueError):
            Document.create_version(self.parent, self.upload(b"third"), self.user)
        self.assertEqual(Document.objects.filter(is_latest=True).count(), 1)

    def test_storage_failure_preserves_parent(self):
        with patch.object(self.storage, "save", side_effect=OSError("storage unavailable")):
            with self.assertRaises(OSError):
                Document.create_version(self.parent, self.upload(), self.user)
        self.assert_original_intact()

    def test_chunk_failure_rolls_back_and_cleans_new_file(self):
        with (
            patch("core.utils.extract_text", return_value="new text"),
            patch.object(
                DocumentChunk.objects, "bulk_create", side_effect=RuntimeError("index failure")
            ),
        ):
            with self.assertRaises(RuntimeError):
                Document.create_version(self.parent, self.upload(), self.user)
        self.assert_original_intact()

    def test_duplicate_file_does_not_hide_parent(self):
        with self.assertRaises(ValueError):
            Document.create_version(self.parent, self.upload(b"original"), self.user)
        self.assert_original_intact()

    def test_parent_write_failure_rolls_back_new_document_and_file(self):
        real_save = Document.save

        def fail_parent(instance, *args, **kwargs):
            if instance.pk == self.parent.pk:
                raise RuntimeError("parent write failed")
            return real_save(instance, *args, **kwargs)

        with patch.object(Document, "save", new=fail_parent):
            with self.assertRaises(RuntimeError):
                Document.create_version(self.parent, self.upload(), self.user)
        self.assert_original_intact()


class ConcurrentIngestionTests(TransactionTestCase):
    def test_competing_versions_have_one_latest_and_reject_stale_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemStorage(location=directory)
            with patch.object(Document._meta.get_field("file"), "storage", storage):
                org = Organisation.objects.create(name="Concurrent docs")
                user = User.objects.create_user(username="parallel-author")
                parent = Document.objects.create(
                    title="Evidence",
                    organisation=org,
                    file=ContentFile(b"original", name="evidence.txt"),
                    created_by=user,
                )

                def worker(index):
                    close_old_connections()
                    try:
                        Document.create_version(
                            parent,
                            SimpleUploadedFile("evidence.txt", f"version {index}".encode()),
                            user,
                        )
                        return "created"
                    except ValueError:
                        return "stale"
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(worker, range(2)))
                self.assertCountEqual(results, ["created", "stale"])
                self.assertEqual(Document.objects.count(), 2)
                self.assertEqual(Document.objects.filter(is_latest=True).count(), 1)
                self.assertEqual(storage.open(parent.file.name).read(), b"original")

    def test_competing_imports_serialize_without_duplicate_rows(self):
        org = Organisation.objects.create(name="Concurrent")
        process = Process.objects.create(name="Site", organisation=org)

        def worker(_):
            close_old_connections()
            try:
                return run_drillhole_import(workbook(), org, process)["counters"]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(sum(r["collars_created"] for r in results), 1)
        self.assertEqual(sum(r["collars_skipped"] for r in results), 1)
        for model in [Drillhole, DrillholeSurvey, LithologyInterval, AssayResult]:
            self.assertEqual(model.objects.count(), 1)
