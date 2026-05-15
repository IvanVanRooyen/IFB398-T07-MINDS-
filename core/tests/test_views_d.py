"""
Coverage;
    assign_report_prospect, samples, create_sample, sample_detail,
    surveys, create_survey, survey_detail,
    doc_link_picker, create_doc_link, delete_doc_link,
    drillhole_link_picker, link_drillhole, unlink_drillhole,
    bulk_link_drillholes, bulk_assign_drillholes,
    drillholes, drillhole_detail, drillhole_import,
    tenements, create_tenement, tenement_detail, edit_tenement,
    edit_process_geometry
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, JsonResponse

from core import views
from core.models import Process

from .test_views_b import _ViewTestBase

User = get_user_model()


# ---------------------------------------------------------------------------
# assign_report_prospect
# ---------------------------------------------------------------------------


class AssignReportProspectTests(_ViewTestBase):
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    def test_clears_prospect_when_no_id_supplied(self, mock_get, _mock_prospect):
        report = MagicMock(organisation=self.org, prospect_id=None)
        mock_get.return_value = report

        request = self._authed_request("post", data={})
        response = views.assign_report_prospect(request, report_id=1)

        self.assertIsNone(report.prospect)
        report.save.assert_called_once_with(update_fields=["prospect"])
        self.assertIsInstance(response, JsonResponse)
        payload = json.loads(response.content)
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["prospect_id"])

    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    def test_assigns_prospect_scoped_to_report_process(self, mock_get, mock_prospect):
        process = Process

        report = MagicMock(organisation=self.org, process=process)
        mock_get.return_value = report

        prospect = MagicMock(pk=99)
        prospect_qs = self._chainable_qs([prospect])
        mock_prospect.objects.filter.return_value = prospect_qs
        report.prospect_id = 99

        request = self._authed_request("post", data={"prospect_id": "99"})
        views.assign_report_prospect(request, report_id=1)

        # the lookup is scoped to the report's process - shouldn't be possible to 'sneak' a prospect
        # from another project onto a report.
        mock_prospect.objects.filter.assert_called_with(pk="99", process=process)
        self.assertIs(report.prospect, prospect)
        report.save.assert_called_once_with(update_fields=["prospect"])

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        other_org = MagicMock(name="other org")
        report = MagicMock(organisation=other_org)
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.assign_report_prospect(self._authed_request("post"), report_id=1)

    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    def test_superuser_can_assign_across_orgs(self, mock_get, mock_prospect):
        self.user.is_superuser = True
        self.user.save()
        report = MagicMock(organisation=MagicMock(name="other"))
        mock_get.return_value = report
        mock_prospect.objects.filter.return_value = self._chainable_qs([])

        response = views.assign_report_prospect(
            self._authed_request("post"), report_id=1
        )
        self.assertEqual(response.status_code, 200)

    def test_get_request_rejected(self):
        # @require_POST
        request = self._authed_request("get")
        self.assertEqual(
            views.assign_report_prospect(request, report_id=1).status_code, 405
        )


# ---------------------------------------------------------------------------
# samples
# ---------------------------------------------------------------------------


class SamplesListTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Sample")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_samples_template_with_paginated_qs(
        self, _f, mock_sample, mock_paginate, mock_render
    ):
        mock_sample.objects = self._chainable_qs([])
        mock_paginate.return_value = MagicMock()

        views.samples(self._authed_request("get"))

        self.assertEqual(mock_render.call_args[0][1], "core/samples.html")
        mock_paginate.assert_called_once()

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Sample")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_prospect_filter_applied_when_query_param_present(
        self, _f, mock_sample, _paginate, _render
    ):
        qs = self._chainable_qs([])
        mock_sample.objects = qs

        views.samples(self._authed_request("get", path="/?prospect=42"))

        # the second filter call narrows by prospect_id
        filter_calls = [c.kwargs for c in qs.filter.call_args_list]
        self.assertTrue(any(kw.get("prospect_id") == "42" for kw in filter_calls))

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Sample")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_no_prospect_filter_when_query_param_absent(
        self, _f, mock_sample, _paginate, _render
    ):
        qs = self._chainable_qs([])
        mock_sample.objects = qs

        views.samples(self._authed_request("get"))

        # only the initial org filter is applied (single call to `filter()`)
        self.assertEqual(qs.filter.call_count, 1)


# ---------------------------------------------------------------------------
# create_sample
# ---------------------------------------------------------------------------


class CreateSampleTests(_ViewTestBase):
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    def test_user_without_org_redirected_to_samples(self, mock_redirect, mock_messages):
        self.profile.organisation = None

        views.create_sample(self._authed_request("get"))

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("samples")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SampleForm")
    @patch("core.views.Prospect")
    def test_get_with_prospect_param_prefills_initial_prospect(
        self, mock_prospect, mock_form_cls, _render
    ):
        prospect = MagicMock()
        mock_prospect.objects.filter.return_value = self._chainable_qs([prospect])
        mock_form_cls.return_value = MagicMock()

        views.create_sample(self._authed_request("get", path="/?prospect=5"))

        _, kwargs = mock_form_cls.call_args
        self.assertIs(kwargs["initial_prospect"], prospect)

    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SampleForm")
    def test_valid_post_saves_and_redirects_to_sample_detail(
        self, mock_form_cls, mock_redirect, mock_audit
    ):
        sample = MagicMock(pk=42, name="S-01", prospect_id=None)
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = sample
        mock_form_cls.return_value = form

        views.create_sample(self._authed_request("post"))

        self.assertIs(sample.organisation, self.org)
        sample.save.assert_called_once()
        mock_audit.assert_called_once()
        mock_redirect.assert_called_with("sample_detail", pk=42)

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SampleForm")
    def test_post_with_next_prospect_redirects_to_prospect_detail(
        self, mock_form_cls, mock_redirect
    ):
        sample = MagicMock(pk=1, prospect_id=99)
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = sample
        mock_form_cls.return_value = form

        request = self._authed_request("post", data={"next": "prospect"})
        with patch("core.views.log_audit"):
            views.create_sample(request)

        mock_redirect.assert_called_with("prospect_detail", pk=99)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SampleForm")
    def test_invalid_post_re_renders_form(self, mock_form_cls, mock_render):
        form = MagicMock()
        form.is_valid.return_value = False
        mock_form_cls.return_value = form

        views.create_sample(self._authed_request("post"))

        self.assertEqual(mock_render.call_args[0][1], "core/sample_form.html")


# ---------------------------------------------------------------------------
# sample_detail
# ---------------------------------------------------------------------------


class SampleDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_same_org_user_sees_sample(self, mock_get, mock_render):
        sample = MagicMock(organisation=self.org)
        mock_get.return_value = sample

        views.sample_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["sample"], sample)

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        sample = MagicMock(organisation=MagicMock(name="other"))
        mock_get.return_value = sample

        with self.assertRaises(PermissionDenied):
            views.sample_detail(self._authed_request("get"), pk=1)


# ---------------------------------------------------------------------------
# survey_detail
# ---------------------------------------------------------------------------


class SurveyDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_geom_serialised_when_present(self, mock_get, mock_render):
        survey = MagicMock(organisation=self.org)
        survey.geom = MagicMock()
        survey.geom.geojson = '{"type":"Polygon","coordinates":[]}'
        mock_get.return_value = survey

        views.survey_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        parsed = json.loads(ctx["area_geom_geojson"])
        self.assertEqual(parsed["type"], "Polygon")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_geom_null_string_when_absent(self, mock_get, mock_render):
        survey = MagicMock(organisation=self.org, geom=None)
        mock_get.return_value = survey

        views.survey_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["area_geom_geojson"], "null")

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        survey = MagicMock(organisation=MagicMock(name="other"), geom=None)
        mock_get.return_value = survey

        with self.assertRaises(PermissionDenied):
            views.survey_detail(self._authed_request("get"), pk=1)


# ---------------------------------------------------------------------------
# create_survey
#       note that this is very similar to `create_sample` so coverage is more
#       narrow here
# ---------------------------------------------------------------------------


class CreateSurveyTests(_ViewTestBase):
    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SurveyForm")
    def test_valid_post_with_prospect_redirects_to_prospect_detail(
        self, mock_form_cls, mock_redirect, _audit
    ):
        survey = MagicMock(pk=1, prospect_id=88, name="Geo survey")
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = survey
        mock_form_cls.return_value = form

        views.create_survey(self._authed_request("post"))
        mock_redirect.assert_called_with("prospect_detail", pk=88)

    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SurveyForm")
    def test_valid_post_without_prospect_redirects_to_survey_detail(
        self, mock_form_cls, mock_redirect, _audit
    ):
        survey = MagicMock(pk=1, prospect_id=None, name="x")
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = survey
        mock_form_cls.return_value = form

        views.create_survey(self._authed_request("post"))

        mock_redirect.assert_called_with("survey_detail", pk=1)


# ---------------------------------------------------------------------------
# doc_link_picker
# ---------------------------------------------------------------------------


class DocLinkPickerTests(_ViewTestBase):
    def test_rejects_unknown_content_type(self):
        request = self._authed_request("get", path="/?content_type=bogus&object_id=1")
        response = views.doc_link_picker(request)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_valid_content_type_renders_picker(self, _f, mock_document, mock_render):
        mock_document.objects = self._chainable_qs([MagicMock() for _ in range(3)])

        request = self._authed_request(
            "get", path="/?content_type=prospect&object_id=5"
        )
        views.doc_link_picker(request)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["content_type_label"], "prospect")
        self.assertEqual(ctx["object_id"], "5")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_each_linkable_content_type_accepted(self, _f, mock_document, _render):
        mock_document.objects = self._chainable_qs([])
        for label in ("prospect", "tenement", "drillhole", "process"):
            request = self._authed_request(
                "get", path=f"/?content_type={label}&object_id=1"
            )
            response = views.doc_link_picker(request)
            self.assertNotEqual(
                getattr(response, "status_code", 200),
                400,
                msg=label,
            )


# ---------------------------------------------------------------------------
# create_doc_link
# ---------------------------------------------------------------------------


class CreateDocLinkTests(_ViewTestBase):
    def test_returns_400_when_required_fields_missing(self):
        request = self._authed_request(
            "post",
            data={
                "content_type_label": "prospect",
                "object_id": "1",
            },
        )
        response = views.create_doc_link(request)
        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_invalid_content_type(self):
        request = self._authed_request(
            "post",
            data={
                "document_id": "1",
                "content_type_label": "bogus",
                "object_id": "1",
            },
        )
        response = views.create_doc_link(request)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.ContentType")
    def test_returns_400_when_content_type_record_missing(self, mock_ct_model):
        mock_ct_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_ct_model.objects.get.side_effect = mock_ct_model.DoesNotExist

        request = self._authed_request(
            "post",
            data={
                "document_id": "1",
                "content_type_label": "prospect",
                "object_id": "1",
            },
        )
        response = views.create_doc_link(request)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.log_audit")
    @patch("core.views.DocLink")
    @patch("core.views.get_object_or_404")
    @patch("core.views.ContentType")
    @patch("core.views.Prospect")
    def test_renders_linked_documents_partial_for_prospect(
        self, mock_prospect, mock_ct, mock_get, mock_doclink, _audit, mock_render
    ):
        mock_ct.objects.get.return_value = MagicMock()
        doc = MagicMock(title="X")
        prospect = MagicMock()

        mock_get.side_effect = [doc, prospect]
        mock_doclink.objects.get_or_create.return_value = (MagicMock(), True)
        mock_doclink.objects.filter.return_value = self._chainable_qs([])

        request = self._authed_request(
            "post",
            data={
                "document_id": "1",
                "content_type_label": "prospect",
                "object_id": "5",
            },
        )
        views.create_doc_link(request)

        self.assertEqual(
            mock_render.call_args[0][1], "core/partials/linked_documents.html"
        )

    @patch("core.views.log_audit")
    @patch("core.views.DocLink")
    @patch("core.views.get_object_or_404")
    @patch("core.views.ContentType")
    def test_returns_204_for_non_prospect_entities(
        self, mock_ct, mock_get, mock_doclink, _audit
    ):
        mock_ct.objects.get.return_value = MagicMock()
        mock_get.return_value = MagicMock(title="x")
        mock_doclink.objects.get_or_create.return_value = (MagicMock(), True)

        request = self._authed_request(
            "post",
            data={
                "document_id": "1",
                "content_type_label": "tenement",
                "object_id": "5",
            },
        )
        response = views.create_doc_link(request)

        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 204)

    @patch("core.views.log_audit")
    @patch("core.views.DocLink")
    @patch("core.views.get_object_or_404")
    @patch("core.views.ContentType")
    def test_audit_only_logged_for_newly_created_links(
        self, mock_ct, mock_get, mock_doclink, mock_audit
    ):
        mock_ct.objects.get.return_value = MagicMock()
        mock_get.return_value = MagicMock(title="x")

        mock_doclink.objects.get_or_create.side_effect = [
            (MagicMock(), True),
            (MagicMock(), False),
        ]

        request = self._authed_request(
            "post",
            data={
                "document_id": ["1", "2"],
                "content_type_label": "tenement",
                "object_id": "5",
            },
        )
        views.create_doc_link(request)
        self.assertEqual(mock_audit.call_count, 1)


# ---------------------------------------------------------------------------
# delete_doc_link
# ---------------------------------------------------------------------------


class DeleteDocLinkTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.log_audit")
    @patch("core.views.Prospect")
    @patch("core.views.DocLink")
    @patch("core.views.get_object_or_404")
    def test_prospect_link_returns_partial(
        self, mock_get, mock_doclink, mock_prospect, _audit, mock_render
    ):
        link = MagicMock()
        link.content_type.model = "prospect"
        link.object_id = 5
        link.document = MagicMock(title="x")
        prospect = MagicMock()

        mock_get.side_effect = [link, prospect]
        mock_doclink.objects.filter.return_value = self._chainable_qs([])

        views.delete_doc_link(self._authed_request("post"), pk=1)

        link.delete.assert_called_once()
        self.assertEqual(
            mock_render.call_args[0][1], "core/partials/linked_documents.html"
        )

    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_non_prospect_link_returns_204(self, mock_get, _audit):
        link = MagicMock()
        link.content_type.model = "tenement"
        link.document = MagicMock(title="x")
        mock_get.return_value = link

        response = views.delete_doc_link(self._authed_request("post"), pk=1)

        link.delete.assert_called_once()
        self.assertEqual(response.status_code, 204)


# ---------------------------------------------------------------------------
# Drillhole linking helpers
# ---------------------------------------------------------------------------


class DrillholeLinkPickerTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.get_object_or_404")
    def test_only_unlinked_drillholes_in_same_process_offered(
        self, mock_get, mock_drillhole, mock_render
    ):
        prospect = MagicMock(process=MagicMock())
        mock_get.return_value = prospect

        unlinked = [MagicMock(name=f"DH{i}") for i in range(3)]
        qs = self._chainable_qs(unlinked)
        mock_drillhole.objects.filter.return_value = qs

        views.drillhole_link_picker(self._authed_request("get", path="/?prospect_id=1"))

        # filter pins both process + `prospect__isnull=True`
        _, kwargs = mock_drillhole.objects.filter.call_args
        self.assertIs(kwargs["process"], prospect.process)
        self.assertTrue(kwargs["prospect__isnull"])


class LinkDrillholeTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.get_object_or_404")
    def test_assigns_prospect_and_renders_partial(
        self, mock_get, mock_drillhole, mock_render
    ):
        prospect = MagicMock(pk=1)
        drillhole = MagicMock()
        mock_get.side_effect = [prospect, drillhole]
        mock_drillhole.objects.filter.return_value = self._chainable_qs([drillhole])

        request = self._authed_request(
            "post",
            data={
                "drillhole_id": "1",
                "prospect_id": "1",
            },
        )
        views.link_drillhole(request)

        self.assertIs(drillhole.prospect, prospect)
        drillhole.save.assert_called_once_with(update_fields=["prospect"])
        self.assertEqual(
            mock_render.call_args[0][1], "core/partials/linked_drillholes.html"
        )


class UnlinkDrillholeTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.get_object_or_404")
    def test_clears_prospect_but_re_renders_for_old_prospect(
        self, mock_get, mock_drillhole, mock_render
    ):
        original_prospect = MagicMock(name="original prospect")
        drillhole = MagicMock(prospect=original_prospect)
        mock_get.return_value = drillhole
        mock_drillhole.objects.filter.return_value = self._chainable_qs([])

        views.unlink_drillhole(self._authed_request("post"), pk=1)

        # the drillhole's prospect was cleared
        self.assertIsNone(drillhole.prospect)
        drillhole.save.assert_called_once_with(update_fields=["prospect"])

        # the partial re-rendered uses the previously linked prospect so the parent
        # prospects ui section refreshes correctly
        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["prospect"], original_prospect)


class BulkLinkDrillholesTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.get_object_or_404")
    def test_no_ids_renders_partial_without_updating(
        self, mock_get, mock_drillhole, mock_render
    ):
        prospect = MagicMock()
        mock_get.return_value = prospect

        final_qs = self._chainable_qs([])
        mock_drillhole.objects.filter.return_value = final_qs

        request = self._authed_request("post", data={"prospect_id": "1"})
        views.bulk_link_drillholes(request)

        final_qs.update.assert_not_called()
        self.assertEqual(
            mock_render.call_args[0][1], "core/partials/linked_drillholes.html"
        )

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.get_object_or_404")
    def test_with_ids_updates_then_renders(self, mock_get, mock_drillhole, mock_render):
        prospect = MagicMock(process=MagicMock())
        mock_get.return_value = prospect
        qs = self._chainable_qs([])
        mock_drillhole.objects.filter.return_value = qs

        request = self._authed_request(
            "post",
            data={
                "prospect_id": "1",
                "drillhole_id": ["10", "11", "12"],
            },
        )

        views.bulk_link_drillholes(request)
        qs.update.assert_called_once_with(prospect=prospect)


class BulkAssignDrillholesTests(_ViewTestBase):
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    def test_missing_inputs_flash_error_and_redirect(
        self, mock_redirect, mock_messages
    ):
        request = self._authed_request("post", data={})
        views.bulk_assign_drillholes(request)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("drillholes")

    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_user_without_org_visibility_blocked(
        self, _f, mock_get, mock_prospect_model
    ):
        prospect = MagicMock()
        mock_get.return_value = prospect

        mock_prospect_model.objects = self._chainable_qs([])

        request = self._authed_request(
            "post",
            data={
                "prospect_id": "1",
                "drillhole_ids": ["1", "2"],
            },
        )
        with self.assertRaises(PermissionDenied):
            views.bulk_assign_drillholes(request)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_success_message_reports_skipped_when_some_wrong_project(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_drillhole,
        mock_redirect,
        mock_messages,
    ):
        prospect = MagicMock(name="P", process=MagicMock())
        prospect.name = "Bonanza"
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])

        # only two of three requested IDs are in the correct project
        qs = self._chainable_qs([])
        qs.update.return_value = 2
        mock_drillhole.objects.filter.return_value = qs

        request = self._authed_request(
            "post",
            data={
                "prospect_id": "1",
                "drillhole_ids": ["1", "2", "3"],
            },
        )
        views.bulk_assign_drillholes(request)

        args, _ = mock_messages.success.call_args
        msg = args[1]
        self.assertIn("2 drillholes linked", msg)
        self.assertIn("1 skipped", msg)
        self.assertIn("Bonanza", msg)
        mock_redirect.assert_called_with("drillholes")

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Drillhole")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_singular_drillhole_message_when_only_one_linked(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_drillhole,
        mock_redirect,
        mock_messages,
    ):
        prospect = MagicMock(process=MagicMock())
        prospect.name = "P"
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])

        qs = self._chainable_qs([])
        qs.update.return_value = 1
        mock_drillhole.objects.filter.return_value = qs

        request = self._authed_request(
            "post",
            data={
                "prospect_id": "1",
                "drillhole_ids": ["1"],
            },
        )
        views.bulk_assign_drillholes(request)

        args, _ = mock_messages.success.call_args
        self.assertIn("1 drillhole linked", args[1])  # no trailing 's'
        self.assertNotIn("skipped", args[1])


# ---------------------------------------------------------------------------
# drillholes list view
# ---------------------------------------------------------------------------


class DrillholesListTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Prospect")
    @patch("core.views._get_model")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_with_drillhole_page_when_model_exists(
        self, _f, mock_get_model, mock_prospect, mock_paginate, mock_render
    ):
        drillhole_model = MagicMock()
        drillhole_model.objects = self._chainable_qs([])
        mock_get_model.return_value = drillhole_model
        mock_prospect.objects = self._chainable_qs([])
        mock_paginate.return_value = MagicMock()

        views.drillholes(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["model_exists"])
        self.assertIn("prospects", ctx)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Prospect")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_safely_when_drillhole_model_missing(
        self, _f, _g, mock_prospect, mock_paginate, mock_render
    ):
        mock_prospect.objects = self._chainable_qs([])

        views.drillholes(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertFalse(ctx["model_exists"])
        self.assertIsNone(ctx["page"])
        mock_paginate.assert_not_called()


# ---------------------------------------------------------------------------
# drillhole_detail
# ---------------------------------------------------------------------------


class DrillholeDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.AssayResult")
    @patch("core.views.LithologyInterval")
    @patch("core.views.DrillholeSurvey")
    @patch("core.views.get_object_or_404")
    def test_assembles_context_with_all_relations(
        self, mock_get, mock_dhsurvey, mock_litho, mock_assay, mock_render
    ):
        drillhole = MagicMock(organisation=self.org)
        mock_get.return_value = drillhole
        mock_dhsurvey.objects = self._chainable_qs(["s1"])
        mock_litho.objects = self._chainable_qs(["l1"])
        mock_assay.objects = self._chainable_qs(["a1"])

        views.drillhole_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["drillhole"], drillhole)
        for key in ("surveys", "lithology", "assays"):
            self.assertIn(key, ctx)

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        drillhole = MagicMock(organisation=MagicMock(name="other"))
        mock_get.return_value = drillhole

        with self.assertRaises(PermissionDenied):
            views.drillhole_detail(self._authed_request("get"), pk=1)


# ---------------------------------------------------------------------------
# drillhole_import
# ---------------------------------------------------------------------------


class DrillholeImportTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Process")
    @patch("core.views.Organisation")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_get_renders_form_with_orgs_and_processes(
        self, _f, mock_org_model, mock_process, mock_render
    ):
        mock_org_model.objects = self._chainable_qs([MagicMock()])
        mock_process.objects = self._chainable_qs([MagicMock()])

        # superuser bypasses the role check.
        self.user.is_superuser = True
        self.user.save()

        views.drillhole_import(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertIn("organisations", ctx)
        self.assertIn("processes", ctx)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Process")
    @patch("core.views.Organisation")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_post_with_missing_fields_collects_form_errors(
        self, _f, mock_org_model, mock_process, mock_render
    ):
        self.user.is_superuser = True
        self.user.save()
        mock_org_model.objects = self._chainable_qs([])
        mock_process.objects = self._chainable_qs([])

        views.drillhole_import(self._authed_request("post"))

        ctx = mock_render.call_args[0][2]
        self.assertEqual(len(ctx["form_errors"]), 3)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.log_audit")
    @patch("core.views.run_drillhole_import")
    @patch("core.views.Process")
    @patch("core.views.Organisation")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_dry_run_does_not_write_audit_log(
        self, _f, mock_org_model, mock_process, mock_run, mock_audit, _render
    ):
        self.user.is_superuser = True
        self.user.save()
        mock_org_model.objects = self._chainable_qs([])
        mock_process.objects = self._chainable_qs([])
        mock_org_model.objects.get.return_value = MagicMock()
        mock_process.objects.get.return_value = MagicMock()
        mock_run.return_value = {"counters": {}, "errors": []}

        request = self._authed_request(
            "post",
            data={"organisation": "1", "process": "1", "dry_run": "on"},
            files={"file": MagicMock()},
        )
        views.drillhole_import(request)

        mock_audit.assert_not_called()

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.run_drillhole_import")
    @patch("core.views.Process")
    @patch("core.views.Organisation")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_import_exception_is_captured_as_form_error(
        self, _f, mock_org_model, mock_process, mock_run, mock_render
    ):
        self.user.is_superuser = True
        self.user.save()
        mock_org_model.objects = self._chainable_qs([])
        mock_process.objects = self._chainable_qs([])
        mock_org_model.objects.get.return_value = MagicMock()
        mock_process.objects.get.return_value = MagicMock()
        mock_run.side_effect = ValueError("bad CSV column")

        request = self._authed_request(
            "post",
            data={"organisation": "1", "process": "1"},
            files={"file": MagicMock()},
        )
        views.drillhole_import(request)

        ctx = mock_render.call_args[0][2]
        self.assertTrue(any("bad CSV column" in e for e in ctx["form_errors"]))


# ---------------------------------------------------------------------------
# tenements (list, create, detail, edit)
# ---------------------------------------------------------------------------


class TenementsTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_list_renders_safely_when_model_missing(
        self, _f, _g, mock_paginate, mock_render
    ):
        views.tenements(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertFalse(ctx["model_exists"])
        self.assertIsNone(ctx["page"])
        mock_paginate.assert_not_called()

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views._get_model")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_list_renders_with_page_when_model_present(
        self, _f, mock_get_model, mock_paginate, mock_render
    ):
        ten_model = MagicMock()
        ten_model.objects = self._chainable_qs([])
        mock_get_model.return_value = ten_model
        mock_paginate.return_value = MagicMock()

        views.tenements(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["model_exists"])


class CreateTenementTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.TenementForm")
    def test_get_seeds_process_from_query_param(self, mock_form_cls, _render):
        mock_form_cls.return_value = MagicMock()

        views.create_tenement(self._authed_request("get", path="/?process=42"))

        _, kwargs = mock_form_cls.call_args
        self.assertEqual(kwargs["initial"], {"process": "42"})

    @patch("core.views.messages")
    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.TenementForm")
    def test_valid_post_creates_tenement_and_redirects(
        self, mock_form_cls, mock_redirect, _audit, mock_messages
    ):
        tenement = MagicMock(pk=12, name="EL1234")
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = tenement
        mock_form_cls.return_value = form

        views.create_tenement(self._authed_request("post"))

        mock_redirect.assert_called_with("tenement_detail", pk=12)
        mock_messages.success.assert_called_once()


class TenementDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Tenement")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_recent_documents_limited_to_ten(
        self, _f, mock_ten, mock_get, mock_document, mock_render
    ):
        tenement = MagicMock()
        mock_ten.objects = self._chainable_qs([tenement])
        mock_get.return_value = tenement
        doc_qs = self._chainable_qs(list(range(20)))
        mock_document.objects = doc_qs

        views.tenement_detail(self._authed_request("get"), pk=1)

        doc_qs.__getitem__.assert_any_call(slice(None, 10, None))


class EditTenementTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.TenementForm")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Tenement")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_get_passes_initial_geojson(
        self, _f, mock_ten, mock_get, mock_form_cls, mock_render
    ):
        tenement = MagicMock()
        tenement.geom = MagicMock()
        tenement.geom.json = '{"type":"Polygon"}'
        mock_ten.objects = self._chainable_qs([tenement])
        mock_get.return_value = tenement
        mock_form_cls.return_value = MagicMock()

        views.edit_tenement(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["initial_geojson"], '{"type":"Polygon"}')
        self.assertTrue(ctx["editing"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.TenementForm")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Tenement")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_get_handles_tenement_without_geom(
        self, _f, mock_ten, mock_get, mock_form_cls, mock_render
    ):
        tenement = MagicMock(geom=None)
        mock_ten.objects = self._chainable_qs([tenement])
        mock_get.return_value = tenement
        mock_form_cls.return_value = MagicMock()

        views.edit_tenement(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["initial_geojson"], "")

    @patch("core.views.messages")
    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.TenementForm")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Tenement")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_valid_post_saves_and_redirects_to_detail(
        self, _f, mock_ten, mock_get, mock_form_cls, mock_redirect, _audit, _msg
    ):
        tenement = MagicMock(pk=7)
        tenement.name = "EL7"
        mock_ten.objects = self._chainable_qs([tenement])
        mock_get.return_value = tenement
        form = MagicMock()
        form.is_valid.return_value = True
        mock_form_cls.return_value = form

        views.edit_tenement(self._authed_request("post"), pk=7)

        form.save.assert_called_once()
        mock_redirect.assert_called_with("tenement_detail", pk=7)


# ---------------------------------------------------------------------------
# edit_process_geometry
# ---------------------------------------------------------------------------


class EditProcessGeometryTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_get_passes_existing_geojson(self, _f, mock_process, mock_get, mock_render):
        process = MagicMock()
        process.geom = MagicMock()
        process.geom.json = '{"type":"MultiPolygon"}'
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process

        views.edit_process_geometry(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["initial_geojson"], '{"type":"MultiPolygon"}')

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.messages")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_post_with_empty_geojson_flashes_error(
        self, _f, mock_process, mock_get, mock_messages, _render
    ):
        process = MagicMock()
        process.geom = None
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process

        views.edit_process_geometry(
            self._authed_request("post", data={"geom_geojson": "  "}), pk=1
        )

        mock_messages.error.assert_called_once()
        process.save.assert_not_called()

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.messages")
    @patch("django.contrib.gis.geos.GEOSGeometry")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_post_with_invalid_geojson_flashes_error(
        self, _f, mock_process, mock_get, mock_geos, mock_messages, _render
    ):
        process = MagicMock(geom=None)
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process
        mock_geos.side_effect = ValueError("not valid")

        views.edit_process_geometry(
            self._authed_request("post", data={"geom_geojson": "bad"}), pk=1
        )

        mock_messages.error.assert_called_once()
        process.save.assert_not_called()
