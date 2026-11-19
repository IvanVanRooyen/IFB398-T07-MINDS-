"""Durable queue and real PostgreSQL race regressions, with model calls isolated."""

import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core.ai import jobs
from core.ai.composition import ReportCompositionForm
from core.models import ReportGenerationJob as Job
from core.models import ReportGenerationSubmission as Submission
from core.models import SavedReport
from core.tests import test_composition as fixtures


def setup_fixture(case):
    fixture = fixtures.CompositionTests(methodName="runTest")
    fixture.client = case.client
    fixture.setUp()
    return fixture


class ReportJobTests(TestCase):
    def setUp(self):
        self.fixture = setup_fixture(self)
        self.user = self.fixture.user

    def enqueue(self, request_id=None, **kwargs):
        return jobs.enqueue(self.fixture.form(**kwargs), request_id)

    def process_next(self, result="# Draft [D1]."):
        with patch("core.ai.composition.GraniteClient.complete", return_value=result):
            return jobs.run_next()

    def test_post_queues_without_calling_model(self):
        with patch("core.ai.composition.GraniteClient.complete") as model:
            response = self.client.post(
                reverse("generate_report"), self.fixture.payload(request_id=str(uuid.uuid4()))
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("?job=", response.url)
        model.assert_not_called()
        self.assertEqual(Job.objects.get().status, "QUEUED")
        self.assertFalse(SavedReport.objects.exists())

    def test_worker_saves_one_draft_and_updates_private_status(self):
        job = self.enqueue()
        self.process_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")
        self.assertEqual(job.attempts, 1)
        self.assertIsNone(job.run_token)
        self.assertEqual(SavedReport.objects.count(), 1)
        self.assertEqual(job.result.source_documents.get(), self.fixture.doc)
        response = self.client.get(reverse("report_list"), {"job_status": "1", "job": job.pk})
        self.assertEqual(response["Cache-Control"], "private, no-store")
        card = response.json()["jobs"][0]
        self.assertEqual(card["report_url"], reverse("saved_report_editor", args=[job.result_id]))
        self.assertNotIn("payload", card)
        self.assertNotIn("run_token", card)

    def test_submission_replay_returns_same_job_after_completion_and_source_edit(self):
        key = uuid.uuid4()
        job = self.enqueue(key)
        self.process_next()
        self.fixture.doc.extracted_text = "Changed source text"
        self.fixture.doc.save()
        self.assertEqual(self.enqueue(key).pk, job.pk)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_same_submission_key_with_changed_options_is_rejected(self):
        key = uuid.uuid4()
        self.enqueue(key)
        with self.assertRaises(ValidationError):
            self.enqueue(key, instructions="Different intent")
        self.assertEqual(Job.objects.count(), 1)

    def test_active_requests_coalesce_and_all_receipts_survive_completion(self):
        first, second = uuid.uuid4(), uuid.uuid4()
        a = self.enqueue(first)
        b = self.enqueue(second)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Submission.objects.count(), 2)
        self.process_next()
        self.assertEqual(self.enqueue(second).pk, a.pk)
        self.assertEqual(Job.objects.count(), 1)

    def test_cancel_queued_job_never_calls_provider(self):
        job = self.enqueue()
        jobs.cancel(self.user, job.pk)
        with patch("core.ai.composition.GraniteClient.complete") as model:
            self.assertIsNone(jobs.run_next())
        model.assert_not_called()
        self.assertEqual(Job.objects.get().status, "CANCELLED")
        self.assertFalse(SavedReport.objects.exists())

    def test_cancel_in_flight_discards_returned_text(self):
        job = self.enqueue()

        def provider(prompt):
            jobs.cancel(self.user, job.pk)
            return "# Late response [D1]"

        with patch("core.ai.composition.GraniteClient.complete", side_effect=provider):
            jobs.run_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "CANCELLED")
        self.assertFalse(SavedReport.objects.exists())

    def test_cancel_completed_job_does_not_remove_draft(self):
        job = self.enqueue()
        self.process_next()
        self.assertEqual(jobs.cancel(self.user, job.pk).status, "SUCCEEDED")
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_provider_failure_can_be_retried_and_duplicate_retry_does_not_add_jobs(self):
        job = self.enqueue()
        with patch(
            "core.ai.composition.GraniteClient.complete",
            side_effect=RuntimeError("provider unavailable"),
        ):
            jobs.run_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertTrue(job.retryable)
        jobs.retry(self.user, job.pk)
        jobs.retry(self.user, job.pk)
        self.process_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")
        self.assertEqual(job.attempts, 2)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_empty_provider_reply_is_retryable(self):
        job = self.enqueue()
        self.process_next("")
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertTrue(job.retryable)
        self.assertFalse(SavedReport.objects.exists())

    def test_retry_marks_changed_inputs_for_review_without_another_call(self):
        job = self.enqueue()
        with patch(
            "core.ai.composition.GraniteClient.complete", side_effect=RuntimeError("offline")
        ):
            jobs.run_next()
        self.fixture.doc.extracted_text = "Revised evidence"
        self.fixture.doc.save()
        refreshed = jobs.retry(self.user, job.pk)
        self.assertFalse(refreshed.retryable)
        self.assertEqual(refreshed.error_code, "INPUT_CHANGED")
        with patch("core.ai.composition.GraniteClient.complete") as model:
            self.assertIsNone(jobs.run_next())
        model.assert_not_called()

    def test_expired_worker_is_failed_and_stale_token_cannot_publish(self):
        job = self.enqueue()
        old = jobs.claim_next()
        Job.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.client.get(reverse("report_list"), {"job_status": "1"})
        job.refresh_from_db()
        self.assertEqual(job.error_code, "WORKER_INTERRUPTED")
        jobs.retry(self.user, job.pk)
        current = jobs.claim_next()
        with patch(
            "core.ai.composition.GraniteClient.complete", return_value="# Current result [D1]"
        ) as model:
            jobs.execute(*old)
            model.assert_not_called()
            jobs.execute(*current)
        self.assertEqual(SavedReport.objects.count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")

    def test_changed_source_before_start_fails_without_model_call(self):
        job = self.enqueue()
        self.fixture.doc.extracted_text = "Changed evidence"
        self.fixture.doc.save()
        with patch("core.ai.composition.GraniteClient.complete") as model:
            jobs.run_next()
        model.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertFalse(job.retryable)
        self.assertFalse(SavedReport.objects.exists())

    def test_changed_source_during_provider_call_prevents_publication(self):
        job = self.enqueue()

        def provider(prompt):
            self.fixture.doc.confidentiality = "jorc_restricted"
            self.fixture.doc.save()
            return "# Late response [D1]"

        with patch("core.ai.composition.GraniteClient.complete", side_effect=provider):
            jobs.run_next()
        self.assertFalse(SavedReport.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")

    def test_automatic_source_set_is_frozen_when_queued(self):
        job = self.enqueue(source_mode="project", document_ids=[])
        initial = set(job.payload["source_ids"])
        added = self.fixture.document("New later file", "SHOULD_NOT_JOIN_QUEUED_REQUEST")
        self.process_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")
        self.assertEqual(
            set(str(pk) for pk in job.result.source_documents.values_list("pk", flat=True)), initial
        )
        self.assertNotIn(str(added.pk), initial)

    def test_changed_prospect_inputs_reject_queued_request(self):
        form = ReportCompositionForm({}, user=self.user, prospect=self.fixture.prospect)
        job = jobs.enqueue(form)
        self.fixture.prospect.hypothesis = "Revised hypothesis"
        self.fixture.prospect.save()
        with patch("core.ai.composition.GraniteClient.complete") as model:
            jobs.run_next()
        model.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")

    def test_role_or_active_account_revocation_prevents_generation(self):
        for field, value in [("role", "VIEWER"), ("is_active", False)]:
            with self.subTest(field=field):
                job = self.enqueue(instructions=f"Case {field}")
                if field == "role":
                    self.user.profile.role = value
                    self.user.profile.save()
                else:
                    self.user.is_active = False
                    self.user.save()
                with patch("core.ai.composition.GraniteClient.complete") as model:
                    jobs.run_next()
                model.assert_not_called()
                job.refresh_from_db()
                self.assertEqual(job.error_code, "ACCESS_CHANGED")
                self.user.is_active = True
                self.user.save()
                self.user.profile.role = "GEOLOGIST_EXPL"
                self.user.profile.save()
        self.assertFalse(SavedReport.objects.exists())

    def test_tenant_transfer_during_generation_prevents_publication(self):
        job = self.enqueue()

        def provider(prompt):
            self.user.profile.organisation = self.fixture.other_org
            self.user.profile.save()
            return "# Late response"

        with patch("core.ai.composition.GraniteClient.complete", side_effect=provider):
            jobs.run_next()
        job.refresh_from_db()
        self.assertEqual(job.error_code, "ACCESS_CHANGED")
        self.assertFalse(SavedReport.objects.exists())

    def test_report_audit_failure_rolls_back_result_and_fails_job(self):
        job = self.enqueue()
        with (
            patch("core.ai.composition.GraniteClient.complete", return_value="# Draft"),
            patch("core.ai.composition.log_audit", side_effect=RuntimeError("audit unavailable")),
        ):
            jobs.run_next()
        self.assertFalse(SavedReport.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertIsNone(job.result_id)

    def test_completion_write_failure_rolls_back_the_created_draft(self):
        job = self.enqueue()
        real_save = Job.save

        def save(instance, *args, **kwargs):
            if instance.status == "SUCCEEDED":
                raise RuntimeError("completion write failed")
            return real_save(instance, *args, **kwargs)

        with patch.object(Job, "save", new=save):
            self.process_next()
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertIsNone(job.result_id)
        self.assertFalse(SavedReport.objects.exists())

    def test_other_users_and_transferred_or_lower_clearance_actors_cannot_read_job(self):
        job = self.enqueue()
        another = User.objects.create_user("another-author")
        another.profile.organisation = self.fixture.org
        another.profile.role = "ADMIN"
        another.profile.clearance_level = "JORC_APPROVED"
        another.profile.save()
        self.client.force_login(another)
        for url in [
            reverse("report_list") + f"?job={job.pk}",
            reverse("cancel_report_job", args=[job.pk]),
        ]:
            response = self.client.get(url) if "?job=" in url else self.client.post(url)
            self.assertEqual(response.status_code, 404)
        self.client.force_login(self.user)
        self.user.profile.clearance_level = "PUBLIC"
        self.user.profile.save()
        self.assertEqual(self.client.get(reverse("report_list"), {"job": job.pk}).status_code, 404)

    def test_success_result_link_respects_reclassified_source(self):
        job = self.enqueue()
        self.process_next()
        self.fixture.doc.confidentiality = "jorc_restricted"
        self.fixture.doc.save()
        job.refresh_from_db()
        self.assertIsNone(jobs.job_card(self.user, job)["report_url"])

    def test_resume_restores_options_and_selection_with_new_submission_key(self):
        job = self.enqueue(instructions="Restore my instructions")
        response = self.client.get(reverse("report_list"), {"resume": job.pk})
        self.assertContains(response, "Restore my instructions")
        self.assertEqual(response.context["selected_document_ids"], [str(self.fixture.doc.pk)])
        self.assertEqual(response.context["composition_form"]["tone"].value(), "technical")
        self.assertTrue(response.context["generation_request_id"])


class ConcurrentJobTests(TransactionTestCase):
    def setUp(self):
        self.fixture = setup_fixture(self)
        self.user = self.fixture.user

    def test_two_submissions_coalesce_with_receipts_under_database_lock(self):
        def submit(index):
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.user.pk)
                form = ReportCompositionForm(self.fixture.payload(), user=actor)
                return jobs.enqueue(form, uuid.uuid4()).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(Submission.objects.count(), 2)

    def test_two_workers_claim_once_and_cancel_during_call_discards_result(self):
        job = jobs.enqueue(self.fixture.form())
        started, release = Event(), Event()

        def provider(prompt):
            started.set()
            self.assertTrue(release.wait(10))
            return "# Returned draft"

        def work():
            close_old_connections()
            try:
                return jobs.run_next()
            finally:
                close_old_connections()

        with (
            patch("core.ai.composition.GraniteClient.complete", side_effect=provider),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(work)
            self.assertTrue(started.wait(10))
            self.assertIsNone(pool.submit(work).result(timeout=10))
            jobs.cancel(self.user, job.pk)
            release.set()
            first.result(timeout=10)
        self.assertFalse(SavedReport.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "CANCELLED")
        self.assertEqual(job.attempts, 1)

    def test_worker_once_command_processes_one_request(self):
        jobs.enqueue(self.fixture.form())
        with patch(
            "core.ai.composition.GraniteClient.complete", return_value="# Worker result [D1]"
        ):
            call_command("run_report_worker", once=True, stdout=io.StringIO())
        self.assertEqual(Job.objects.get().status, "SUCCEEDED")
        self.assertEqual(SavedReport.objects.count(), 1)

    def test_completion_wins_cancel_race_without_a_cancelled_saved_result(self):
        job = jobs.enqueue(self.fixture.form())
        entered, release, cancelling = Event(), Event(), Event()
        real_persist = jobs.persist_composition

        def persist(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return real_persist(*args, **kwargs)

        def work():
            close_old_connections()
            try:
                jobs.run_next()
            finally:
                close_old_connections()

        def cancel():
            close_old_connections()
            try:
                cancelling.set()
                return jobs.cancel(User.objects.get(pk=self.user.pk), job.pk).status
            finally:
                close_old_connections()

        with (
            patch("core.ai.composition.GraniteClient.complete", return_value="# Draft [D1]"),
            patch("core.ai.jobs.persist_composition", side_effect=persist),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            worker = pool.submit(work)
            self.assertTrue(entered.wait(10))
            cancellation = pool.submit(cancel)
            self.assertTrue(cancelling.wait(10))
            release.set()
            worker.result(timeout=10)
            self.assertEqual(cancellation.result(timeout=10), "SUCCEEDED")
        job.refresh_from_db()
        self.assertEqual(job.status, "SUCCEEDED")
        self.assertEqual(SavedReport.objects.count(), 1)
