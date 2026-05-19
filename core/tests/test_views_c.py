"""
Coverage:
    projects, project_detail, prospects, prospect_detail,
    create_prospect, edit_prospect, generate_prospect_report
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from core import views

from .test_views_b import _ViewTestBase

User = get_user_model()


# ---------------------------------------------------------------------------
# projects (list view)
# ---------------------------------------------------------------------------


class ProjectsViewTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_projects_template_with_paginated_qs(
        self, _f, mock_process, mock_paginate, mock_render
    ):
        mock_process.objects = self._chainable_qs(["p1", "p2", "p3"])
        mock_paginate.return_value = MagicMock(name="page")

        views.projects(self._authed_request("get"))

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/projects.html")
        self.assertIn("page", args[2])
        mock_paginate.assert_called_once()

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter")
    def test_org_filter_applied_to_queryset(self, mock_filter, mock_process, _paginate, _render):
        org_q = Q(organisation=42)
        mock_filter.return_value = org_q
        mock_process.objects = self._chainable_qs([])

        views.projects(self._authed_request("get"))

        mock_process.objects.filter.assert_called_with(org_q)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_annotates_related_counts(self, _f, mock_process, _paginate, _render):
        qs = self._chainable_qs([])
        mock_process.objects = qs

        views.projects(self._authed_request("get"))

        # The view annotates three distinct counts on each row.
        _, kwargs = qs.annotate.call_args
        self.assertIn("prospect_count", kwargs)
        self.assertIn("drillhole_count", kwargs)
        self.assertIn("document_count", kwargs)

    def test_post_request_rejected(self):
        request = self._authed_request("post")
        self.assertEqual(views.projects(request).status_code, 405)


# ---------------------------------------------------------------------------
# project_detail
# ---------------------------------------------------------------------------


class ProjectDetailViewTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.models.Tenement")
    @patch("core.views.SavedReport")
    @patch("core.views.Document")
    @patch("core.views.Drillhole")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_assembles_context_from_all_related_models(
        self,
        _f,
        mock_process,
        mock_get,
        mock_prospect,
        mock_drillhole,
        mock_document,
        mock_saved,
        mock_tenement,
        mock_render,
    ):
        proc = MagicMock(name="process")
        mock_process.objects = self._chainable_qs([proc])
        mock_get.return_value = proc

        mock_prospect.objects = self._chainable_qs(["pros1"])
        mock_drillhole.objects = self._chainable_qs(["dh1"])
        mock_tenement.objects = self._chainable_qs(["t1"])
        mock_document.objects = self._chainable_qs(["d1", "d2"], count=12)
        mock_saved.objects = self._chainable_qs(["r1"])

        views.project_detail(self._authed_request("get"), pk=1)

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/project_detail.html")
        ctx = args[2]
        self.assertIs(ctx["process"], proc)
        for key in ("prospects", "drillholes", "tenements", "documents", "reports"):
            self.assertIn(key, ctx)
        # documents_total uses .count() on the full qs.
        self.assertEqual(ctx["documents_total"], 12)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.models.Tenement")
    @patch("core.views.SavedReport")
    @patch("core.views.Document")
    @patch("core.views.Drillhole")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_documents_limited_to_ten(
        self,
        _f,
        mock_process,
        mock_get,
        mock_prospect,
        mock_drillhole,
        mock_document,
        mock_saved,
        mock_tenement,
        _render,
    ):
        proc = MagicMock()
        mock_process.objects = self._chainable_qs([proc])
        mock_get.return_value = proc
        mock_prospect.objects = self._chainable_qs([])
        mock_drillhole.objects = self._chainable_qs([])
        mock_tenement.objects = self._chainable_qs([])
        doc_qs = self._chainable_qs(list(range(20)), count=20)
        mock_document.objects = doc_qs
        mock_saved.objects = self._chainable_qs([])

        views.project_detail(self._authed_request("get"), pk=1)

        # [:10] slice was invoked.
        doc_qs.__getitem__.assert_any_call(slice(None, 10, None))

    def test_post_rejected(self):
        request = self._authed_request("post")
        self.assertEqual(views.project_detail(request, pk=1).status_code, 405)


# ---------------------------------------------------------------------------
# prospects (list view)
# ---------------------------------------------------------------------------


class ProspectsListViewTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views._get_model")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_with_page_when_model_exists(
        self, _f, mock_get_model, mock_paginate, mock_render
    ):
        prospect = MagicMock()
        prospect.objects = self._chainable_qs(["p1"])
        mock_get_model.return_value = prospect
        mock_paginate.return_value = MagicMock(name="page")

        views.prospects(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["model_exists"])
        self.assertIsNotNone(ctx["page"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_with_empty_page_when_model_missing(self, _f, _g, mock_paginate, mock_render):
        views.prospects(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertFalse(ctx["model_exists"])
        self.assertIsNone(ctx["page"])
        # Don't paginate something that doesn't exist.
        mock_paginate.assert_not_called()


# ---------------------------------------------------------------------------
# prospect_detail
# ---------------------------------------------------------------------------


class ProspectDetailViewTests(_ViewTestBase):
    def _build_prospect(self, *, organisation=None, with_area=True):
        prospect = MagicMock(
            pk=1,
            organisation=organisation if organisation is not None else self.org,
            process=MagicMock(),
        )
        if with_area:
            prospect.area_geom = MagicMock()
            prospect.area_geom.geojson = '{"type":"Polygon","coordinates":[]}'
        else:
            prospect.area_geom = None
        return prospect

    def _patch_all_relations(
        self,
        prospect,
        *,
        drillholes=None,
        tenements=None,
        reports=None,
        samples=None,
        surveys=None,
        doc_links=None,
    ):
        """Apply the common set of model patches needed by this view."""
        patches = [
            patch("core.views.get_object_or_404", return_value=prospect),
            patch("core.views.DocLink"),
            patch("core.views.ContentType"),
            patch("core.views.Drillhole"),
            patch("core.views.Tenement"),
            patch("core.views.SavedReport"),
            patch("core.views.Sample"),
            patch("core.views.Survey"),
            patch(
                "django.core.serializers.serialize",
                return_value='{"type":"FeatureCollection","features":[]}',
            ),
            patch("core.views.render", return_value=MagicMock()),
        ]
        started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])
        (
            _get_obj,
            mock_doclink,
            _ct,
            mock_drill,
            mock_ten,
            mock_saved,
            mock_sample,
            mock_survey,
            _mock_serialize,
            mock_render,
        ) = started

        mock_doclink.objects = self._chainable_qs(doc_links or [])
        mock_drill.objects = self._chainable_qs(drillholes or [])
        mock_ten.objects = self._chainable_qs(tenements or [])
        mock_saved.objects = self._chainable_qs(reports or [])
        mock_sample.objects = self._chainable_qs(samples or [])
        mock_survey.objects = self._chainable_qs(surveys or [])

        return {"render": mock_render}

    def test_superuser_can_view_prospect_in_other_org(self):
        self.user.is_superuser = True
        self.user.save()
        other_org = MagicMock(name="other org")
        prospect = self._build_prospect(organisation=other_org)
        mocks = self._patch_all_relations(prospect)

        views.prospect_detail(self._authed_request("get"), pk=1)
        mocks["render"].assert_called_once()

    def test_cross_org_user_blocked(self):
        other_org = MagicMock(name="other org")
        prospect = self._build_prospect(organisation=other_org)
        self._patch_all_relations(prospect)

        with self.assertRaises(PermissionDenied):
            views.prospect_detail(self._authed_request("get"), pk=1)

    def test_same_org_user_gets_full_context(self):
        prospect = self._build_prospect()
        mocks = self._patch_all_relations(
            prospect,
            drillholes=["dh1"],
            samples=["s1"],
            surveys=["sv1"],
        )

        views.prospect_detail(self._authed_request("get"), pk=1)

        ctx = mocks["render"].call_args[0][2]
        for key in (
            "prospect",
            "doc_links",
            "drillholes",
            "tenements",
            "prospect_reports",
            "samples",
            "surveys",
            "drillholes_geojson",
            "tenements_geojson",
            "area_geom_geojson",
        ):
            self.assertIn(key, ctx, msg=f"Missing context key: {key}")

    def test_area_geom_null_when_prospect_has_no_polygon(self):
        prospect = self._build_prospect(with_area=False)
        mocks = self._patch_all_relations(prospect)

        views.prospect_detail(self._authed_request("get"), pk=1)

        ctx = mocks["render"].call_args[0][2]
        # The literal string "null" — that's what the template expects.
        self.assertEqual(ctx["area_geom_geojson"], "null")

    def test_area_geom_serialised_to_json_when_present(self):
        prospect = self._build_prospect(with_area=True)
        mocks = self._patch_all_relations(prospect)

        views.prospect_detail(self._authed_request("get"), pk=1)

        ctx = mocks["render"].call_args[0][2]

        parsed = json.loads(ctx["area_geom_geojson"])
        self.assertEqual(parsed["type"], "Polygon")


# ---------------------------------------------------------------------------
# create_prospect
# ---------------------------------------------------------------------------


class CreateProspectTests(_ViewTestBase):
    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    def test_user_without_organisation_redirected_with_error(self, mock_redirect, mock_messages):
        self.profile.organisation = None

        views.create_prospect(self._authed_request("get"))

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("prospects")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.Process")
    def test_get_renders_blank_form_with_default_map_centre(
        self, mock_process, mock_form_cls, mock_render
    ):
        mock_form_cls.return_value = MagicMock()

        views.create_prospect(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        # Default centre is the geographic middle of Australia-ish.
        self.assertEqual(ctx["initial_lat"], -25.0)
        self.assertEqual(ctx["initial_lng"], 133.0)
        self.assertEqual(ctx["initial_zoom"], 4)
        self.assertEqual(ctx["initial_area_geojson"], "null")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.Process")
    def test_get_with_project_param_prefills_initial_process(
        self, mock_process, mock_form_cls, _mock_render
    ):
        target_process = MagicMock(name="proc-7")
        mock_process.objects.get.return_value = target_process
        mock_form_cls.return_value = MagicMock()

        views.create_prospect(self._authed_request("get", path="/?project=7"))

        # Form was constructed with initial_process=target_process.
        _, kwargs = mock_form_cls.call_args
        self.assertIs(kwargs["initial_process"], target_process)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.Process")
    def test_get_with_invalid_project_id_silently_falls_back(
        self, mock_process, mock_form_cls, _render
    ):
        mock_process.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_process.objects.get.side_effect = mock_process.DoesNotExist
        mock_form_cls.return_value = MagicMock()

        # Should not raise.
        views.create_prospect(self._authed_request("get", path="/?project=999"))

        _, kwargs = mock_form_cls.call_args
        self.assertIsNone(kwargs["initial_process"])

    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("django.contrib.gis.geos.Point")
    @patch("core.views.ProspectForm")
    def test_valid_post_creates_prospect_with_point_geom(
        self, mock_form_cls, mock_point_cls, mock_redirect, mock_audit
    ):
        prospect = MagicMock(pk=42, name="Site A")
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = prospect
        form.cleaned_data = {"latitude": -31.95, "longitude": 115.86}
        mock_form_cls.return_value = form

        point = MagicMock(name="point")
        mock_point_cls.return_value = point

        views.create_prospect(self._authed_request("post"))

        # Note ordering: Point(lng, lat) - easy to get wrong, easy to regress.
        mock_point_cls.assert_called_once_with(115.86, -31.95, srid=4326)
        self.assertIs(prospect.geom, point)
        self.assertIs(prospect.organisation, self.org)
        prospect.save.assert_called_once()
        mock_audit.assert_called_once()
        mock_redirect.assert_called_with("prospect_detail", pk=42)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    def test_invalid_post_renders_full_form_for_non_htmx(self, mock_form_cls, mock_render):
        form = MagicMock()
        form.is_valid.return_value = False
        mock_form_cls.return_value = form

        views.create_prospect(self._authed_request("post"))

        # Renders the full page, not the partial.
        self.assertEqual(mock_render.call_args[0][1], "core/prospect_form.html")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    def test_invalid_post_renders_partial_for_htmx(self, mock_form_cls, mock_render):
        form = MagicMock()
        form.is_valid.return_value = False
        mock_form_cls.return_value = form

        request = self._authed_request("post")
        request.headers = {"HX-Request": "true"}
        views.create_prospect(request)

        self.assertEqual(
            mock_render.call_args[0][1],
            "core/partials/prospect_form_partial.html",
        )


# ---------------------------------------------------------------------------
# edit_prospect
# ---------------------------------------------------------------------------


class EditProspectTests(_ViewTestBase):
    def _build_prospect(self, *, geom=True, area=True):
        prospect = MagicMock(pk=1, organisation=self.org, name="Site A")
        if geom:
            prospect.geom = MagicMock()
            prospect.geom.x = 115.86
            prospect.geom.y = -31.95
        else:
            prospect.geom = None
        if area:
            prospect.area_geom = MagicMock()
            prospect.area_geom.geojson = '{"type":"Polygon","coordinates":[]}'
        else:
            prospect.area_geom = None
        return prospect

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.get_object_or_404")
    def test_get_uses_existing_geom_for_map_centre(self, mock_get, mock_form_cls, mock_render):
        prospect = self._build_prospect(geom=True)
        mock_get.return_value = prospect
        mock_form_cls.return_value = MagicMock()

        views.edit_prospect(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["editing"])
        self.assertEqual(ctx["initial_lat"], -31.95)
        self.assertEqual(ctx["initial_lng"], 115.86)
        self.assertEqual(ctx["initial_zoom"], 10)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.get_object_or_404")
    def test_get_falls_back_to_default_centre_when_no_geom(
        self, mock_get, mock_form_cls, mock_render
    ):
        prospect = self._build_prospect(geom=False, area=False)
        mock_get.return_value = prospect
        mock_form_cls.return_value = MagicMock()

        views.edit_prospect(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["initial_lat"], -25.0)
        self.assertEqual(ctx["initial_lng"], 133.0)
        self.assertEqual(ctx["initial_zoom"], 4)
        self.assertEqual(ctx["initial_area_geojson"], "null")

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        other_org = MagicMock(name="other org")
        prospect = self._build_prospect()
        prospect.organisation = other_org
        mock_get.return_value = prospect

        with self.assertRaises(PermissionDenied):
            views.edit_prospect(self._authed_request("get"), pk=1)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_superuser_bypasses_org_check(self, mock_get, _render):
        self.user.is_superuser = True
        self.user.save()
        other_org = MagicMock(name="other org")
        prospect = self._build_prospect()
        prospect.organisation = other_org
        mock_get.return_value = prospect

        with patch("core.views.ProspectForm", return_value=MagicMock()):
            views.edit_prospect(self._authed_request("get"), pk=1)

    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("django.contrib.gis.geos.Point")
    @patch("core.views.ProspectForm")
    @patch("core.views.get_object_or_404")
    def test_valid_post_updates_geom_and_redirects_to_detail(
        self, mock_get, mock_form_cls, mock_point_cls, mock_redirect, mock_audit
    ):
        prospect = self._build_prospect()
        mock_get.return_value = prospect

        updated = MagicMock(pk=1, name="Updated")
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = updated
        form.cleaned_data = {"latitude": 10.0, "longitude": 20.0}
        mock_form_cls.return_value = form

        point = MagicMock()
        mock_point_cls.return_value = point

        views.edit_prospect(self._authed_request("post"), pk=1)

        mock_point_cls.assert_called_once_with(20.0, 10.0, srid=4326)
        self.assertIs(updated.geom, point)
        updated.save.assert_called_once()
        mock_audit.assert_called_once()
        mock_redirect.assert_called_with("prospect_detail", pk=1)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.ProspectForm")
    @patch("core.views.get_object_or_404")
    def test_invalid_post_re_renders_with_existing_prospect_geom(
        self, mock_get, mock_form_cls, mock_render
    ):
        prospect = self._build_prospect(geom=True, area=True)
        mock_get.return_value = prospect

        form = MagicMock()
        form.is_valid.return_value = False
        mock_form_cls.return_value = form

        views.edit_prospect(self._authed_request("post"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["editing"])
        # Map snaps back to the existing prospect's geom on error.
        self.assertEqual(ctx["initial_lat"], -31.95)
        self.assertEqual(ctx["initial_lng"], 115.86)


# ---------------------------------------------------------------------------
# generate_prospect_report
# ---------------------------------------------------------------------------


class GenerateProspectReportTests(_ViewTestBase):
    def _prospect(self):
        return MagicMock(
            pk=5,
            name="Site A",
            organisation=self.org,
            process=MagicMock(),
            process_id="proc-1",
        )

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.generate_project_report")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_creates_new_report_when_no_existing_title(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_gen,
        mock_saved,
        mock_document,
        mock_redirect,
    ):
        prospect = self._prospect()
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])
        mock_gen.return_value = ("# Body", ["doc-1", "doc-2"])

        # No existing report with this title.
        mock_saved.objects = self._chainable_qs([])
        new_report = MagicMock(pk=99)
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        mock_document.objects = self._chainable_qs([])

        request = self._authed_request("post", path="/", data={"report_title": ""})
        views.generate_prospect_report(request, pk=5)

        mock_gen.assert_called_once_with("proc-1", clearance_level="PUBLIC")
        # New report uses the default title pattern.
        _, kwargs = mock_saved.objects.create.call_args
        self.assertIn("Site A", kwargs["title"])
        self.assertEqual(kwargs["version_number"], 1)
        # And we redirect into the editor for the new report.
        mock_redirect.assert_called_with("saved_report_editor", report_id=99)

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.generate_project_report")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_creates_new_version_when_title_already_exists(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_gen,
        mock_saved,
        mock_document,
        mock_redirect,
    ):
        prospect = self._prospect()
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])
        mock_gen.return_value = ("body", [])

        existing = MagicMock(pk=10)
        existing_qs = self._chainable_qs([existing])
        mock_saved.objects.filter.return_value = existing_qs
        mock_saved.ChangeReason.REGENERATED = "REGENERATED"

        new_version = MagicMock(pk=11)
        mock_saved.create_version.return_value = new_version
        mock_document.objects = self._chainable_qs([])

        request = self._authed_request("post", data={"report_title": "Custom Title"})
        views.generate_prospect_report(request, pk=5)

        # We branched into create_version, not objects.create.
        mock_saved.create_version.assert_called_once()
        mock_saved.objects.create.assert_not_called()
        mock_redirect.assert_called_with("saved_report_editor", report_id=11)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.generate_project_report")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_generation_exception_flashes_error_and_redirects_back(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_gen,
        mock_redirect,
        mock_messages,
    ):
        prospect = self._prospect()
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])
        mock_gen.side_effect = RuntimeError("LLM unavailable")

        views.generate_prospect_report(self._authed_request("post"), pk=5)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("prospect_detail", pk=5)

    @patch("core.views.generate_project_report")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_user_without_org_visibility_blocked(self, _f, mock_get, mock_prospect_model, _gen):
        prospect = self._prospect()
        mock_get.return_value = prospect
        # The org-scoped filter returns no rows for this user.
        mock_prospect_model.objects = self._chainable_qs([])

        with self.assertRaises(PermissionDenied):
            views.generate_prospect_report(self._authed_request("post"), pk=5)

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.generate_project_report")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_source_documents_linked_when_doc_ids_returned(
        self,
        _f,
        mock_get,
        mock_prospect_model,
        mock_gen,
        mock_saved,
        mock_document,
        _redir,
    ):
        prospect = self._prospect()
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])
        mock_gen.return_value = ("body", ["d1", "d2", "d3"])

        mock_saved.objects = self._chainable_qs([])
        new_report = MagicMock()
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        doc_qs = self._chainable_qs(["d1", "d2", "d3"])
        mock_document.objects = doc_qs

        views.generate_prospect_report(self._authed_request("post"), pk=5)

        # m2m setter called with the document queryset filtered to the ids.
        new_report.source_documents.set.assert_called_once()
        mock_document.objects.filter.assert_called_with(pk__in=["d1", "d2", "d3"])

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views.generate_project_report", return_value=("body", []))
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_empty_doc_ids_skips_source_document_setter(
        self, _f, mock_get, mock_prospect_model, _gen, mock_saved, _redir
    ):
        prospect = self._prospect()
        mock_get.return_value = prospect
        mock_prospect_model.objects = self._chainable_qs([prospect])
        mock_saved.objects = self._chainable_qs([])
        new_report = MagicMock()
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        views.generate_prospect_report(self._authed_request("post"), pk=5)

        new_report.source_documents.set.assert_not_called()

    def test_get_request_rejected(self):
        # @require_POST.
        request = self._authed_request("get")
        self.assertEqual(views.generate_prospect_report(request, pk=5).status_code, 405)
