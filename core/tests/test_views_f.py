"""
Coverage:
    submit_report_for_review, approve_report, reject_report, publish_report,
    report_history, report_version_detail, all_reports_history,
    export_report, report_detail,
    audit_log_view, approval_workflows_list,
    document_analysis_page, analyze_document, export_document_analysis
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.test import RequestFactory, TestCase
from django.utils.datastructures import MultiValueDict

from core import views

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------


class _ViewTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="alice", password="pw", email="alice@example.com"
        )
        self.org = MagicMock(name="Org", id=7)
        self.profile = MagicMock(
            organisation=self.org,
            role="ADMIN",
            clearance_level="PUBLIC",
            can_approve_jorc=True,
            can_approve_valmin=True,
        )

    def _authed_request(self, method="get", path="/", files=None, **kwargs):
        request = getattr(self.factory, method)(path, **kwargs)
        request.user = self.user
        type(request.user).profile = property(lambda s, p=self.profile: p)
        if files is not None:
            normalised = {
                k: (v if isinstance(v, list) else [v]) for k, v in files.items()
            }
            request._files = MultiValueDict(normalised)
        return request

    @staticmethod
    def _chainable_qs(result, count=None):
        qs = MagicMock(name="QuerySet")
        for method in (
            "filter",
            "exclude",
            "order_by",
            "select_related",
            "prefetch_related",
            "annotate",
            "distinct",
            "values_list",
            "values",
            "set",
            "update",
            "iterator",
        ):
            getattr(qs, method).return_value = qs
        qs.count.return_value = (
            count
            if count is not None
            else (len(result) if hasattr(result, "__len__") else 0)
        )
        qs.__iter__.side_effect = lambda: iter(result)
        qs.__getitem__.side_effect = lambda key: result[key]
        qs.exists.return_value = bool(result)
        qs.first.return_value = result[0] if result else None
        return qs


# ---------------------------------------------------------------------------
# submit_report_for_review
# ---------------------------------------------------------------------------


class SubmitReportForReviewTests(_ViewTestBase):
    def _stub_status_enum(self, mock_saved):
        mock_saved.Status.DRAFT = "DRAFT"
        mock_saved.Status.UNDER_REVIEW = "UNDER_REVIEW"
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"

    def _stub_workflow_enum(self, mock_workflow):
        jorc = MagicMock(value="JORC")
        valmin = MagicMock(value="VALMIN")
        mock_workflow.WorkflowType = MagicMock()
        mock_workflow.WorkflowType.JORC = "JORC"
        mock_workflow.WorkflowType.VALMIN = "VALMIN"
        mock_workflow.WorkflowType.__iter__ = lambda self_: iter([jorc, valmin])
        mock_workflow.Status.PENDING = "PENDING"

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_non_draft_status_blocked(
        self, mock_get, mock_saved, mock_redirect, mock_messages
    ):
        self._stub_status_enum(mock_saved)
        report = MagicMock(status="UNDER_REVIEW")
        mock_get.return_value = report

        views.submit_report_for_review(self._authed_request("post"), report_id=1)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("saved_report_editor", report_id=1)

    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ContentType")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_draft_report_transitions_to_under_review(
        self,
        mock_get,
        mock_saved,
        mock_workflow,
        mock_ct,
        mock_redirect,
        mock_messages,
        _audit,
    ):
        self._stub_status_enum(mock_saved)
        self._stub_workflow_enum(mock_workflow)

        report = MagicMock(pk=1, status="DRAFT")
        mock_get.return_value = report

        workflow = MagicMock()
        workflow.get_workflow_type_display.return_value = "JORC"
        mock_workflow.objects.create.return_value = workflow

        views.submit_report_for_review(
            self._authed_request("post", data={"workflow_type": "JORC"}),
            report_id=1,
        )

        # Report state machine moved forward.
        self.assertEqual(report.status, "UNDER_REVIEW")
        self.assertIs(report.approval_workflow, workflow)
        report.save.assert_called_once_with(
            update_fields=["status", "approval_workflow"]
        )
        mock_messages.success.assert_called_once()

    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ContentType")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_unknown_workflow_type_defaults_to_jorc(
        self,
        mock_get,
        mock_saved,
        mock_workflow,
        mock_ct,
        _redir,
        _msg,
        _audit,
    ):
        self._stub_status_enum(mock_saved)
        self._stub_workflow_enum(mock_workflow)

        report = MagicMock(pk=1, status="DRAFT")
        mock_get.return_value = report
        mock_workflow.objects.create.return_value = MagicMock()

        views.submit_report_for_review(
            self._authed_request("post", data={"workflow_type": "BOGUS"}),
            report_id=1,
        )

        _, kwargs = mock_workflow.objects.create.call_args
        self.assertEqual(kwargs["workflow_type"], "JORC")

    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ContentType")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_valmin_workflow_type_accepted(
        self,
        mock_get,
        mock_saved,
        mock_workflow,
        mock_ct,
        _redir,
        _msg,
        _audit,
    ):
        self._stub_status_enum(mock_saved)
        self._stub_workflow_enum(mock_workflow)

        report = MagicMock(pk=1, status="DRAFT")
        mock_get.return_value = report
        mock_workflow.objects.create.return_value = MagicMock()

        views.submit_report_for_review(
            self._authed_request("post", data={"workflow_type": "valmin"}),
            report_id=1,
        )

        _, kwargs = mock_workflow.objects.create.call_args
        self.assertEqual(kwargs["workflow_type"], "VALMIN")


# ---------------------------------------------------------------------------
# approve_report
# ---------------------------------------------------------------------------


class ApproveReportTests(_ViewTestBase):
    def _stub_enums(self, mock_saved, mock_workflow):
        mock_saved.Status.UNDER_REVIEW = "UNDER_REVIEW"
        mock_saved.Status.APPROVED = "APPROVED"
        mock_workflow.WorkflowType.JORC = "JORC"
        mock_workflow.WorkflowType.VALMIN = "VALMIN"
        mock_workflow.Status.APPROVED = "APPROVED"

    @patch("core.views.UserProfile")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_user_without_jorc_approval_blocked_for_jorc_workflow(
        self, mock_get, mock_saved, mock_workflow, mock_userprofile
    ):
        self._stub_enums(mock_saved, mock_workflow)
        mock_userprofile.RoleChoices.COMPETENT_PERSON = "COMPETENT_PERSON"

        self.profile.can_approve_jorc = False
        self.profile.can_approve_valmin = True
        self.profile.role = "GEOLOGIST_EXPL"

        report = MagicMock(status="UNDER_REVIEW")
        report.approval_workflow = MagicMock(workflow_type="JORC")
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.approve_report(self._authed_request("post"), report_id=1)

    @patch("core.views.UserProfile")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_user_without_valmin_approval_blocked_for_valmin_workflow(
        self, mock_get, mock_saved, mock_workflow, mock_userprofile
    ):
        self._stub_enums(mock_saved, mock_workflow)
        mock_userprofile.RoleChoices.COMPETENT_PERSON = "COMPETENT_PERSON"
        self.profile.can_approve_jorc = True
        self.profile.can_approve_valmin = False
        self.profile.role = "GEOLOGIST_EXPL"

        report = MagicMock(status="UNDER_REVIEW")
        report.approval_workflow = MagicMock(workflow_type="VALMIN")
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.approve_report(self._authed_request("post"), report_id=1)

    @patch("core.views.UserProfile")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_competent_person_can_approve_jorc_without_explicit_flag(
        self, mock_get, mock_saved, mock_workflow, mock_userprofile
    ):
        self._stub_enums(mock_saved, mock_workflow)
        mock_userprofile.RoleChoices.COMPETENT_PERSON = "COMPETENT_PERSON"

        self.profile.can_approve_jorc = False
        self.profile.can_approve_valmin = False
        self.profile.role = "COMPETENT_PERSON"

        report = MagicMock(status="UNDER_REVIEW")
        report.approval_workflow = MagicMock(workflow_type="JORC")
        mock_get.return_value = report

        with (
            patch("core.views.log_audit"),
            patch("core.views.messages"),
            patch("core.views.redirect", return_value=MagicMock()),
            patch("django.utils.timezone"),
        ):
            views.approve_report(self._authed_request("post"), report_id=1)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_non_under_review_status_blocked(
        self, mock_get, mock_saved, mock_workflow, mock_redirect, mock_messages
    ):
        self._stub_enums(mock_saved, mock_workflow)
        report = MagicMock(status="DRAFT")
        report.approval_workflow = MagicMock(workflow_type="JORC")
        mock_get.return_value = report

        views.approve_report(self._authed_request("post"), report_id=1)

        mock_messages.error.assert_called_once()
        report.save.assert_not_called()

    @patch("django.utils.timezone")
    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_happy_path_approves_report_and_workflow(
        self,
        mock_get,
        mock_saved,
        mock_workflow,
        mock_redirect,
        mock_messages,
        _audit,
        mock_timezone,
    ):
        self._stub_enums(mock_saved, mock_workflow)
        now = MagicMock()
        mock_timezone.now.return_value = now

        workflow = MagicMock(workflow_type="JORC")
        report = MagicMock(status="UNDER_REVIEW", approval_workflow=workflow)
        mock_get.return_value = report

        views.approve_report(
            self._authed_request("post", data={"approval_notes": "looks good"}),
            report_id=1,
        )

        self.assertEqual(report.status, "APPROVED")
        report.save.assert_called_once_with(update_fields=["status"])
        self.assertEqual(workflow.status, "APPROVED")
        self.assertIs(workflow.approved_by, self.user)
        self.assertEqual(workflow.approval_notes, "looks good")
        self.assertIs(workflow.reviewed_at, now)


# ---------------------------------------------------------------------------
# reject_report
# ---------------------------------------------------------------------------


class RejectReportTests(_ViewTestBase):
    @patch("django.utils.timezone")
    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_returns_report_to_draft_and_clears_workflow_link(
        self,
        mock_get,
        mock_saved,
        mock_workflow,
        mock_redirect,
        mock_messages,
        _audit,
        mock_timezone,
    ):
        mock_saved.Status.UNDER_REVIEW = "UNDER_REVIEW"
        mock_saved.Status.DRAFT = "DRAFT"
        mock_workflow.WorkflowType.JORC = "JORC"
        mock_workflow.WorkflowType.VALMIN = "VALMIN"
        mock_workflow.Status.REJECTED = "REJECTED"

        workflow = MagicMock(workflow_type="JORC")
        report = MagicMock(status="UNDER_REVIEW", approval_workflow=workflow)
        mock_get.return_value = report

        views.reject_report(
            self._authed_request("post", data={"approval_notes": "redo"}),
            report_id=1,
        )

        self.assertEqual(report.status, "DRAFT")
        self.assertIsNone(report.approval_workflow)
        report.save.assert_called_once_with(
            update_fields=["status", "approval_workflow"]
        )
        self.assertEqual(workflow.status, "REJECTED")
        self.assertEqual(workflow.approval_notes, "redo")

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_cannot_reject_already_approved_report(
        self, mock_get, mock_saved, mock_workflow, mock_redirect, mock_messages
    ):
        mock_saved.Status.UNDER_REVIEW = "UNDER_REVIEW"
        mock_saved.Status.DRAFT = "DRAFT"
        mock_workflow.WorkflowType.JORC = "JORC"
        mock_workflow.WorkflowType.VALMIN = "VALMIN"
        report = MagicMock(status="APPROVED")
        report.approval_workflow = MagicMock(workflow_type="JORC")
        mock_get.return_value = report

        views.reject_report(self._authed_request("post"), report_id=1)

        mock_messages.error.assert_called_once()
        report.save.assert_not_called()


# ---------------------------------------------------------------------------
# publish_report
# ---------------------------------------------------------------------------


class PublishReportTests(_ViewTestBase):
    def _stub(self, mock_saved, mock_userprofile):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_userprofile.RoleChoices.ADMIN = "ADMIN"
        mock_userprofile.RoleChoices.COMPETENT_PERSON = "COMPETENT_PERSON"

    @patch("core.views.UserProfile")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_geologist_without_approval_flag_blocked(
        self, mock_get, mock_saved, mock_userprofile
    ):
        self._stub(mock_saved, mock_userprofile)
        self.profile.can_approve_jorc = False
        self.profile.role = "GEOLOGIST_EXPL"

        report = MagicMock(status="APPROVED")
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.publish_report(self._authed_request("post"), report_id=1)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.UserProfile")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_only_approved_reports_can_be_published(
        self, mock_get, mock_saved, mock_userprofile, mock_redirect, mock_messages
    ):
        self._stub(mock_saved, mock_userprofile)
        report = MagicMock(status="DRAFT")
        mock_get.return_value = report

        views.publish_report(self._authed_request("post"), report_id=1)

        mock_messages.error.assert_called_once()
        report.save.assert_not_called()

    @patch("core.views.log_audit")
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.UserProfile")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_admin_can_publish_approved_report(
        self, mock_get, mock_saved, mock_userprofile, _redir, _msg, _audit
    ):
        self._stub(mock_saved, mock_userprofile)
        self.profile.can_approve_jorc = False
        self.profile.role = "ADMIN"

        report = MagicMock(status="APPROVED")
        mock_get.return_value = report

        views.publish_report(self._authed_request("post"), report_id=1)

        self.assertEqual(report.status, "PUBLISHED")
        report.save.assert_called_once_with(update_fields=["status"])


# ---------------------------------------------------------------------------
# report_history
# ---------------------------------------------------------------------------


class ReportHistoryTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_groups_reports_by_title(self, _f, mock_saved, mock_render):
        r1a = MagicMock()
        r1a.title = "Annual"
        r1b = MagicMock()
        r1b.title = "Annual"
        r2 = MagicMock()
        r2.title = "Quarterly"
        mock_saved.objects.filter.return_value = self._chainable_qs([r1a, r1b, r2])

        views.report_history(self._authed_request("get"), process_id="p1")

        ctx = mock_render.call_args[0][2]
        grouped = ctx["grouped"]
        self.assertEqual(set(grouped.keys()), {"Annual", "Quarterly"})
        self.assertEqual(len(grouped["Annual"]), 2)
        self.assertEqual(len(grouped["Quarterly"]), 1)
        self.assertEqual(ctx["process_id"], "p1")


# ---------------------------------------------------------------------------
# report_version_detail
# ---------------------------------------------------------------------------


class ReportVersionDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.log_audit")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_logs_view_audit_and_renders_all_versions(
        self, mock_get, mock_saved, mock_audit, mock_render
    ):
        report = MagicMock(version_number=2)
        report.title = "Annual"
        report.process = MagicMock()
        mock_get.return_value = report

        versions = [MagicMock(), MagicMock(), MagicMock()]
        mock_saved.objects.filter.return_value = self._chainable_qs(versions)

        views.report_version_detail(self._authed_request("get"), report_id=1)

        mock_audit.assert_called_once()
        _, kwargs = mock_audit.call_args
        self.assertEqual(kwargs.get("action"), views.AuditLog.ActionType.VIEW)
        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["report"], report)
        self.assertEqual(len(list(ctx["all_versions"])), 3)


# ---------------------------------------------------------------------------
# all_reports_history
# ---------------------------------------------------------------------------


class AllReportsHistoryTests(_ViewTestBase):
    def _make_report(self, *, title, project_name=None, project_id=None):
        report = MagicMock()
        report.title = title
        if project_name is not None:
            report.process = MagicMock()
            report.process.name = project_name
            report.process.id = project_id or "pid"
        else:
            report.process = None
        return report

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_no_search_returns_all_grouped_by_project_then_title(
        self, _f, mock_saved, mock_render
    ):
        r1 = self._make_report(title="Annual", project_name="Alpha", project_id="A")
        r2 = self._make_report(title="Annual", project_name="Alpha", project_id="A")
        r3 = self._make_report(title="Q1", project_name="Alpha", project_id="A")
        r4 = self._make_report(title="Geo", project_name=None)
        mock_saved.objects.filter.return_value = self._chainable_qs([r1, r2, r3, r4])

        views.all_reports_history(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        grouped = ctx["grouped"]
        self.assertEqual(set(grouped.keys()), {"Alpha", "No Project"})
        self.assertEqual(len(grouped["Alpha"]["titles"]["Annual"]), 2)
        self.assertEqual(len(grouped["Alpha"]["titles"]["Q1"]), 1)
        self.assertEqual(grouped["No Project"]["process_id"], None)
        self.assertIsNone(ctx["total"])  # total only populated for search.

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views.SearchQuery")
    @patch("core.views.SearchRank")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_search_query_branch_runs_annotate_and_sets_total(
        self, _f, _rank, _query, mock_saved, mock_render
    ):
        qs = self._chainable_qs([])
        qs.count.return_value = 5
        mock_saved.objects.filter.return_value = qs

        views.all_reports_history(self._authed_request("get", path="/?q=lithium"))

        qs.annotate.assert_called_once()
        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["q"], "lithium")
        self.assertEqual(ctx["total"], 5)


# ---------------------------------------------------------------------------
# export_report
# ---------------------------------------------------------------------------


class ExportReportTests(_ViewTestBase):
    def test_invalid_format_returns_400(self):
        request = self._authed_request(
            "post",
            data={
                "format": "html",
                "content_md": "x",
                "title": "t",
            },
        )
        response = views.export_report(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid format", response.content)

    def test_get_request_rejected(self):
        request = self._authed_request("get")
        self.assertEqual(views.export_report(request).status_code, 405)

    @patch("core.views.SimpleDocTemplate")
    def test_pdf_response_has_correct_content_type_and_filename(self, mock_doc_cls):
        mock_doc_cls.return_value = MagicMock()

        request = self._authed_request(
            "post",
            data={
                "format": "pdf",
                "content_md": "# Title",
                "title": "My Report Title",
            },
        )
        response = views.export_report(request)

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("My_Report_Title", response["Content-Disposition"])

    @patch("core.views.DocxDocument")
    def test_docx_response_has_correct_content_type(self, mock_docx_cls):
        mock_docx_cls.return_value = MagicMock()

        request = self._authed_request(
            "post",
            data={
                "format": "docx",
                "content_md": "body",
                "title": "T",
            },
        )
        response = views.export_report(request)

        self.assertIn("wordprocessingml", response["Content-Type"])
        self.assertIn(".docx", response["Content-Disposition"])

    @patch("core.views.Paragraph")
    @patch("core.views.SimpleDocTemplate")
    @patch("core.views.SavedReport")
    def test_pdf_includes_sources_section_when_report_id_provided(
        self, mock_saved, mock_doc_cls, mock_paragraph
    ):
        d1 = MagicMock(title="Doc A", doc_type="Survey", confidentiality="PUBLIC")
        d1.timestamp = MagicMock()
        d1.timestamp.strftime.return_value = "2026-01-01"
        d2 = MagicMock(
            title="Doc B", doc_type=None, confidentiality=None, timestamp=None
        )

        saved = MagicMock()
        saved.source_documents.order_by.return_value = [d1, d2]
        chain = MagicMock()
        chain.get.return_value = saved
        mock_saved.objects.prefetch_related.return_value = chain

        mock_doc_cls.return_value = MagicMock()

        request = self._authed_request(
            "post",
            data={
                "format": "pdf",
                "content_md": "body",
                "title": "T",
                "report_id": "uuid-here",
            },
        )
        views.export_report(request)

        all_args = [c.args[0] for c in mock_paragraph.call_args_list if c.args]
        joined = " ".join(all_args)
        self.assertIn("Sources", joined)
        self.assertIn("Doc A", joined)
        self.assertIn("Doc B", joined)

    @patch("core.views.Paragraph")
    @patch("core.views.SimpleDocTemplate")
    @patch("core.views.SavedReport")
    def test_pdf_skips_sources_when_lookup_fails(
        self, mock_saved, mock_doc_cls, mock_paragraph
    ):
        mock_saved.DoesNotExist = type("DoesNotExist", (Exception,), {})
        chain = MagicMock()
        chain.get.side_effect = mock_saved.DoesNotExist
        mock_saved.objects.prefetch_related.return_value = chain
        mock_doc_cls.return_value = MagicMock()

        request = self._authed_request(
            "post",
            data={
                "format": "pdf",
                "content_md": "body",
                "title": "T",
                "report_id": "missing",
            },
        )
        views.export_report(request)

        all_args = [c.args[0] for c in mock_paragraph.call_args_list if c.args]
        self.assertNotIn("Sources", " ".join(all_args))


# ---------------------------------------------------------------------------
# report_detail
# ---------------------------------------------------------------------------


class ReportDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    def test_renders_template_with_report_id(self, mock_render):
        views.report_detail(self._authed_request("get"), report_id="r1")

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/report_detail.html")
        self.assertEqual(args[2]["report_id"], "r1")


# ---------------------------------------------------------------------------
# audit_log_view
# ---------------------------------------------------------------------------


class AuditLogViewTests(_ViewTestBase):
    def setUp(self):
        super().setUp()
        self.profile.role = "ADMIN"

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.AuditLog")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_each_filter_param_narrows_the_queryset(
        self, _f, mock_audit, mock_paginate, mock_render
    ):
        qs = self._chainable_qs([])
        mock_audit.objects.select_related.return_value = qs
        mock_paginate.return_value = MagicMock()

        request = self._authed_request(
            "get",
            path=(
                "/?action=CREATE&username=bob&date_from=2026-01-01"
                "&date_to=2026-05-01&obj_type=Document"
            ),
        )
        views.audit_log_view(request)

        filter_kwargs = [c.kwargs for c in qs.filter.call_args_list]
        self.assertTrue(any(kw.get("action") == "CREATE" for kw in filter_kwargs))
        self.assertTrue(
            any(kw.get("user__username__icontains") == "bob" for kw in filter_kwargs)
        )
        self.assertTrue(
            any(kw.get("timestamp__date__gte") == "2026-01-01" for kw in filter_kwargs)
        )
        self.assertTrue(
            any(kw.get("timestamp__date__lte") == "2026-05-01" for kw in filter_kwargs)
        )
        self.assertTrue(
            any(kw.get("content_type__model") == "document" for kw in filter_kwargs)
        )

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.AuditLog")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_no_filter_params_only_applies_base_query(
        self, _f, mock_audit, mock_paginate, _render
    ):
        qs = self._chainable_qs([])
        mock_audit.objects.select_related.return_value = qs
        mock_paginate.return_value = MagicMock()

        views.audit_log_view(self._authed_request("get"))

        qs.filter.assert_not_called()

    @patch("core.views.AuditLog")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_csv_export_returns_streaming_response_with_attachment_header(
        self, _f, mock_audit
    ):
        entry = MagicMock(
            action="CREATE",
            description="x",
            ip_address="127.0.0.1",
            object_id=1,
        )
        entry.timestamp = MagicMock()
        entry.timestamp.strftime.return_value = "2026-01-01 12:00:00"
        entry.user = MagicMock(username="alice")
        entry.content_type = MagicMock(model="document")

        qs = self._chainable_qs([entry])
        qs.iterator.return_value = iter([entry])
        mock_audit.objects.select_related.return_value = qs

        request = self._authed_request("get", path="/?export=csv")
        response = views.audit_log_view(request)

        self.assertIsInstance(response, StreamingHttpResponse)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("audit_log.csv", response["Content-Disposition"])

    @patch("core.views.AuditLog")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_csv_export_handles_missing_user_gracefully(self, _f, mock_audit):
        entry = MagicMock(
            user=None,
            action="CREATE",
            description="auto",
            ip_address=None,
            object_id=1,
        )
        entry.timestamp = MagicMock()
        entry.timestamp.strftime.return_value = "2026-01-01 12:00:00"
        entry.content_type = MagicMock(model="document")

        qs = self._chainable_qs([entry])
        qs.iterator.return_value = iter([entry])
        mock_audit.objects.select_related.return_value = qs

        response = views.audit_log_view(
            self._authed_request("get", path="/?export=csv")
        )

        rows = b"".join(response.streaming_content)
        self.assertIn(b"auto", rows)
        self.assertNotIn(b"None", rows)


# ---------------------------------------------------------------------------
# approval_workflows_list
# ---------------------------------------------------------------------------


class ApprovalWorkflowsListTests(_ViewTestBase):
    @patch("core.views.UserProfile")
    def test_unprivileged_user_blocked(self, mock_userprofile):
        mock_userprofile.RoleChoices.ADMIN = "ADMIN"
        mock_userprofile.RoleChoices.DATA_MANAGER = "DATA_MANAGER"
        mock_userprofile.RoleChoices.OPERATIONS_MANAGER = "OPERATIONS_MANAGER"

        self.profile.role = "GEOLOGIST_EXPL"
        self.profile.can_approve_jorc = False
        self.profile.can_approve_valmin = False

        with self.assertRaises(PermissionDenied):
            views.approval_workflows_list(self._authed_request("get"))

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.ContentType")
    @patch("core.views.UserProfile")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_user_with_jorc_approval_flag_allowed_even_without_role(
        self,
        _f,
        mock_userprofile,
        mock_ct,
        mock_saved,
        mock_workflow,
        mock_paginate,
        _render,
    ):
        mock_userprofile.RoleChoices.ADMIN = "ADMIN"
        mock_userprofile.RoleChoices.DATA_MANAGER = "DATA_MANAGER"
        mock_userprofile.RoleChoices.OPERATIONS_MANAGER = "OPERATIONS_MANAGER"

        self.profile.role = "GEOLOGIST_EXPL"
        self.profile.can_approve_jorc = True
        self.profile.can_approve_valmin = False

        mock_saved.objects = self._chainable_qs([])
        mock_workflow.objects = self._chainable_qs([])
        mock_paginate.return_value = MagicMock()

        views.approval_workflows_list(self._authed_request("get"))

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.ApprovalWorkflow")
    @patch("core.views.SavedReport")
    @patch("core.views.ContentType")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_status_and_workflow_type_filters_applied(
        self, _f, mock_ct, mock_saved, mock_workflow, mock_paginate, mock_render
    ):
        self.user.is_superuser = True
        self.user.save()
        mock_saved.objects = self._chainable_qs([])
        qs = self._chainable_qs([])
        mock_workflow.objects.filter.return_value = qs
        mock_paginate.return_value = MagicMock()

        views.approval_workflows_list(
            self._authed_request("get", path="/?status=PENDING&workflow_type=JORC")
        )

        filter_kwargs = [c.kwargs for c in qs.filter.call_args_list]
        self.assertTrue(any(kw.get("status") == "PENDING" for kw in filter_kwargs))
        self.assertTrue(any(kw.get("workflow_type") == "JORC" for kw in filter_kwargs))


# ---------------------------------------------------------------------------
# document_analysis_page
# ---------------------------------------------------------------------------


class DocumentAnalysisPageTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_with_recent_docs(self, _f, mock_document, mock_render):
        mock_document.objects = self._chainable_qs([MagicMock()])

        views.document_analysis_page(self._authed_request("get"))

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/document_analysis.html")
        self.assertIn("recent_docs", args[2])


# ---------------------------------------------------------------------------
# analyze_document
# ---------------------------------------------------------------------------


class AnalyzeDocumentTests(_ViewTestBase):
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_document_with_no_extracted_text_redirects_with_error(
        self, mock_get, mock_redirect, mock_messages
    ):
        document = MagicMock(organisation=self.org, extracted_text="")
        mock_get.return_value = document

        views.analyze_document(self._authed_request("get"), pk=1)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("document_analysis_page")

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.GraniteClient")
    @patch("core.views.get_object_or_404")
    def test_successful_analysis_saves_and_redirects_to_detail(
        self, mock_get, mock_granite_cls, mock_redirect, mock_messages
    ):
        document = MagicMock(
            pk=42,
            organisation=self.org,
            extracted_text="Some real document content.",
            title="Drillhole report",
        )
        mock_get.return_value = document

        client = MagicMock()
        client.complete.return_value = "## Summary\nLooks good."
        mock_granite_cls.return_value = client

        views.analyze_document(self._authed_request("get"), pk=42)

        client.complete.assert_called_once()
        prompt = client.complete.call_args[0][0]
        self.assertIn("Drillhole report", prompt)
        self.assertIn("Some real document content.", prompt)

        self.assertEqual(document.analysis_text, "## Summary\nLooks good.")
        document.save.assert_called_once_with(update_fields=["analysis_text"])
        mock_redirect.assert_called_with("document_analysis_detail", pk=42)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.GraniteClient")
    @patch("core.views.get_object_or_404")
    def test_granite_failure_flashes_error_and_redirects_back(
        self, mock_get, mock_granite_cls, mock_redirect, mock_messages
    ):
        document = MagicMock(organisation=self.org, extracted_text="content")
        mock_get.return_value = document

        mock_granite_cls.side_effect = RuntimeError("model down")

        views.analyze_document(self._authed_request("get"), pk=1)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("document_analysis_page")

        document.save.assert_not_called()

    @patch("core.views.GraniteClient")
    @patch("core.views.get_object_or_404")
    def test_long_document_text_is_truncated_at_12000_chars(
        self, mock_get, mock_granite_cls
    ):
        long_text = "A" * 20000
        document = MagicMock(
            organisation=self.org,
            extracted_text=long_text,
            title="big",
        )
        mock_get.return_value = document
        client = MagicMock()
        client.complete.return_value = "ok"
        mock_granite_cls.return_value = client

        with (
            patch("core.views.messages"),
            patch("core.views.redirect", return_value=MagicMock()),
        ):
            views.analyze_document(self._authed_request("get"), pk=1)

        prompt = client.complete.call_args[0][0]
        self.assertEqual(prompt.count("A"), 12000)

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        document = MagicMock(organisation=MagicMock(name="other"), extracted_text="x")
        mock_get.return_value = document

        with self.assertRaises(PermissionDenied):
            views.analyze_document(self._authed_request("get"), pk=1)


# ---------------------------------------------------------------------------
# export_document_analysis
# ---------------------------------------------------------------------------


class ExportDocumentAnalysisTests(_ViewTestBase):
    @patch("core.views.get_object_or_404")
    def test_400_when_document_has_no_analysis(self, mock_get):
        document = MagicMock(analysis_text="")
        mock_get.return_value = document

        response = views.export_document_analysis(self._authed_request("get"), pk=1)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No analysis", response.content)

    @patch("core.views.SimpleDocTemplate")
    @patch("core.views.get_object_or_404")
    def test_pdf_export_returns_pdf_response_with_slugified_filename(
        self, mock_get, mock_doc_cls
    ):
        document = MagicMock(analysis_text="# Header")
        document.title = "My/Bad:Title"
        mock_get.return_value = document
        mock_doc_cls.return_value = MagicMock()

        response = views.export_document_analysis(
            self._authed_request("get", path="/?format=pdf"), pk=1
        )

        self.assertEqual(response["Content-Type"], "application/pdf")
        disposition = response["Content-Disposition"]
        self.assertNotIn("/", disposition.replace("filename=", ""))
        self.assertNotIn(":", disposition.replace('"', "").replace("filename=", ""))
        self.assertIn("_analysis.pdf", disposition)

    @patch("core.views.DocxDocument")
    @patch("core.views.get_object_or_404")
    def test_docx_export_returns_docx_response(self, mock_get, mock_docx_cls):
        document = MagicMock(analysis_text="body")
        document.title = "Doc"
        mock_get.return_value = document
        mock_docx_cls.return_value = MagicMock()

        response = views.export_document_analysis(
            self._authed_request("get", path="/?format=docx"), pk=1
        )

        self.assertIn("wordprocessingml", response["Content-Type"])
        self.assertIn(".docx", response["Content-Disposition"])

    @patch("core.views.get_object_or_404")
    def test_invalid_format_returns_400(self, mock_get):
        document = MagicMock(analysis_text="body")
        mock_get.return_value = document

        response = views.export_document_analysis(
            self._authed_request("get", path="/?format=html"), pk=1
        )

        self.assertEqual(response.status_code, 400)

    @patch("core.views.SimpleDocTemplate")
    @patch("core.views.get_object_or_404")
    def test_default_format_is_pdf(self, mock_get, mock_doc_cls):
        document = MagicMock(analysis_text="body")
        document.title = "Doc"
        mock_get.return_value = document
        mock_doc_cls.return_value = MagicMock()

        response = views.export_document_analysis(self._authed_request("get"), pk=1)

        self.assertEqual(response["Content-Type"], "application/pdf")
