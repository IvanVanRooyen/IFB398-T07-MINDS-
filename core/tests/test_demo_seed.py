"""Synthetic seed safety, repeatability and file/database failure behavior."""

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.management.commands.seed_demo import REVIEWER, WRITER, identity
from core.models import (
    AssayResult,
    DocLink,
    Document,
    Drillhole,
    Organisation,
    Process,
    SavedReport,
)
from core.utils import extract_text


@override_settings(DEBUG=True, ALLOW_DEMO_SEED=True)
class DemoSeedTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.enterContext(override_settings(MEDIA_ROOT=directory.name))
        self.enterContext(patch.dict(os.environ, {"DEMO_PASSWORD": "synthetic-test-password-only"}))

    def seed(self, **kwargs):
        call_command("seed_demo", stdout=io.StringIO(), **kwargs)

    def test_repeat_seed_preserves_ids_files_edits_and_passwords(self):
        self.seed()
        doc = Document.objects.get(pk=identity("document"))
        original_key = doc.file.name
        original_counts = (
            Drillhole.objects.count(),
            AssayResult.objects.count(),
            SavedReport.objects.count(),
        )
        project = Process.objects.get(pk=identity("project"))
        project.name = "Edited synthetic project"
        project.save()
        writer = User.objects.get(username=WRITER)
        writer.set_password("changed-locally-only")
        writer.save()
        self.seed()
        self.assertEqual(
            original_counts,
            (Drillhole.objects.count(), AssayResult.objects.count(), SavedReport.objects.count()),
        )
        self.assertEqual(Document.objects.get(pk=doc.pk).file.name, original_key)
        self.assertEqual(Process.objects.get(pk=project.pk).name, "Edited synthetic project")
        self.assertTrue(User.objects.get(username=WRITER).check_password("changed-locally-only"))
        self.assertEqual(DocLink.objects.count(), 1)

    def test_real_document_and_snapshot_have_synthetic_values_and_no_model_call(self):
        with patch(
            "core.ai.composition.GraniteClient",
            side_effect=AssertionError("No model should be called"),
        ):
            self.seed()
        doc = Document.objects.get(pk=identity("document"))
        with doc.file.open("rb"):
            text = extract_text(doc.file)
        self.assertIn("Synthetic", text)
        self.assertIn("8000", text)
        report = SavedReport.objects.get(pk=identity("report"))
        self.assertEqual(report.generation_manifest["backend"], "manual")
        self.assertEqual(report.source_documents.get().pk, doc.pk)
        self.assertEqual(len(report.data_appendix["tables"]), 3)
        self.assertEqual(report.data_appendix["plan"]["omitted"], 1)
        for username in (WRITER, REVIEWER):
            user = User.objects.get(username=username)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertTrue(user.check_password("synthetic-test-password-only"))

    def test_reset_replaces_only_demo_project_and_cleans_old_files_after_commit(self):
        self.seed()
        org = Organisation.objects.get(pk=identity("organisation"))
        outside = Process.objects.create(name="Another project", organisation=org)
        extra = User.objects.create_user("another-local-user")
        extra.profile.organisation = org
        extra.profile.save()
        old_file = Document.objects.get(pk=identity("document")).file.path
        report = SavedReport.objects.get(pk=identity("report"))
        report.title = "Edited report"
        report.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.seed(reset=True)
        self.assertTrue(Process.objects.filter(pk=outside.pk).exists())
        self.assertTrue(User.objects.get(pk=extra.pk).profile.organisation_id == org.pk)
        self.assertEqual(User.objects.get(username=WRITER).profile.organisation_id, org.pk)
        self.assertEqual(
            SavedReport.objects.get(pk=report.pk).title, "Synthetic exploration evidence review"
        )
        self.assertFalse(Path(old_file).exists())
        self.assertTrue(Path(Document.objects.get(pk=identity("document")).file.path).exists())

    def test_failed_initial_seed_rolls_back_rows_and_cleans_new_file(self):
        with patch(
            "core.management.commands.seed_demo.log_audit",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.seed()
        self.assertFalse(Organisation.objects.exists())
        self.assertFalse(User.objects.exists())
        self.assertEqual([p for p in self.directory.rglob("*") if p.is_file()], [])

    def test_failed_reset_preserves_old_rows_and_file(self):
        self.seed()
        old_file = Document.objects.get(pk=identity("document")).file.path
        with patch(
            "core.management.commands.seed_demo.log_audit",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.seed(reset=True)
        self.assertEqual(Document.objects.get(pk=identity("document")).file.path, old_file)
        self.assertTrue(Path(old_file).exists())
        self.assertEqual(len([p for p in self.directory.rglob("*") if p.is_file()]), 1)

    def test_existing_username_is_never_taken_over(self):
        user = User.objects.create_user(WRITER, password="existing-account-only")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertTrue(User.objects.get(pk=user.pk).check_password("existing-account-only"))
        self.assertFalse(Organisation.objects.exists())

    def test_foreign_document_identity_collision_is_rejected(self):
        foreign = Organisation.objects.create(name="Foreign")
        doc = Document.objects.create(
            id=identity("document"), title="Foreign record", organisation=foreign
        )
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(Document.objects.get(pk=doc.pk).organisation_id, foreign.pk)
        self.assertFalse(DocLink.objects.exists())
        self.assertFalse(User.objects.exists())

    def test_seed_requires_local_profile_and_explicit_password(self):
        with override_settings(ALLOW_DEMO_SEED=False):
            with self.assertRaises(CommandError):
                self.seed()
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self.seed()
        with patch.dict(os.environ, {"DEMO_PASSWORD": ""}):
            with self.assertRaises(CommandError):
                self.seed()
        self.assertFalse(Organisation.objects.exists())
