"""
Unit tests for the report service module (the one with
fetch_process_bundle / build_structured_context / build_prompt /
generate_project_report / save_report).

IMPORTANT: Update MODULE_PATH below to match where this module actually lives
in your Django project. Every @patch in the file is built off that constant,
so once it's right, all the mocks resolve correctly.

These tests use SimpleTestCase + heavy mocking — no DB access required.

Run with:
    python manage.py test path.to.this.module
"""

import hashlib
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.ai.report_service import (
    CLEARANCE_LEVELS,
    CONFIDENTIALITY_MAP,
    build_prompt,
    build_structured_context,
    fetch_process_bundle,
    generate_project_report,
    save_report,
)

MODULE_PATH = "core.ai.report_service"

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class ConstantsTests(SimpleTestCase):
    def test_clearance_levels_are_ordered(self):
        self.assertEqual(CLEARANCE_LEVELS["PUBLIC"], 0)
        self.assertEqual(CLEARANCE_LEVELS["INTERNAL"], 1)
        self.assertEqual(CLEARANCE_LEVELS["CONFIDENTIAL"], 2)
        self.assertEqual(CLEARANCE_LEVELS["JORC_APPROVED"], 3)

    def test_confidentiality_map_is_ordered(self):
        self.assertEqual(CONFIDENTIALITY_MAP["public"], 0)
        self.assertEqual(CONFIDENTIALITY_MAP["internal"], 1)
        self.assertEqual(CONFIDENTIALITY_MAP["confidential"], 2)
        self.assertEqual(CONFIDENTIALITY_MAP["jorc_restricted"], 3)


# ---------------------------------------------------------------------------
# fetch_process_bundle (clearance filtering logic)
# ---------------------------------------------------------------------------


class FetchProcessBundleTests(SimpleTestCase):
    def _patch_models(self):
        proc_patcher = patch(f"{MODULE_PATH}.Process")
        doc_patcher = patch(f"{MODULE_PATH}.Document")
        mock_Process = proc_patcher.start()
        mock_Document = doc_patcher.start()
        self.addCleanup(proc_patcher.stop)
        self.addCleanup(doc_patcher.stop)
        return mock_Process, mock_Document

    def _filter_confidentiality(self, mock_Document):
        return set(mock_Document.objects.filter.call_args.kwargs["confidentiality__in"])

    def test_public_clearance_filters_to_public_only(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1", clearance_level="PUBLIC")
        self.assertEqual(self._filter_confidentiality(mock_Document), {"public"})

    def test_internal_clearance_includes_public_and_internal(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1", clearance_level="INTERNAL")
        self.assertEqual(
            self._filter_confidentiality(mock_Document),
            {"public", "internal"},
        )

    def test_confidential_clearance_includes_three_levels(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1", clearance_level="CONFIDENTIAL")
        self.assertEqual(
            self._filter_confidentiality(mock_Document),
            {"public", "internal", "confidential"},
        )

    def test_jorc_approved_clearance_includes_all_levels(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1", clearance_level="JORC_APPROVED")
        self.assertEqual(
            self._filter_confidentiality(mock_Document),
            {"public", "internal", "confidential", "jorc_restricted"},
        )

    def test_unknown_clearance_defaults_to_internal_level(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1", clearance_level="NOT_A_REAL_LEVEL")
        self.assertEqual(
            self._filter_confidentiality(mock_Document),
            {"public", "internal"},
        )

    def test_default_clearance_argument_is_internal(self):
        _, mock_Document = self._patch_models()
        fetch_process_bundle("p1")
        self.assertEqual(
            self._filter_confidentiality(mock_Document),
            {"public", "internal"},
        )

    def test_fetches_process_by_pk_with_organisation_join(self):
        mock_Process, _ = self._patch_models()
        fetch_process_bundle("proc-xyz")
        mock_Process.objects.select_related.assert_called_with("organisation")
        mock_Process.objects.select_related.return_value.get.assert_called_with(
            pk="proc-xyz"
        )

    def test_document_query_filters_by_returned_process(self):
        mock_Process, mock_Document = self._patch_models()
        mock_proc = MagicMock(name="proc")
        mock_Process.objects.select_related.return_value.get.return_value = mock_proc

        fetch_process_bundle("p1")

        self.assertEqual(
            mock_Document.objects.filter.call_args.kwargs["process"],
            mock_proc,
        )

    def test_returns_dict_with_process_and_docs_keys(self):
        mock_Process, _ = self._patch_models()
        mock_proc = MagicMock(name="proc")
        mock_Process.objects.select_related.return_value.get.return_value = mock_proc

        result = fetch_process_bundle("p1")

        self.assertIn("process", result)
        self.assertIn("docs", result)
        self.assertEqual(result["process"], mock_proc)
        self.assertIsInstance(result["docs"], list)


# ---------------------------------------------------------------------------
# build_structured_context
# ---------------------------------------------------------------------------


class BuildStructuredContextTests(SimpleTestCase):
    def _make_process(self, **overrides):
        p = MagicMock()
        p.id = overrides.get("id", 42)
        p.name = overrides.get("name", "Project Alpha")
        p.mode = overrides.get("mode", "exploration")
        p.commodity = overrides.get("commodity", "Cu")
        org = MagicMock()
        org.name = overrides.get("org_name", "Acme Mining")
        p.organisation = overrides.get("organisation", org)
        return p

    def _make_doc(self, **overrides):
        d = MagicMock()
        d.id = overrides.get("id", 1)
        d.title = overrides.get("title", "Sample Doc")
        d.timestamp = overrides.get("timestamp", "2024-01-15")
        d.doc_type = overrides.get("doc_type", "report")
        d.confidentiality = overrides.get("confidentiality", "internal")
        d.extracted_text = overrides.get("extracted_text", "Sample text.")
        d.checksum_sha256 = overrides.get("checksum_sha256", "abc123")
        d.created_at = overrides.get("created_at", None)
        created_by = MagicMock()
        created_by.username = overrides.get("username", "testuser")
        d.created_by = created_by
        file_mock = MagicMock()
        file_mock.name = overrides.get("file_name", "docs/sample.pdf")
        d.file = file_mock
        return d

    def test_includes_process_header_and_fields(self):
        bundle = {"process": self._make_process(), "docs": []}
        result = build_structured_context(bundle)

        self.assertIn("PROCESS", result)
        self.assertIn("id: 42", result)
        self.assertIn("name: Project Alpha", result)
        self.assertIn("mode: exploration", result)
        self.assertIn("commodity: Cu", result)
        self.assertIn("organisation: Acme Mining", result)

    def test_handles_none_organisation(self):
        p = self._make_process(organisation=None)
        result = build_structured_context({"process": p, "docs": []})
        self.assertIn("organisation: ", result)

    def test_handles_blank_process_fields(self):
        p = self._make_process(name=None, commodity=None)
        result = build_structured_context({"process": p, "docs": []})
        self.assertIn("name: ", result)
        self.assertIn("commodity: ", result)

    def test_includes_documents_header(self):
        bundle = {"process": self._make_process(), "docs": []}
        result = build_structured_context(bundle)
        self.assertIn("DOCUMENTS (latest up to 50)", result)

    def test_renders_document_entry(self):
        doc = self._make_doc(title="Q3 Geological Report")
        bundle = {"process": self._make_process(), "docs": [doc]}

        result = build_structured_context(bundle)

        self.assertIn("'Q3 Geological Report'", result)
        self.assertIn("uploaded_by: testuser", result)
        self.assertIn("conf: internal", result)
        self.assertIn("file: docs/sample.pdf", result)
        self.assertIn("checksum: abc123", result)

    def test_snippet_is_truncated_to_1000_chars(self):
        long_text = "x" * 2000
        doc = self._make_doc(extracted_text=long_text)
        bundle = {"process": self._make_process(), "docs": [doc]}

        result = build_structured_context(bundle)

        self.assertIn("x" * 1000, result)
        self.assertNotIn("x" * 1001, result)

    def test_snippet_newlines_are_replaced_with_spaces(self):
        doc = self._make_doc(extracted_text="line one\nline two\nline three")
        bundle = {"process": self._make_process(), "docs": [doc]}

        result = build_structured_context(bundle)

        self.assertIn("line one line two line three", result)
        snippet_chunk = result.split("text_snippet:")[1]
        self.assertNotIn("line one\nline two", snippet_chunk)

    def test_handles_none_extracted_text(self):
        doc = self._make_doc(extracted_text=None)
        bundle = {"process": self._make_process(), "docs": [doc]}
        result = build_structured_context(bundle)
        self.assertIn("text_snippet:", result)

    def test_renders_multiple_documents(self):
        docs = [
            self._make_doc(id=1, title="Doc One"),
            self._make_doc(id=2, title="Doc Two"),
            self._make_doc(id=3, title="Doc Three"),
        ]
        bundle = {"process": self._make_process(), "docs": docs}

        result = build_structured_context(bundle)

        self.assertIn("'Doc One'", result)
        self.assertIn("'Doc Two'", result)
        self.assertIn("'Doc Three'", result)


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class BuildPromptTests(SimpleTestCase):
    def test_includes_system_instructions(self):
        prompt = build_prompt("ctx")
        self.assertIn("technical writer", prompt)
        self.assertIn("Markdown", prompt)

    def test_includes_context_block(self):
        prompt = build_prompt("UNIQUE_CONTEXT_MARKER_12345")
        self.assertIn("CONTEXT:", prompt)
        self.assertIn("UNIQUE_CONTEXT_MARKER_12345", prompt)

    def test_includes_default_sections(self):
        prompt = build_prompt("ctx")
        for snippet in (
            "Project Summary",
            "Key Documents & Evidence",
            "Activities Timeline",
            "Commodities & Targets",
            "Data Gaps & Next Steps",
        ):
            self.assertIn(snippet, prompt)

    def test_custom_sections_replace_defaults(self):
        prompt = build_prompt("ctx", sections=["A. Intro", "B. Findings"])
        self.assertIn("A. Intro", prompt)
        self.assertIn("B. Findings", prompt)
        self.assertNotIn("Project Summary", prompt)

    def test_custom_as_of_appears_in_output(self):
        prompt = build_prompt("ctx", as_of="2030-01-15")
        self.assertIn("DATE: 2030-01-15", prompt)

    @patch(f"{MODULE_PATH}.datetime")
    def test_default_as_of_uses_utcnow(self, mock_datetime):
        mock_datetime.utcnow.return_value.strftime.return_value = "2024-12-25"

        prompt = build_prompt("ctx")

        mock_datetime.utcnow.return_value.strftime.assert_called_with("%Y-%m-%d")
        self.assertIn("DATE: 2024-12-25", prompt)

    def test_default_date_format_is_yyyy_mm_dd(self):
        prompt = build_prompt("ctx")
        self.assertRegex(prompt, r"DATE: \d{4}-\d{2}-\d{2}")

    def test_sections_are_rendered_as_bullets(self):
        prompt = build_prompt("ctx", sections=["X. First"])
        self.assertIn("- X. First", prompt)


class GenerateProjectReportTests(SimpleTestCase):
    def _patch_all(self):
        fetch_p = patch(f"{MODULE_PATH}.fetch_process_bundle")
        retrieve_p = patch(f"{MODULE_PATH}.retrieve_context")
        client_p = patch(f"{MODULE_PATH}.GraniteClient")

        mock_fetch = fetch_p.start()
        mock_retrieve = retrieve_p.start()
        mock_client_cls = client_p.start()

        self.addCleanup(fetch_p.stop)
        self.addCleanup(retrieve_p.stop)
        self.addCleanup(client_p.stop)

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        return mock_fetch, mock_retrieve, mock_client_cls, mock_client

    def test_orchestrates_full_pipeline(self):
        mock_fetch, mock_retrieve, mock_client_cls, mock_client = self._patch_all()

        proc = MagicMock()
        proc.name = "Test Project"
        proc.commodity = "Au"
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.id = "doc-1"
        doc2.id = "doc-2"
        mock_fetch.return_value = {"process": proc, "docs": [doc1, doc2]}
        mock_retrieve.return_value = "retrieved chunks"
        mock_client.complete.return_value = "# Generated Report"

        text, doc_ids = generate_project_report("p-1", clearance_level="CONFIDENTIAL")

        mock_fetch.assert_called_once_with("p-1", clearance_level="CONFIDENTIAL")
        mock_retrieve.assert_called_once_with(
            query="Test Project Au",
            process=proc,
            clearance_level="CONFIDENTIAL",
            max_chunks=8,
        )
        mock_client_cls.assert_called_once_with()
        mock_client.complete.assert_called_once()

        self.assertEqual(text, "# Generated Report")
        self.assertEqual(doc_ids, ["doc-1", "doc-2"])

    def test_default_clearance_is_internal(self):
        mock_fetch, mock_retrieve, _, mock_client = self._patch_all()
        proc = MagicMock()
        proc.name = ""
        proc.commodity = ""
        mock_fetch.return_value = {"process": proc, "docs": []}
        mock_retrieve.return_value = ""
        mock_client.complete.return_value = ""

        generate_project_report("p-1")

        mock_fetch.assert_called_once_with("p-1", clearance_level="INTERNAL")
        self.assertEqual(mock_retrieve.call_args.kwargs["clearance_level"], "INTERNAL")

    def test_handles_none_name_and_commodity_in_query(self):
        mock_fetch, mock_retrieve, _, mock_client = self._patch_all()
        proc = MagicMock()
        proc.name = None
        proc.commodity = None
        mock_fetch.return_value = {"process": proc, "docs": []}
        mock_retrieve.return_value = ""
        mock_client.complete.return_value = ""

        generate_project_report("p-1")

        # `f"{None or ''} {None or ''}".strip()` == ""
        self.assertEqual(mock_retrieve.call_args.kwargs["query"], "")

    def test_doc_ids_are_stringified(self):
        mock_fetch, mock_retrieve, _, mock_client = self._patch_all()
        proc = MagicMock()
        proc.name = "n"
        proc.commodity = "c"
        d = MagicMock()
        d.id = 12345  # (should resolve to string despite being numeric)
        mock_fetch.return_value = {"process": proc, "docs": [d]}
        mock_retrieve.return_value = ""
        mock_client.complete.return_value = ""

        _, doc_ids = generate_project_report("p-1")

        self.assertEqual(doc_ids, ["12345"])

    def test_prompt_passed_to_client_includes_metadata_and_excerpts(self):
        mock_fetch, mock_retrieve, _, mock_client = self._patch_all()
        proc = MagicMock()
        proc.name = "ProjN"
        proc.commodity = "Ag"
        mock_fetch.return_value = {"process": proc, "docs": []}
        mock_retrieve.return_value = "EXCERPT_MARKER"
        mock_client.complete.return_value = ""

        generate_project_report("p-1")

        prompt_arg = mock_client.complete.call_args.args[0]
        self.assertIn("DOCUMENT CONTENT EXCERPTS:", prompt_arg)
        self.assertIn("EXCERPT_MARKER", prompt_arg)
        self.assertIn("PROCESS", prompt_arg)


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------


class SaveReportTests(SimpleTestCase):
    def _patch_all(self):
        sr_p = patch(f"{MODULE_PATH}.SavedReport")
        audit_log_p = patch(f"{MODULE_PATH}.AuditLog")
        log_audit_p = patch(f"{MODULE_PATH}.log_audit")

        mock_SavedReport = sr_p.start()
        mock_AuditLog = audit_log_p.start()
        mock_log_audit = log_audit_p.start()

        self.addCleanup(sr_p.stop)
        self.addCleanup(audit_log_p.stop)
        self.addCleanup(log_audit_p.stop)

        mock_AuditLog.ActionType.CREATE = "CREATE"
        return mock_SavedReport, mock_AuditLog, mock_log_audit

    def _set_existing(self, mock_SavedReport, existing):
        (
            mock_SavedReport.objects.filter.return_value.order_by.return_value.first.return_value
        ) = existing

    def test_first_version_when_no_existing_report(self):
        mock_SavedReport, _, mock_log_audit = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        new_report = MagicMock()
        new_report.version_number = 1
        mock_SavedReport.objects.create.return_value = new_report

        proc, org, user = MagicMock(), MagicMock(), MagicMock()

        result = save_report(
            proc,
            org,
            "My Title",
            "# content",
            user,
            reason="GENERATED",
            summary="initial",
        )

        mock_SavedReport.objects.create.assert_called_once()
        mock_SavedReport.create_version.assert_not_called()

        kwargs = mock_SavedReport.objects.create.call_args.kwargs
        self.assertEqual(kwargs["process"], proc)
        self.assertEqual(kwargs["organisation"], org)
        self.assertEqual(kwargs["title"], "My Title")
        self.assertEqual(kwargs["content_md"], "# content")
        self.assertEqual(kwargs["created_by"], user)
        self.assertEqual(kwargs["version_number"], 1)
        self.assertEqual(kwargs["change_reason"], "GENERATED")
        self.assertEqual(kwargs["change_summary"], "initial")
        self.assertEqual(kwargs["clearance_level"], "INTERNAL")
        self.assertIn("content_hash", kwargs)

        mock_log_audit.assert_called_once()
        self.assertEqual(result, new_report)

    def test_creates_new_version_when_one_exists(self):
        mock_SavedReport, _, mock_log_audit = self._patch_all()
        existing = MagicMock()
        existing.version_number = 2
        self._set_existing(mock_SavedReport, existing)

        new_version = MagicMock()
        new_version.version_number = 3
        mock_SavedReport.create_version.return_value = new_version

        user = MagicMock()
        result = save_report(
            MagicMock(),
            MagicMock(),
            "Title",
            "# md",
            user,
            reason="UPDATED",
            summary="fix typo",
        )

        mock_SavedReport.create_version.assert_called_once_with(
            parent=existing,
            content_md="# md",
            user=user,
            reason="UPDATED",
            summary="fix typo",
        )
        mock_SavedReport.objects.create.assert_not_called()
        mock_log_audit.assert_called_once()
        self.assertEqual(result, new_version)

    def test_content_hash_is_sha256_of_content_md(self):
        mock_SavedReport, _, _ = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        mock_SavedReport.objects.create.return_value = MagicMock(version_number=1)

        content = "# Some report content"
        expected = hashlib.sha256(content.encode()).hexdigest()

        save_report(MagicMock(), MagicMock(), "T", content, MagicMock())

        kwargs = mock_SavedReport.objects.create.call_args.kwargs
        self.assertEqual(kwargs["content_hash"], expected)

    def test_filters_existing_by_process_and_title(self):
        mock_SavedReport, _, _ = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        mock_SavedReport.objects.create.return_value = MagicMock(version_number=1)

        proc = MagicMock()
        save_report(proc, MagicMock(), "Unique Title", "x", MagicMock())

        kwargs = mock_SavedReport.objects.filter.call_args.kwargs
        self.assertEqual(kwargs["process"], proc)
        self.assertEqual(kwargs["title"], "Unique Title")

    def test_orders_existing_by_version_descending(self):
        mock_SavedReport, _, _ = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        mock_SavedReport.objects.create.return_value = MagicMock(version_number=1)

        save_report(MagicMock(), MagicMock(), "T", "x", MagicMock())

        order_call = mock_SavedReport.objects.filter.return_value.order_by
        order_call.assert_called_once_with("-version_number")

    def test_audit_log_records_action_and_description(self):
        mock_SavedReport, mock_AuditLog, mock_log_audit = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        created = MagicMock()
        created.version_number = 1
        mock_SavedReport.objects.create.return_value = created

        user = MagicMock()
        save_report(MagicMock(), MagicMock(), "Some Title", "x", user)

        kwargs = mock_log_audit.call_args.kwargs
        self.assertEqual(kwargs["user"], user)
        self.assertEqual(kwargs["action"], mock_AuditLog.ActionType.CREATE)
        self.assertEqual(kwargs["obj"], created)
        self.assertIn("Some Title", kwargs["description"])
        self.assertIn("v1", kwargs["description"])

    def test_default_reason_and_summary(self):
        mock_SavedReport, _, _ = self._patch_all()
        self._set_existing(mock_SavedReport, None)
        mock_SavedReport.objects.create.return_value = MagicMock(version_number=1)

        save_report(MagicMock(), MagicMock(), "T", "x", MagicMock())

        kwargs = mock_SavedReport.objects.create.call_args.kwargs
        self.assertEqual(kwargs["change_reason"], "GENERATED")
        self.assertEqual(kwargs["change_summary"], "")
