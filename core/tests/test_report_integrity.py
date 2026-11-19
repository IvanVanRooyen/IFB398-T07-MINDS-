
"""Persisted report identity, optimistic edits and exact review-snapshot regressions."""

import hashlib
import importlib
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from core.ai.jobs import run_next
from core.models import (
    ApprovalWorkflow,
    Document,
    Organisation,
    Process,
    SavedReport,
)


def author(name, org, reviewer=False):
    user = User.objects.create_user(name, password="review-only")
    user.profile.organisation = org
    user.profile.role = "ADMIN" if reviewer else "GEOLOGIST_EXPL"
    user.profile.clearance_level = "CONFIDENTIAL"
    user.profile.can_approve_jorc = reviewer
    user.profile.save()
    return user


class ReportIntegrityTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Report test")
        self.process = Process.objects.create(name="Project", organisation=self.org)
        self.user = author("writer", self.org)
        self.reviewer = author("reviewer", self.org, True)
        self.report = SavedReport.objects.create(
            title="Original",
            content_md="# Original evidence",
            process=self.process,
            organisation=self.org,
            created_by=self.user,
            clearance_level="CONFIDENTIAL",
            content_hash=hashlib.sha256(b"# Original evidence").hexdigest(),
        )
        self.doc = Document.objects.create(
            title="Source",
            organisation=self.org,
            process=self.process,
            confidentiality="confidential",
            checksum_sha256="a" * 64,
        )
        self.report.source_documents.add(self.doc)
        self.client.force_login(self.user)

    def update(self, report=None, title="Renamed", content="# Revised evidence"):
        return self.client.post(
            reverse("update_saved_report", args=[(report or self.report).pk]),
            {"title": title, "content_md": content},
        )

    def test_title_only_edit_preserves_series_sources_and_original_snapshot(self):
        response = self.update(content=self.report.content_md)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        version = SavedReport.objects.get(pk=data["report_id"])
        self.assertEqual(version.title, "Renamed")
        self.assertEqual(version.series_id, self.report.series_id)
        self.assertEqual(version.version_number, 2)
        self.assertEqual(version.parent_version_id, self.report.pk)
        self.assertEqual(list(version.source_documents.all()), [self.doc])
        self.report.refresh_from_db()
        self.assertEqual(self.report.title, "Original")
        self.assertEqual(data["save_url"], reverse("update_saved_report", args=[version.pk]))
        self.assertEqual(data["submit_url"], reverse("submit_report_for_review", args=[version.pk]))
        self.assertEqual(data["redirect_url"], reverse("saved_report_editor", args=[version.pk]))

    def test_second_save_uses_returned_identity_and_stale_tab_is_rejected(self):
        first = self.update().json()
        stale = self.update(title="Stale title")
        self.assertEqual(stale.status_code, 409)
        self.assertFalse(stale.json()["success"])
        version = SavedReport.objects.get(pk=first["report_id"])
        second = self.update(version, title="Third version")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["version_number"], 3)
        self.assertEqual(SavedReport.objects.count(), 3)

    def test_noop_save_reuses_current_version(self):
        response = self.update(title=self.report.title, content=self.report.content_md)
        self.assertEqual(response.json()["report_id"], str(self.report.pk))
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_same_title_does_not_merge_independent_reports_or_owners(self):
        for user in [self.user, self.reviewer]:
            self.client.force_login(user)
            response = self.client.post(
                reverse("save_report"),
                {
                    "process_id": self.process.pk,
                    "title": self.report.title,
                    "content_md": "# A separate investigation",
                },
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(SavedReport.objects.count(), 3)
        self.assertEqual(SavedReport.objects.values("series_id").distinct().count(), 3)

    def test_generated_reports_with_same_title_have_separate_series_and_sources(self):
        with patch(
            "core.ai.composition.GraniteClient.complete",
            return_value="# Generated evidence",
        ):
            for _ in range(2):
                response = self.client.post(
                    reverse("generate_report"),
                    {
                        "process_id": self.process.pk,
                        "report_title": "Same generated title",
                    },
                )
                run_next()
                self.assertEqual(response.status_code, 302)
        generated = SavedReport.objects.filter(title="Same generated title")
        self.assertEqual(generated.count(), 2)
        self.assertEqual(generated.values("series_id").distinct().count(), 2)
        for report in generated:
            self.assertEqual(report.source_documents.get(), self.doc)

    def test_generated_report_audit_failure_rolls_back_new_draft(self):
        with (
            patch(
                "core.ai.composition.GraniteClient.complete",
                return_value="# Generated evidence",
            ),
            patch(
                "core.ai.composition.log_audit",
                side_effect=RuntimeError("audit write failed"),
            ),
        ):
            response = self.client.post(reverse("generate_report"), {"process_id": self.process.pk})
            run_next()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_title_validation_rejects_before_writes(self):
        for title in ["", "x" * 257]:
            self.assertEqual(self.update(title=title).status_code, 400)
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_review_submits_current_editor_title_and_content_with_sources(self):
        response = self.client.post(
            reverse("submit_report_for_review", args=[self.report.pk]),
            {
                "title": "Ready for review",
                "content_md": "# The exact reviewed text",
                "workflow_type": "JORC",
                "submission_notes": "Check sources",
            },
        )
        self.assertEqual(response.status_code, 302)
        review = SavedReport.objects.get(status="UNDER_REVIEW")
        self.assertEqual(review.title, "Ready for review")
        self.assertEqual(review.content_md, "# The exact reviewed text")
        self.assertEqual(review.source_documents.get(), self.doc)
        self.assertEqual(review.approval_workflow.object_id, review.pk)
        self.assertEqual(response.url, reverse("saved_report_editor", args=[review.pk]))
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "DRAFT")
        self.assertEqual(self.report.content_md, "# Original evidence")
        self.assertEqual(self.update(review).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("assign_report_prospect", args=[review.pk]), {"prospect_id": ""}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                reverse("submit_report_for_review", args=[self.report.pk])
            ).status_code,
            409,
        )

    def test_invalid_review_payload_never_submits_or_creates_version(self):
        for data in [
            {"title": ""},
            {"content_md": "text"},
            {"title": "x" * 257, "content_md": "text"},
        ]:
            response = self.client.post(
                reverse("submit_report_for_review", args=[self.report.pk]), data
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(SavedReport.objects.count(), 1)
        self.assertFalse(ApprovalWorkflow.objects.exists())

    def test_review_audit_failure_rolls_back_revision_workflow_and_status(self):
        with patch("core.views.log_audit", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("submit_report_for_review", args=[self.report.pk]),
                    {"title": "New", "content_md": "Latest text"},
                )
        self.assertEqual(SavedReport.objects.count(), 1)
        self.assertFalse(ApprovalWorkflow.objects.exists())
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "DRAFT")

    def test_update_audit_failure_rolls_back_version_and_source_relations(self):
        with patch("core.views.log_audit", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.update()
        self.assertEqual(SavedReport.objects.count(), 1)
        self.assertEqual(self.report.source_documents.get(), self.doc)

    def test_approve_and_publish_preserve_reviewed_text(self):
        self.client.post(reverse("submit_report_for_review", args=[self.report.pk]))
        self.client.force_login(self.reviewer)
        self.assertEqual(
            self.client.post(reverse("approve_report", args=[self.report.pk])).status_code, 302
        )
        self.assertEqual(
            self.client.post(reverse("publish_report", args=[self.report.pk])).status_code, 302
        )
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "PUBLISHED")
        self.assertEqual(self.report.content_md, "# Original evidence")
        self.assertEqual(self.report.approval_workflow.status, "APPROVED")

    def test_approval_failure_keeps_workflow_and_report_in_review(self):
        self.client.post(reverse("submit_report_for_review", args=[self.report.pk]))
        self.client.force_login(self.reviewer)
        with patch("core.views.log_audit", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("approve_report", args=[self.report.pk]))
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "UNDER_REVIEW")
        self.assertEqual(self.report.approval_workflow.status, "PENDING")

    def test_history_retains_renamed_versions_and_separates_identical_titles(self):
        data = self.update().json()
        unrelated = SavedReport.objects.create(
            title="Renamed",
            content_md="Other",
            organisation=self.org,
            process=self.process,
            created_by=self.user,
        )
        response = self.client.get(reverse("report_version_detail", args=[data["report_id"]]))
        self.assertEqual(
            {r.pk for r in response.context["all_versions"]},
            {self.report.pk, SavedReport.objects.get(pk=data["report_id"]).pk},
        )
        response = self.client.get(reverse("report_history", args=[self.process.pk]))
        self.assertEqual(len(response.context["grouped"]), 2)
        self.assertNotEqual(unrelated.series_id, self.report.series_id)

    def test_migration_backfills_parent_families_not_same_titles(self):
        child = SavedReport.objects.create(
            title="Renamed",
            content_md="child",
            organisation=self.org,
            process=self.process,
            parent_version=self.report,
            version_number=2,
        )
        unrelated = SavedReport.objects.create(
            title="Original", content_md="independent", organisation=self.org, process=self.process
        )
        migration = importlib.import_module("core.migrations.0026_savedreport_series_id")
        migration.backfill_series(apps, None)
        self.report.refresh_from_db()
        child.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual(child.series_id, self.report.series_id)
        self.assertNotEqual(unrelated.series_id, self.report.series_id)

    def test_locked_editor_and_old_version_are_read_only(self):
        data = self.update().json()
        old = self.client.get(reverse("saved_report_editor", args=[self.report.pk]))
        self.assertFalse(old.context["can_edit"])
        self.assertContains(old, 'id="md-editor"')
        self.assertNotContains(old, 'id="btn-save"')
        current = SavedReport.objects.get(pk=data["report_id"])
        self.client.post(reverse("submit_report_for_review", args=[current.pk]))
        response = self.client.get(reverse("saved_report_editor", args=[current.pk]))
        self.assertFalse(response.context["can_edit"])
        self.assertNotContains(response, 'id="form-review"')

    def test_submission_from_tab_locked_by_another_request_returns_conflict(self):
        self.client.post(reverse("submit_report_for_review", args=[self.report.pk]))
        response = self.client.post(
            reverse("submit_report_for_review", args=[self.report.pk]),
            {
                "title": "Unsaved title",
                "content_md": "Unsaved later changes",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.report.refresh_from_db()
        self.assertEqual(self.report.content_md, "# Original evidence")


class ConcurrentReportTests(TransactionTestCase):
    def test_competing_review_submissions_create_one_locked_snapshot(self):
        org = Organisation.objects.create(name="Review concurrency")
        user = author("parallel-submitter", org)
        process = Process.objects.create(name="Site", organisation=org)
        report = SavedReport.objects.create(
            title="Report",
            content_md="Original",
            organisation=org,
            process=process,
            created_by=user,
        )

        def worker(index):
            close_old_connections()
            try:
                client = Client()
                client.force_login(user)
                return client.post(
                    reverse("submit_report_for_review", args=[report.pk]),
                    {
                        "title": "Review draft",
                        "content_md": f"Submitted text {index}",
                    },
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertCountEqual(results, [302, 409])
        self.assertEqual(ApprovalWorkflow.objects.count(), 1)
        self.assertEqual(SavedReport.objects.count(), 2)
        reviewed = SavedReport.objects.get(status="UNDER_REVIEW")
        self.assertEqual(reviewed.approval_workflow.object_id, reviewed.pk)
        self.assertIn(reviewed.content_md, ["Submitted text 0", "Submitted text 1"])

    def test_competing_edits_create_one_version_and_one_conflict(self):
        org = Organisation.objects.create(name="Concurrency")
        user = author("parallel-writer", org)
        report = SavedReport.objects.create(
            title="Report", content_md="Original", organisation=org, created_by=user
        )

        def worker(index):
            close_old_connections()
            try:
                SavedReport.create_version(report, f"Edit {index}", user, "MANUAL_EDIT")
                return "saved"
            except ValueError:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(SavedReport.objects.count(), 2)
        self.assertEqual(SavedReport.objects.get(parent_version=report).version_number, 2)
