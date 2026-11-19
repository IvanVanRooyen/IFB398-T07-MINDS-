
"""HTTP/database regressions for the authorization failures found in review.

Requests use real users, querysets, templates, middleware and persisted state.
Generation is stubbed where needed; a provenance test isolates its metadata
bundle. Storage is isolated from the application's S3.
"""

import hashlib
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.ai.jobs import run_next
from core.ai.retrieval import query_chunks
from core.forms import DocumentForm
from core.models import (
    AuditLog,
    DocLink,
    Document,
    DocumentChunk,
    Drillhole,
    Organisation,
    Process,
    Prospect,
    Sample,
    SavedReport,
    Survey,
    log_audit,
)


class AccessSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="First organisation")
        cls.other_org = Organisation.objects.create(name="Second organisation")
        cls.project = Process.objects.create(name="First project", organisation=cls.org)
        cls.other = Process.objects.create(name="Second project", organisation=cls.other_org)
        cls.local_other = Process.objects.create(
            name="Another first-org project", organisation=cls.org
        )
        cls.author = cls.make_user("author", cls.org, "GEOLOGIST_EXPL", "CONFIDENTIAL")
        cls.viewer = cls.make_user("viewer", cls.org, "VIEWER", "PUBLIC")
        cls.foreign = cls.make_user("foreign", cls.other_org, "ADMIN", "JORC_APPROVED")
        cls.unassigned = cls.make_user("unassigned", None, "ADMIN", "JORC_APPROVED")
        cls.doc = Document.objects.create(
            title="CONFIDENTIAL evidence",
            organisation=cls.org,
            process=cls.project,
            confidentiality="confidential",
            file="",
            analysis_text="PRIVATE analysis",
            checksum_sha256="a" * 64,
        )
        cls.public_doc = Document.objects.create(
            title="Public evidence",
            organisation=cls.org,
            process=cls.project,
            confidentiality="public",
            file="",
            checksum_sha256="b" * 64,
        )
        cls.prospect = Prospect.objects.create(
            name="First prospect",
            organisation=cls.org,
            process=cls.project,
            hypothesis="Test hypothesis",
            objective="Test objective",
            geom=Point(151, -27, srid=4326),
        )
        cls.drillhole = Drillhole.objects.create(
            name="DH-001", organisation=cls.org, process=cls.project, prospect=cls.prospect
        )
        cls.sample = Sample.objects.create(name="Sample", organisation=cls.org, process=cls.project)
        cls.survey = Survey.objects.create(name="Survey", organisation=cls.org, process=cls.project)
        cls.report = SavedReport.objects.create(
            title="CONFIDENTIAL report",
            organisation=cls.org,
            process=cls.project,
            content_md="PRIVATE report body",
            clearance_level="CONFIDENTIAL",
            created_by=cls.author,
        )
        cls.report.source_documents.add(cls.doc)

    @staticmethod
    def make_user(name, organisation, role, clearance):
        user = User.objects.create_user(name, password="test-only")
        user.profile.organisation = organisation
        user.profile.role = role
        user.profile.clearance_level = clearance
        user.profile.save()
        return user

    def setUp(self):
        cache.clear()

    def assert_denied(self, response):
        self.assertIn(response.status_code, (403, 404))

    def record_urls(self):
        return [
            reverse("document_detail", args=[self.doc.pk]),
            reverse("download_document", args=[self.doc.pk]),
            reverse("document_analysis_detail", args=[self.doc.pk]),
            reverse("export_document_analysis", args=[self.doc.pk]) + "?format=docx",
            reverse("prospect_detail", args=[self.prospect.pk]),
            reverse("drillhole_detail", args=[self.drillhole.pk]),
            reverse("sample_detail", args=[self.sample.pk]),
            reverse("survey_detail", args=[self.survey.pk]),
            reverse("saved_report_editor", args=[self.report.pk]),
            reverse("report_version_detail", args=[self.report.pk]),
            reverse("report_detail", args=[self.report.pk]),
        ]

    def test_foreign_and_unassigned_users_cannot_read_records(self):
        for user in (self.foreign, self.unassigned):
            self.client.force_login(user)
            for url in self.record_urls():
                with self.subTest(user=user.username, url=url):
                    self.assert_denied(self.client.get(url))

    def test_profileless_user_cannot_read_records(self):
        user = User.objects.create_user("profileless")
        user.profile.delete()
        self.client.force_login(User.objects.get(pk=user.pk))
        for url in self.record_urls():
            with self.subTest(url=url):
                self.assert_denied(self.client.get(url))

    def test_low_clearance_cannot_read_restricted_documents_or_reports(self):
        self.client.force_login(self.viewer)
        for name, pk in (
            ("document_detail", self.doc.pk),
            ("download_document", self.doc.pk),
            ("document_analysis_detail", self.doc.pk),
            ("export_document_analysis", self.doc.pk),
            ("saved_report_editor", self.report.pk),
            ("report_version_detail", self.report.pk),
        ):
            with self.subTest(name=name):
                self.assert_denied(self.client.get(reverse(name, args=[pk])))

    def test_all_document_and_report_lists_respect_clearance(self):
        self.client.force_login(self.viewer)
        urls = [
            reverse(name)
            for name in (
                "home",
                "dashboard",
                "documents",
                "ai_insights",
                "report_list",
                "all_reports_history",
                "document_analysis_page",
            )
        ]
        urls += [
            reverse("project_detail", args=[self.project.pk]),
            reverse("report_history", args=[self.project.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, self.doc.title)
                self.assertNotContains(response, self.report.title)

    def test_clearance_cache_isolation_in_both_directions(self):
        for first, second in ((self.author, self.viewer), (self.viewer, self.author)):
            cache.clear()
            self.client.force_login(first)
            self.client.get(reverse("documents"))
            self.client.force_login(second)
            response = self.client.get(reverse("documents"))
            if second == self.viewer:
                self.assertNotContains(response, self.doc.title)
            else:
                self.assertContains(response, self.doc.title)

    def test_existing_underclassified_report_is_hidden_if_source_is_restricted(self):
        self.report.clearance_level = "PUBLIC"
        self.report.save(update_fields=["clearance_level"])
        self.client.force_login(self.viewer)
        self.assert_denied(self.client.get(reverse("report_version_detail", args=[self.report.pk])))
        self.assertNotContains(self.client.get(reverse("all_reports_history")), self.report.title)

    def test_viewer_cannot_mutate_records_or_submit_review(self):
        self.client.force_login(self.viewer)
        requests = [
            (
                reverse("link_drillhole"),
                {"prospect_id": self.prospect.pk, "drillhole_id": self.drillhole.pk},
            ),
            (reverse("unlink_drillhole", args=[self.drillhole.pk]), {}),
            (
                reverse("bulk_link_drillholes"),
                {"prospect_id": self.prospect.pk, "drillhole_id": [self.drillhole.pk]},
            ),
            (
                reverse("save_report"),
                {"process_id": self.project.pk, "title": "Injected", "content_md": "text"},
            ),
            (reverse("create_tenement"), {"name": "Injected", "process": self.project.pk}),
            (reverse("edit_process_geometry", args=[self.project.pk]), {}),
            (reverse("submit_report_for_review", args=[self.report.pk]), {}),
        ]
        for url, data in requests:
            with self.subTest(url=url):
                self.assert_denied(self.client.post(url, data))
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "DRAFT")

    def test_foreign_admin_cannot_mutate_or_export_report(self):
        self.client.force_login(self.foreign)
        for name in (
            "submit_report_for_review",
            "update_saved_report",
            "approve_report",
            "reject_report",
            "publish_report",
            "assign_report_prospect",
        ):
            with self.subTest(name=name):
                self.assert_denied(
                    self.client.post(
                        reverse(name, args=[self.report.pk]),
                        {"title": "Injected", "content_md": "Injected"},
                    )
                )
        self.assert_denied(
            self.client.post(
                reverse("export_report"),
                {"report_id": self.report.pk, "format": "docx", "content_md": "text"},
            )
        )
        self.assert_denied(
            self.client.post(
                reverse("save_report"),
                {"process_id": self.project.pk, "title": "Injected", "content_md": "text"},
            )
        )
        self.assertFalse(SavedReport.objects.filter(title="Injected").exists())

    def test_other_author_cannot_submit_someone_elses_draft(self):
        peer = self.make_user("peer", self.org, "GEOLOGIST_EXPL", "CONFIDENTIAL")
        self.client.force_login(peer)
        self.assert_denied(
            self.client.post(reverse("submit_report_for_review", args=[self.report.pk]))
        )
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "DRAFT")

    def test_linking_validates_both_target_and_source(self):
        self.client.force_login(self.foreign)
        self.assert_denied(
            self.client.post(
                reverse("link_drillhole"),
                {"prospect_id": self.prospect.pk, "drillhole_id": self.drillhole.pk},
            )
        )
        self.assert_denied(
            self.client.post(
                reverse("create_doc_link"),
                {
                    "content_type_label": "prospect",
                    "object_id": self.prospect.pk,
                    "document_id": self.doc.pk,
                },
            )
        )
        self.assertFalse(DocLink.objects.exists())

    def test_same_organisation_cross_project_link_is_rejected(self):
        foreign_project_hole = Drillhole.objects.create(
            name="Other project", organisation=self.org, process=self.local_other
        )
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("link_drillhole"),
            {"prospect_id": self.prospect.pk, "drillhole_id": foreign_project_hole.pk},
        )
        self.assertEqual(response.status_code, 400)
        foreign_project_hole.refresh_from_db()
        self.assertIsNone(foreign_project_hole.prospect_id)

    def test_author_can_link_and_unlink_own_records(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("create_doc_link"),
            {
                "content_type_label": "prospect",
                "object_id": self.prospect.pk,
                "document_id": self.doc.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        link = DocLink.objects.get()
        self.assertEqual(
            self.client.post(reverse("delete_doc_link", args=[link.pk])).status_code, 200
        )
        self.assertFalse(DocLink.objects.exists())

    def test_upload_choices_and_post_validation_are_scoped(self):
        form = DocumentForm(organisation=self.org, user=self.author)
        self.assertNotIn(self.other, form.fields["process"].queryset)
        self.assertNotIn(self.other_org, form.fields["organisation"].queryset)
        form = DocumentForm(
            {
                "title": "Upload",
                "organisation": self.other_org.pk,
                "process": self.other.pk,
                "confidentiality": "internal",
            },
            {"file": SimpleUploadedFile("test.pdf", b"test")},
            organisation=self.org,
            user=self.author,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("organisation", form.errors)
        self.assertIn("process", form.errors)

    def test_download_streams_private_file_instead_of_redirecting(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            override_settings(
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": directory},
                    },
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                    },
                }
            ),
        ):
            self.public_doc.file.save(
                "private.txt", SimpleUploadedFile("private.txt", b"private file bytes")
            )
            self.client.force_login(self.viewer)
            response = self.client.get(reverse("download_document", args=[self.public_doc.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"private file bytes")
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertNotIn("Location", response)

    def test_generated_reports_keep_caller_clearance_and_open_saved_record(self):
        self.client.force_login(self.author)
        with patch(
            "core.ai.composition.GraniteClient.complete",
            return_value="Generated confidential text",
        ):
            response = self.client.post(
                reverse("generate_report"),
                {"process_id": self.project.pk, "report_title": "Generated", "source_mode": "selected", "document_ids": [str(self.doc.pk)]},
            )
            run_next()
        report = SavedReport.objects.get(title="Generated")
        self.assertEqual(report.clearance_level, "CONFIDENTIAL")
        self.assertEqual(list(report.source_documents.all()), [self.doc])
        self.assertIn(reverse("report_list") + "?job=", response.url)

    def test_prospect_generation_and_regeneration_do_not_lower_clearance(self):
        self.client.force_login(self.author)
        for text in ("First generation", "Second generation"):
            with patch(
                "core.ai.composition.GraniteClient.complete", return_value=text
            ):
                response = self.client.post(
                    reverse("generate_prospect_report", args=[self.prospect.pk]),
                    {"report_title": "Prospect generated"},
                )
                run_next()
            self.assertEqual(response.status_code, 302)
        reports = SavedReport.objects.filter(title="Prospect generated")
        self.assertEqual(reports.count(), 2)
        self.assertEqual(set(reports.values_list("clearance_level", flat=True)), {"CONFIDENTIAL"})

    def test_unchanged_regenerated_content_cannot_reuse_underclassified_parent(self):
        self.report.content_hash = hashlib.sha256(self.report.content_md.encode()).hexdigest()
        self.report.clearance_level = "INTERNAL"
        self.report.save()
        version = SavedReport.create_version(
            self.report,
            self.report.content_md,
            self.author,
            "REGENERATED",
            clearance_level="CONFIDENTIAL",
        )
        self.assertNotEqual(version.pk, self.report.pk)
        self.assertEqual(version.clearance_level, "CONFIDENTIAL")

    def test_ai_retrieval_excludes_mismatched_tenants_and_old_versions(self):
        DocumentChunk.objects.create(
            document=self.doc, process=self.project, chunk_index=0, text="gold valid"
        )
        foreign_doc = Document.objects.create(
            title="Foreign",
            organisation=self.other_org,
            process=self.other,
            confidentiality="public",
            file="",
        )
        DocumentChunk.objects.create(
            document=foreign_doc, process=self.project, chunk_index=0, text="gold foreign"
        )
        self.public_doc.is_latest = False
        self.public_doc.save()
        DocumentChunk.objects.create(
            document=self.public_doc, process=self.project, chunk_index=0, text="gold old"
        )
        self.assertEqual(
            [
                c.text
                for c in query_chunks("gold", process=self.project, clearance_level="CONFIDENTIAL")
            ],
            ["gold valid"],
        )
        self.assertEqual(query_chunks("gold"), [])
        self.assertEqual(query_chunks("gold", process=self.project, clearance_level="INVALID"), [])

    def test_analysis_requires_post_and_cannot_be_run_by_viewer(self):
        self.client.force_login(self.author)
        self.assertEqual(
            self.client.get(reverse("analyze_document", args=[self.doc.pk])).status_code, 405
        )
        self.client.force_login(self.viewer)
        self.assert_denied(self.client.post(reverse("analyze_document", args=[self.public_doc.pk])))

    def test_unscoped_admin_is_reserved_for_platform_superusers(self):
        self.author.is_staff = True
        self.author.save()
        self.author.user_permissions.add(Permission.objects.get(codename="view_document"))
        self.client.force_login(self.author)
        self.assertEqual(self.client.get("/admin/core/document/").status_code, 302)
        platform_admin = User.objects.create_superuser("platform", password="test-only")
        self.client.force_login(platform_admin)
        self.assertEqual(self.client.get("/admin/core/document/").status_code, 200)

    def test_audit_history_keeps_tenant_and_clearance_after_actor_transfer(self):
        log_audit(self.author, AuditLog.ActionType.VIEW, self.doc, "PRIVATE historical event")
        self.author.profile.organisation = self.other_org
        self.author.profile.save()
        admin = self.make_user("local-admin", self.org, "ADMIN", "CONFIDENTIAL")
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("audit_log")), "PRIVATE historical event")
        self.client.force_login(self.foreign)
        self.assertNotContains(self.client.get(reverse("audit_log")), "PRIVATE historical event")
        admin.profile.clearance_level = "PUBLIC"
        admin.profile.save()
        self.client.force_login(admin)
        self.assertNotContains(self.client.get(reverse("audit_log")), "PRIVATE historical event")

    def test_geospatial_metadata_cannot_break_out_of_json_script(self):
        self.drillhole.name = "</script><script>window.__mindsReviewXss=1</script>"
        self.drillhole.collar_location = Point(151, -27, srid=4326)
        self.drillhole.save()
        self.client.force_login(self.author)
        response = self.client.get(reverse("prospect_detail", args=[self.prospect.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.drillhole.name)
        self.assertContains(response, r"\u003C/script\u003E")

    def test_warm_document_cache_does_not_expose_reclassified_document(self):
        self.client.force_login(self.viewer)
        self.assertContains(self.client.get(reverse("documents")), self.public_doc.title)
        self.public_doc.confidentiality = "confidential"
        self.public_doc.save(update_fields=["confidentiality"])
        self.assertNotContains(self.client.get(reverse("documents")), self.public_doc.title)

    def test_report_cache_rechecks_source_classification(self):
        from core.views import _get_cached_report_bundle

        with patch(
            "core.views.generate_project_report",
            return_value=("Public old text", [str(self.public_doc.pk)]),
        ):
            _get_cached_report_bundle(str(self.project.pk), "PUBLIC")
        self.public_doc.confidentiality = "confidential"
        self.public_doc.save(update_fields=["confidentiality"])
        with patch(
            "core.views.generate_project_report", return_value=("No public evidence", [])
        ) as generate:
            result = _get_cached_report_bundle(str(self.project.pk), "PUBLIC")
        generate.assert_called_once()
        self.assertEqual(result["md"], "No public evidence")

    def test_generated_manifest_includes_documents_used_only_as_chunk_sources(self):
        from core.ai.report_service import generate_project_report

        DocumentChunk.objects.create(
            document=self.doc,
            process=self.project,
            chunk_index=0,
            text="First project gold evidence",
        )
        with (
            patch(
                "core.ai.report_service.fetch_process_bundle",
                return_value={"process": self.project, "docs": []},
            ),
            patch("core.ai.report_service.GraniteClient") as client,
        ):
            client.return_value.complete.return_value = "Grounded text"
            _, ids = generate_project_report(str(self.project.pk), "CONFIDENTIAL")
        self.assertEqual(ids, [str(self.doc.pk)])

    def test_unknown_document_classification_is_denied(self):
        self.doc.confidentiality = "unrecognised"
        self.doc.save(update_fields=["confidentiality"])
        self.client.force_login(self.author)
        self.assert_denied(self.client.get(reverse("document_detail", args=[self.doc.pk])))

    def test_malformed_project_id_is_rejected_without_saving(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("save_report"),
            {"process_id": "not-a-uuid", "title": "Bad project", "content_md": "text"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SavedReport.objects.filter(title="Bad project").exists())

    def test_data_manager_can_open_import_but_cannot_import_into_foreign_project(self):
        manager = self.make_user("manager", self.org, "DATA_MANAGER", "CONFIDENTIAL")
        self.client.force_login(manager)
        self.assertEqual(self.client.get(reverse("drillhole_import")).status_code, 200)
        with patch("core.views.run_drillhole_import") as importer:
            self.client.post(
                reverse("drillhole_import"),
                {
                    "organisation": self.other_org.pk,
                    "process": self.other.pk,
                    "file": SimpleUploadedFile("data.xlsx", b"placeholder"),
                },
            )
        importer.assert_not_called()

    def test_author_can_analyse_permitted_document_using_post(self):
        self.doc.extracted_text = "Source document content"
        self.doc.save()
        self.client.force_login(self.author)
        with patch("core.views.GraniteClient") as client:
            client.return_value.complete.return_value = "Authorised analysis"
            self.assertEqual(
                self.client.post(reverse("analyze_document", args=[self.doc.pk])).status_code, 302
            )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.analysis_text, "Authorised analysis")

    def test_deleted_records_keep_audit_tenant_snapshot(self):
        log_audit(
            self.author, AuditLog.ActionType.DELETE, self.public_doc, "Original record deletion"
        )
        self.public_doc.delete()
        event = AuditLog.objects.get(description="Original record deletion")
        self.assertEqual(event.organisation_id, self.org.pk)
        self.assertEqual(event.clearance_level, "PUBLIC")

    def test_legacy_document_with_foreign_project_is_hidden(self):
        self.public_doc.process = self.other
        self.public_doc.save(update_fields=["process"])
        self.client.force_login(self.viewer)
        self.assert_denied(self.client.get(reverse("document_detail", args=[self.public_doc.pk])))
        self.assertNotContains(self.client.get(reverse("documents")), self.public_doc.title)

    def test_viewer_cannot_trigger_generation_through_get_routes(self):
        self.client.force_login(self.viewer)
        for name in ("report_editor", "project_report_pdf", "project_report_docx"):
            with self.subTest(name=name), patch("core.views.generate_project_report") as generate:
                self.assert_denied(self.client.get(reverse(name, args=[self.project.pk])))
                generate.assert_not_called()

    def test_report_audit_event_preserves_source_classification(self):
        self.report.clearance_level = "PUBLIC"
        self.report.save(update_fields=["clearance_level"])
        log_audit(self.author, AuditLog.ActionType.VIEW, self.report, "Sensitive report event")
        event = AuditLog.objects.get(description="Sensitive report event")
        self.assertEqual(event.clearance_level, "CONFIDENTIAL")

    def test_historical_audit_backfill_respects_report_sources(self):
        from importlib import import_module

        from django.apps import apps
        from django.contrib.contenttypes.models import ContentType

        self.report.clearance_level = "PUBLIC"
        self.report.save(update_fields=["clearance_level"])
        event = AuditLog.objects.create(user=self.author, action="VIEW", content_type=ContentType.objects.get_for_model(SavedReport), object_id=self.report.pk)
        migration = import_module("core.migrations.0025_audit_access_context")
        migration.backfill_context(apps, None)
        event.refresh_from_db()
        self.assertEqual(event.organisation_id, self.org.pk)
        self.assertEqual(event.clearance_level, "CONFIDENTIAL")
