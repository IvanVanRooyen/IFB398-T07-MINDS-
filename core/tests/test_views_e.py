"""
Coverage:
    ai_insights, map_view, healthcheck,
    project_report_pdf, project_report_docx,
    document_analysis_detail, save_document_analysis,
    geojson_projects, geojson_tenements, geojson_prospects, geojson_drillholes,
    spatial_search,
    report_list_page, generate_report, report_editor, saved_report_editor,
    save_report, update_saved_report
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, JsonResponse

from core import views

from .test_views_b import _ViewTestBase

User = get_user_model()

# ---------------------------------------------------------------------------
# ai_insights, map_view, healthcheck
# ---------------------------------------------------------------------------


class AiInsightsTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.SavedReport")
    @patch("core.views.Process")
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_with_three_recent_collections(
        self, _f, mock_doc, mock_process, mock_saved, mock_render
    ):
        mock_doc.objects = self._chainable_qs([])
        mock_process.objects = self._chainable_qs([])
        mock_saved.objects = self._chainable_qs([])

        views.ai_insights(self._authed_request("get"))

        ctx = mock_render.call_args[0][2]
        self.assertEqual(mock_render.call_args[0][1], "core/ai_insights.html")
        for key in ("recent_docs", "recent_projects", "recent_reports"):
            self.assertIn(key, ctx)


class MapViewTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    def test_renders_map_template(self, mock_render):
        views.map_view(self._authed_request("get"))
        self.assertEqual(mock_render.call_args[0][1], "core/map.html")


class HealthcheckTests(_ViewTestBase):
    def test_returns_json_ok(self):
        request = self.factory.get("/health/")

        response = views.healthcheck(request)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    def test_post_request_rejected(self):
        request = self.factory.post("/health/")
        self.assertEqual(views.healthcheck(request).status_code, 405)


# ---------------------------------------------------------------------------
# project_report_pdf
# ---------------------------------------------------------------------------


class ProjectReportPdfTests(_ViewTestBase):
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_raises_404_when_process_not_visible_to_user(self, _f, mock_process):
        mock_process.objects = self._chainable_qs([])

        with self.assertRaises(Http404):
            views.project_report_pdf(self._authed_request("get"), process_id="p1")

    @patch("core.views._get_cached_report_md", side_effect=RuntimeError("Granite down"))
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_returns_503_when_cache_generation_fails(self, _f, mock_process, _cache):
        mock_process.objects = self._chainable_qs([MagicMock()])

        response = views.project_report_pdf(
            self._authed_request("get"), process_id="p1"
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Granite", response.content)

    @patch("core.views.SimpleDocTemplate")
    @patch("core.views._get_cached_report_md", return_value="# Header\n\nBody text.")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_returns_pdf_with_content_disposition(
        self, _f, mock_process, _cache, mock_doc_cls
    ):
        proc = MagicMock()
        proc.name = "My Project"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        doc_instance = MagicMock()
        mock_doc_cls.return_value = doc_instance

        response = views.project_report_pdf(
            self._authed_request("get"), process_id="p1"
        )

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("My_Project_report.pdf", response["Content-Disposition"])

        # the simpleDocTemplate was actually built
        doc_instance.build.assert_called_once()

    @patch("core.views.Paragraph")
    @patch("core.views.SimpleDocTemplate")
    @patch("core.views._get_cached_report_md")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_each_markdown_line_type_produces_a_paragraph(
        self, _f, mock_process, mock_cache, mock_doc_cls, mock_paragraph
    ):
        proc = MagicMock()
        proc.name = "P"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        # hit every branch in the markdown converter at least once.
        mock_cache.return_value = (
            "# H1 heading\n"
            "## H2 heading\n"
            "### H3 heading\n"
            "- bullet item\n"
            "* asterisk bullet\n"
            "1. numbered item\n"
            "regular body line\n"
            "\n"
        )

        views.project_report_pdf(self._authed_request("get"), process_id="p1")

        # 7 Paragraph(...) calls - one per non-blank line (blank lines produce spacer,
        # not paragraph.)
        self.assertEqual(mock_paragraph.call_count, 7)

    @patch("core.views.SimpleDocTemplate")
    @patch("core.views._get_cached_report_md", return_value="body")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_filename_slug_sanitises_special_characters(
        self, _f, mock_process, _cache, _doc_cls
    ):
        proc = MagicMock()
        proc.name = "Project / With * Bad: Chars"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        response = views.project_report_pdf(
            self._authed_request("get"), process_id="p1"
        )

        # Only word chars and hyphens survive the slug.
        disposition = response["Content-Disposition"]
        self.assertNotIn("/", disposition.replace("filename=", ""))
        self.assertNotIn("*", disposition)
        self.assertNotIn(":", disposition.replace("filename=", "").replace('"', ""))


# ---------------------------------------------------------------------------
# project_report_docx
# ---------------------------------------------------------------------------


class ProjectReportDocxTests(_ViewTestBase):
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_404_when_not_visible(self, _f, mock_process):
        mock_process.objects = self._chainable_qs([])

        with self.assertRaises(Http404):
            views.project_report_docx(self._authed_request("get"), process_id="p1")

    @patch("core.views._get_cached_report_md", side_effect=RuntimeError("down"))
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_503_when_cache_fails(self, _f, mock_process, _cache):
        mock_process.objects = self._chainable_qs([MagicMock()])

        response = views.project_report_docx(
            self._authed_request("get"), process_id="p1"
        )

        self.assertEqual(response.status_code, 503)

    @patch("core.views.DocxDocument")
    @patch("core.views._get_cached_report_md", return_value="# Title\n\nbody")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_returns_docx_with_content_disposition(
        self, _f, mock_process, _cache, mock_docx_cls
    ):
        proc = MagicMock()
        proc.name = "MyProj"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        instance = MagicMock()
        mock_docx_cls.return_value = instance

        response = views.project_report_docx(
            self._authed_request("get"), process_id="p1"
        )

        self.assertIn("wordprocessingml", response["Content-Type"])
        self.assertIn("MyProj_report.docx", response["Content-Disposition"])
        instance.save.assert_called_once()

    @patch("core.views.DocxDocument")
    @patch("core.views._get_cached_report_md")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_markdown_headers_use_add_heading_with_level(
        self, _f, mock_process, mock_cache, mock_docx_cls
    ):
        proc = MagicMock()
        proc.name = "P"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        mock_cache.return_value = "# h1\n## h2\n### h3\n"

        instance = MagicMock()
        mock_docx_cls.return_value = instance

        views.project_report_docx(self._authed_request("get"), process_id="p1")

        # add_heading called three times, once per heading level
        levels_used = sorted(
            c.kwargs.get("level") for c in instance.add_heading.call_args_list
        )
        self.assertEqual(levels_used, [1, 2, 3])

    @patch("core.views.DocxDocument")
    @patch("core.views._get_cached_report_md")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_bullets_and_numbered_lists_use_correct_styles(
        self, _f, mock_process, mock_cache, mock_docx_cls
    ):
        proc = MagicMock()
        proc.name = "P"
        mock_process.objects = self._chainable_qs([proc])
        mock_process.objects.get.return_value = proc

        mock_cache.return_value = "- bullet\n* star\n1. numbered\n"

        instance = MagicMock()
        mock_docx_cls.return_value = instance

        views.project_report_docx(self._authed_request("get"), process_id="p1")

        styles_used = [
            c.kwargs.get("style")
            for c in instance.add_paragraph.call_args_list
            if c.kwargs.get("style")
        ]
        # two bullets, one numbered
        self.assertEqual(styles_used.count("List Bullet"), 2)
        self.assertEqual(styles_used.count("List Number"), 1)


# ---------------------------------------------------------------------------
# document_analysis_detail & save_document_analysis
# ---------------------------------------------------------------------------


class DocumentAnalysisDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_falls_back_to_default_when_analysis_text_missing(
        self, mock_get, mock_render
    ):
        # Build a doc that explicitly has no analysis_text attribute.
        document = MagicMock(organisation=self.org, spec=["organisation"])
        mock_get.return_value = document

        views.document_analysis_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["analysis"], "No insights available yet.")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_empty_string_analysis_falls_back_to_default(self, mock_get, mock_render):
        document = MagicMock(organisation=self.org, analysis_text="")
        mock_get.return_value = document

        views.document_analysis_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["analysis"], "No insights available yet.")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_uses_analysis_text_when_present(self, mock_get, mock_render):
        document = MagicMock(organisation=self.org, analysis_text="Real insights.")
        mock_get.return_value = document

        views.document_analysis_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["analysis"], "Real insights.")

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        document = MagicMock(organisation=MagicMock(name="other"))
        mock_get.return_value = document

        with self.assertRaises(PermissionDenied):
            views.document_analysis_detail(self._authed_request("get"), pk=1)


class SaveDocumentAnalysisTests(_ViewTestBase):
    def test_returns_placeholder_response(self):
        response = views.save_document_analysis(self._authed_request("post"), pk=1)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"placeholder", response.content)

    def test_get_rejected(self):
        # @require_POST
        request = self._authed_request("get")
        self.assertEqual(views.save_document_analysis(request, pk=1).status_code, 405)


# ---------------------------------------------------------------------------
# GeoJSON endpoints (projects, tenements, prospects, drillholes)
# ---------------------------------------------------------------------------


class GeoJsonProjectsTests(_ViewTestBase):
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_empty_qs_returns_empty_feature_collection(self, _f, mock_process):
        mock_process.objects = self._chainable_qs([])

        response = views.geojson_projects(self._authed_request("get"))

        payload = json.loads(response.content)
        self.assertEqual(payload, {"type": "FeatureCollection", "features": []})

    @patch("django.core.serializers.serialize")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_uses_geodjango_serializer_when_processes_present(
        self, _f, mock_process, mock_serialize
    ):
        mock_process.objects = self._chainable_qs([MagicMock()])
        mock_serialize.return_value = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {}, "properties": {}}],
            }
        )

        response = views.geojson_projects(self._authed_request("get"))

        payload = json.loads(response.content)
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(len(payload["features"]), 1)
        # The serializer was invoked with the right geometry field.
        _, kwargs = mock_serialize.call_args
        self.assertEqual(kwargs.get("geometry_field"), "geom")


class GeoJsonTenementsTests(_ViewTestBase):
    @patch("core.views.Tenement")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_empty_collection_when_no_tenements(self, _f, mock_ten):
        mock_ten.objects = self._chainable_qs([])

        response = views.geojson_tenements(self._authed_request("get"))

        self.assertEqual(json.loads(response.content)["features"], [])


class GeoJsonProspectsTests(_ViewTestBase):
    @patch("core.views.Prospect")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_features_include_geometry_and_properties(self, _f, mock_prospect):
        p1 = MagicMock()
        p1.pk = 1
        p1.name = "Site A"
        p1.organisation = "Acme"
        p1.process = "Project X"
        p1.geom.geojson = '{"type":"Point","coordinates":[133, -25]}'
        p1.area_geom = None
        mock_prospect.objects = self._chainable_qs([p1])

        response = views.geojson_prospects(self._authed_request("get"))

        payload = json.loads(response.content)
        feat = payload["features"][0]
        self.assertEqual(feat["type"], "Feature")
        self.assertEqual(feat["geometry"]["type"], "Point")
        self.assertEqual(feat["properties"]["name"], "Site A")

    @patch("core.views.Prospect")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_area_geom_included_when_present(self, _f, mock_prospect):
        p1 = MagicMock()
        p1.pk = 1
        p1.name = "A"
        p1.organisation = None
        p1.process = None
        p1.geom.geojson = '{"type":"Point","coordinates":[0,0]}'
        p1.area_geom = MagicMock()
        p1.area_geom.geojson = '{"type":"Polygon","coordinates":[]}'
        mock_prospect.objects = self._chainable_qs([p1])

        response = views.geojson_prospects(self._authed_request("get"))

        props = json.loads(response.content)["features"][0]["properties"]
        self.assertIn("area_geom_geojson", props)
        self.assertEqual(props["area_geom_geojson"]["type"], "Polygon")

    @patch("core.views.Prospect")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_area_geom_omitted_when_absent(self, _f, mock_prospect):
        p = MagicMock()
        p.pk = 1
        p.name = "n"
        p.organisation = None
        p.process = None
        p.geom.geojson = '{"type":"Point","coordinates":[0,0]}'
        p.area_geom = None
        mock_prospect.objects = self._chainable_qs([p])

        response = views.geojson_prospects(self._authed_request("get"))

        props = json.loads(response.content)["features"][0]["properties"]
        self.assertNotIn("area_geom_geojson", props)


class GeoJsonDrillholesTests(_ViewTestBase):
    @patch("core.views.Drillhole")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_empty_collection_when_no_drillholes(self, _f, mock_drill):
        mock_drill.objects = self._chainable_qs([])

        response = views.geojson_drillholes(self._authed_request("get"))

        self.assertEqual(json.loads(response.content)["features"], [])


# ---------------------------------------------------------------------------
# spatial_search
# ---------------------------------------------------------------------------


class SpatialSearchTests(_ViewTestBase):
    def test_400_when_body_invalid_json(self):
        request = self._authed_request("post", body=b"not-json")
        response = views.spatial_search(request)
        self.assertEqual(response.status_code, 400)

    def test_400_when_no_geometry_in_body(self):
        request = self._authed_request("post", body=b'{"radius": 100}')
        response = views.spatial_search(request)
        self.assertEqual(response.status_code, 400)

    @patch("django.contrib.gis.geos.GEOSGeometry")
    def test_400_when_geometry_construction_raises(self, mock_geos):
        mock_geos.side_effect = ValueError("bad WKT")
        body = json.dumps({"geometry": {"type": "Point", "coordinates": [0, 0]}})
        response = views.spatial_search(self._authed_request("post", body=body))
        self.assertEqual(response.status_code, 400)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._get_model", return_value=None)
    @patch("core.views.Process")
    @patch("django.contrib.gis.geos.GEOSGeometry")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_point_with_radius_buffers_into_circle(
        self, _f, mock_geos, mock_process, _get_model, mock_render
    ):
        point = MagicMock()
        point.geom_type = "Point"
        buffered = MagicMock(geom_type="Polygon")
        point.buffer.return_value = buffered
        mock_geos.return_value = point

        mock_process.objects = self._chainable_qs([])

        body = json.dumps(
            {
                "geometry": {"type": "Point", "coordinates": [133.0, -25.0]},
                "radius": 5000,
            }
        )
        views.spatial_search(self._authed_request("post", body=body))

        # 5000m/111111 ≈ 0.045 degrees (pin the conversion)
        point.buffer.assert_called_once()
        radius_arg = point.buffer.call_args[0][0]
        self.assertAlmostEqual(radius_arg, 5000 / 111111.0, places=4)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._get_model", return_value=None)
    @patch("core.views.Process")
    @patch("django.contrib.gis.geos.GEOSGeometry")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_non_point_geometry_used_as_is(
        self, _f, mock_geos, mock_process, _get_model, _render
    ):
        polygon = MagicMock()
        polygon.geom_type = "Polygon"
        mock_geos.return_value = polygon
        mock_process.objects = self._chainable_qs([])

        body = json.dumps({"geometry": {"type": "Polygon", "coordinates": [[[]]]}})
        views.spatial_search(self._authed_request("post", body=body))

        # polygon was NOT buffered
        polygon.buffer.assert_not_called()


# ---------------------------------------------------------------------------
# report_list_page
# ---------------------------------------------------------------------------


class ReportListPageTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views.SavedReport")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_public_user_only_sees_public_reports(
        self, _f, mock_saved, mock_process, mock_doc, _render
    ):
        self.profile.clearance_level = "PUBLIC"
        qs = self._chainable_qs([])
        mock_saved.objects.filter.return_value = qs
        mock_process.objects = self._chainable_qs([])
        mock_doc.objects = self._chainable_qs([])

        views.report_list_page(self._authed_request("get"))

        _, kwargs = mock_saved.objects.filter.call_args
        self.assertEqual(kwargs["clearance_level__in"], ["PUBLIC"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views.SavedReport")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_jorc_approved_user_sees_all_levels(
        self, _f, mock_saved, mock_process, mock_doc, _render
    ):
        self.profile.clearance_level = "JORC_APPROVED"
        qs = self._chainable_qs([])
        mock_saved.objects.filter.return_value = qs
        mock_process.objects = self._chainable_qs([])
        mock_doc.objects = self._chainable_qs([])

        views.report_list_page(self._authed_request("get"))

        _, kwargs = mock_saved.objects.filter.call_args
        self.assertEqual(
            set(kwargs["clearance_level__in"]),
            {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "JORC_APPROVED"},
        )

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views.SavedReport")
    @patch("core.views.SearchQuery")
    @patch("core.views.SearchRank")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_search_query_branch_uses_full_text_search(
        self, _f, _rank, _query, mock_saved, mock_process, mock_doc, mock_render
    ):
        qs = self._chainable_qs([])
        mock_saved.objects.filter.return_value = qs
        mock_process.objects = self._chainable_qs([])
        mock_doc.objects = self._chainable_qs([])

        views.report_list_page(self._authed_request("get", path="/?q=lithium"))

        # the .annotate(rank=...) branch was taken, and q is passed back in context
        qs.annotate.assert_called_once()
        self.assertEqual(mock_render.call_args[0][2]["q"], "lithium")


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class GenerateReportTests(_ViewTestBase):
    @patch("core.views.redirect", return_value=MagicMock())
    def test_get_request_redirects_to_report_list(self, mock_redirect):
        views.generate_report(self._authed_request("get"))
        mock_redirect.assert_called_with("report_list")

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    def test_missing_process_id_flashes_error(self, mock_redirect, mock_messages):
        views.generate_report(self._authed_request("post"))

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("report_list")

    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_404_when_process_not_visible(self, _f, mock_process):
        mock_process.objects = self._chainable_qs([])

        request = self._authed_request("post", data={"process_id": "p1"})
        with self.assertRaises(Http404):
            views.generate_report(request)

    @patch("core.views.reverse", return_value="/reports/p1/")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views._get_cached_report_bundle")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_creates_new_report_when_no_title_collision(
        self,
        _f,
        mock_process,
        mock_get,
        mock_bundle,
        mock_saved,
        mock_doc,
        mock_redirect,
        mock_reverse,
    ):
        process = MagicMock(organisation=self.org)
        process.name = "Proj A"
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process
        mock_bundle.return_value = {"md": "body", "doc_ids": []}

        mock_saved.objects = self._chainable_qs([])
        new_report = MagicMock(pk=42)
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"
        mock_doc.objects = self._chainable_qs([])

        request = self._authed_request("post", data={"process_id": "p1"})
        views.generate_report(request)

        mock_saved.objects.create.assert_called_once()
        mock_saved.create_version.assert_not_called()

    @patch("core.views.reverse", return_value="/reports/p1/")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views._get_cached_report_bundle")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_creates_new_version_when_title_exists(
        self,
        _f,
        mock_process,
        mock_get,
        mock_bundle,
        mock_saved,
        mock_doc,
        mock_redirect,
        mock_reverse,
    ):
        process = MagicMock(organisation=self.org)
        process.name = "Proj"
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process
        mock_bundle.return_value = {"md": "body", "doc_ids": ["d1"]}

        existing = MagicMock(pk=10)
        mock_saved.objects.filter.return_value = self._chainable_qs([existing])
        new_version = MagicMock(pk=11)
        mock_saved.create_version.return_value = new_version
        mock_saved.ChangeReason.REGENERATED = "REGENERATED"
        mock_doc.objects = self._chainable_qs([])

        views.generate_report(
            self._authed_request(
                "post",
                data={
                    "process_id": "p1",
                    "report_title": "Custom",
                },
            )
        )

        mock_saved.create_version.assert_called_once()
        mock_saved.objects.create.assert_not_called()
        new_version.source_documents.set.assert_called_once()

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views._get_cached_report_bundle")
    @patch("core.views.get_object_or_404")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_bundle_exception_flashes_error(
        self,
        _f,
        mock_process,
        mock_get,
        mock_bundle,
        mock_redirect,
        mock_messages,
    ):
        process = MagicMock()
        mock_process.objects = self._chainable_qs([process])
        mock_get.return_value = process
        mock_bundle.side_effect = RuntimeError("LLM down")

        views.generate_report(self._authed_request("post", data={"process_id": "p1"}))

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("report_list")


# ---------------------------------------------------------------------------
# report_editor
# ---------------------------------------------------------------------------


class ReportEditorTests(_ViewTestBase):
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_404_when_process_invisible(self, _f, mock_process):
        mock_process.DoesNotExist = type("DoesNotExist", (Exception,), {})
        qs = self._chainable_qs([])
        qs.get.side_effect = mock_process.DoesNotExist
        mock_process.objects.filter.return_value = qs

        with self.assertRaises(Http404):
            views.report_editor(self._authed_request("get"), process_id="p1")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views._get_cached_report_md", return_value="# Hi")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_editor_with_cached_markdown(
        self, _f, mock_process, mock_cache, mock_reverse, mock_render
    ):
        proc = MagicMock()
        proc.name = "Proj"
        qs = self._chainable_qs([proc])
        qs.get.return_value = proc
        mock_process.objects.filter.return_value = qs

        views.report_editor(self._authed_request("get"), process_id="p1")

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["markdown_content"], "# Hi")
        self.assertIs(ctx["process"], proc)
        self.assertIsNone(ctx["saved_report"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views._get_cached_report_md", side_effect=RuntimeError("nope"))
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_cache_failure_falls_back_to_placeholder_markdown(
        self, _f, mock_process, _cache, mock_reverse, mock_render
    ):
        proc = MagicMock()
        proc.name = "Proj"
        qs = self._chainable_qs([proc])
        qs.get.return_value = proc
        mock_process.objects.filter.return_value = qs

        views.report_editor(self._authed_request("get"), process_id="p1")

        ctx = mock_render.call_args[0][2]
        # the fallback string carries both project name and exception text
        self.assertIn("Proj", ctx["markdown_content"])
        self.assertIn("nope", ctx["markdown_content"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views._get_cached_report_md", return_value="")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_custom_title_query_param_used_as_default(
        self, _f, mock_process, _cache, _reverse, mock_render
    ):
        proc = MagicMock()
        proc.name = "Proj"
        qs = self._chainable_qs([proc])
        qs.get.return_value = proc
        mock_process.objects.filter.return_value = qs

        views.report_editor(
            self._authed_request("get", path="/?title=Custom%20Title"),
            process_id="p1",
        )

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["default_title"], "Custom Title")


# ---------------------------------------------------------------------------
# saved_report_editor
# ---------------------------------------------------------------------------


class SavedReportEditorTests(_ViewTestBase):
    def _make_report(self, *, organisation=None, clearance="PUBLIC"):
        report = MagicMock(
            pk=1,
            organisation=organisation if organisation is not None else self.org,
            clearance_level=clearance,
            content_md="# body",
            title="A report",
            process=MagicMock(),
        )
        return report

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    def test_renders_editor_with_report_context(
        self, mock_get, mock_prospect, _reverse, mock_render
    ):
        report = self._make_report()
        mock_get.return_value = report
        mock_prospect.objects = self._chainable_qs([])

        views.saved_report_editor(self._authed_request("get"), report_id=1)

        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["saved_report"], report)
        self.assertEqual(ctx["markdown_content"], "# body")

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        report = self._make_report(organisation=MagicMock(name="other"))
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.saved_report_editor(self._authed_request("get"), report_id=1)

    @patch("core.views.get_object_or_404")
    def test_user_with_lower_clearance_blocked(self, mock_get):
        # user is PUBLIC (rank 0), report is CONFIDENTIAL (rank 2)
        self.profile.clearance_level = "PUBLIC"
        report = self._make_report(clearance="CONFIDENTIAL")
        mock_get.return_value = report

        with self.assertRaises(PermissionDenied):
            views.saved_report_editor(self._authed_request("get"), report_id=1)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views.Prospect")
    @patch("core.views.get_object_or_404")
    def test_user_with_equal_clearance_allowed(
        self, mock_get, mock_prospect, _reverse, _render
    ):
        self.profile.clearance_level = "CONFIDENTIAL"
        report = self._make_report(clearance="CONFIDENTIAL")
        mock_get.return_value = report
        mock_prospect.objects = self._chainable_qs([])

        # Should not raise.
        views.saved_report_editor(self._authed_request("get"), report_id=1)


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------


class SaveReportTests(_ViewTestBase):
    def test_400_when_title_missing(self):
        request = self._authed_request("post", data={"content_md": "body"})
        response = views.save_report(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Title is required", response.content)

    def test_400_when_content_empty(self):
        request = self._authed_request("post", data={"title": "T"})
        response = views.save_report(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"empty", response.content)

    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views.log_audit")
    @patch("core.views._get_cached_report_bundle")
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.Process")
    def test_creates_new_report_when_no_collision(
        self,
        mock_process,
        mock_saved,
        mock_doc,
        _bundle,
        mock_audit,
        _reverse,
    ):
        proc = MagicMock(organisation=self.org)
        mock_process.objects.select_related.return_value = mock_process.objects
        mock_process.objects.get.return_value = proc
        mock_saved.objects.filter.return_value = self._chainable_qs([])

        new_report = MagicMock()
        new_report.id = "abc-123"
        new_report.version_number = 1
        new_report.source_documents = MagicMock()
        new_report.source_documents.exists.return_value = True  # skip cache fetch
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        request = self._authed_request(
            "post",
            data={
                "process_id": "p1",
                "title": "T",
                "content_md": "body",
            },
        )
        response = views.save_report(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["report_id"], "abc-123")
        self.assertEqual(payload["version_number"], 1)
        mock_audit.assert_called_once()

    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views.log_audit")
    @patch("core.views._get_cached_report_bundle")
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.Process")
    def test_invalid_process_id_falls_back_to_no_process(
        self,
        mock_process,
        mock_saved,
        mock_doc,
        _bundle,
        _audit,
        _reverse,
    ):
        mock_process.DoesNotExist = type("DoesNotExist", (Exception,), {})
        chain = MagicMock()
        chain.get.side_effect = mock_process.DoesNotExist
        mock_process.objects.select_related.return_value = chain

        mock_saved.objects.filter.return_value = self._chainable_qs([])
        new_report = MagicMock()
        new_report.id = "x"
        new_report.version_number = 1
        new_report.source_documents = MagicMock()
        new_report.source_documents.exists.return_value = True
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        request = self._authed_request(
            "post",
            data={
                "process_id": "bogus",
                "title": "T",
                "content_md": "body",
            },
        )
        response = views.save_report(request)

        # Did not raise - saved with process=None.
        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_saved.objects.create.call_args
        self.assertIsNone(kwargs["process"])

    @patch("core.views.reverse", side_effect=lambda name, *a, **k: f"/{name}/")
    @patch("core.views.log_audit")
    @patch("core.views._get_cached_report_bundle", side_effect=RuntimeError("x"))
    @patch("core.views.Document")
    @patch("core.views.SavedReport")
    @patch("core.views.Process")
    def test_cache_bundle_failure_does_not_break_save(
        self,
        mock_process,
        mock_saved,
        mock_doc,
        _bundle,
        _audit,
        _reverse,
    ):
        proc = MagicMock(organisation=self.org)
        mock_process.objects.select_related.return_value = mock_process.objects
        mock_process.objects.get.return_value = proc

        mock_saved.objects.filter.return_value = self._chainable_qs([])
        new_report = MagicMock()
        new_report.id = "x"
        new_report.version_number = 1
        new_report.source_documents = MagicMock()
        new_report.source_documents.exists.return_value = False  # forces cache call
        mock_saved.objects.create.return_value = new_report
        mock_saved.ChangeReason.GENERATED = "GENERATED"

        request = self._authed_request(
            "post",
            data={
                "process_id": "p1",
                "title": "T",
                "content_md": "body",
            },
        )

        response = views.save_report(request)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# update_saved_report
# ---------------------------------------------------------------------------


class UpdateSavedReportTests(_ViewTestBase):
    def _make_report(self, *, status_value="DRAFT", created_by=None):
        report = MagicMock(
            pk=1,
            created_by=created_by if created_by is not None else self.user,
        )
        report.status = status_value
        report.source_documents = MagicMock()
        report.source_documents.exists.return_value = False
        return report

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_locked_approved_report_returns_403(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        report = self._make_report(status_value="APPROVED")
        mock_get.return_value = report

        response = views.update_saved_report(self._authed_request("post"), report_id=1)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"locked", response.content)

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_locked_published_report_returns_403(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        report = self._make_report(status_value="PUBLISHED")
        mock_get.return_value = report

        response = views.update_saved_report(self._authed_request("post"), report_id=1)
        self.assertEqual(response.status_code, 403)

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_non_owner_non_admin_blocked(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        other_user = MagicMock()
        report = self._make_report(created_by=other_user)
        mock_get.return_value = report
        self.profile.role = "GEOLOGIST_EXPL"  # NOT admin

        response = views.update_saved_report(self._authed_request("post"), report_id=1)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Permission denied", response.content)

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_admin_can_edit_other_users_report(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_saved.ChangeReason.MANUAL_EDIT = "MANUAL_EDIT"
        report = self._make_report(created_by=MagicMock())  # someone else
        mock_get.return_value = report
        self.profile.role = "ADMIN"

        new_version = MagicMock(pk=2, version_number=2)
        new_version.id = "v2"
        new_version.source_documents = MagicMock()
        mock_saved.create_version.return_value = new_version

        request = self._authed_request(
            "post",
            data={
                "title": "T",
                "content_md": "body",
            },
        )
        with patch("core.views.log_audit"):
            response = views.update_saved_report(request, report_id=1)

        self.assertEqual(response.status_code, 200)

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_400_when_title_missing(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_get.return_value = self._make_report()

        request = self._authed_request("post", data={"content_md": "body"})
        response = views.update_saved_report(request, report_id=1)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_400_when_content_empty(self, mock_get, mock_saved):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_get.return_value = self._make_report()

        request = self._authed_request("post", data={"title": "T"})
        response = views.update_saved_report(request, report_id=1)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.log_audit")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_source_documents_propagated_to_new_version(
        self, mock_get, mock_saved, _audit
    ):
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_saved.ChangeReason.MANUAL_EDIT = "MANUAL_EDIT"

        report = self._make_report()
        report.pk = 1
        report.source_documents = MagicMock()
        report.source_documents.exists.return_value = True
        report.source_documents.all.return_value = ["sd1", "sd2"]
        mock_get.return_value = report

        new_version = MagicMock(version_number=2)
        new_version.pk = 2  # different from parent
        new_version.id = "v2"
        new_version.source_documents = MagicMock()
        mock_saved.create_version.return_value = new_version

        request = self._authed_request(
            "post",
            data={
                "title": "T",
                "content_md": "body",
            },
        )
        views.update_saved_report(request, report_id=1)

        new_version.source_documents.set.assert_called_with(["sd1", "sd2"])

    @patch("core.views.log_audit")
    @patch("core.views.SavedReport")
    @patch("core.views.get_object_or_404")
    def test_unchanged_content_no_propagation(self, mock_get, mock_saved, _audit):
        """When create_version returns the original (no content change), don't
        re-set source_documents — avoid an unnecessary write."""
        mock_saved.Status.APPROVED = "APPROVED"
        mock_saved.Status.PUBLISHED = "PUBLISHED"
        mock_saved.ChangeReason.MANUAL_EDIT = "MANUAL_EDIT"

        report = self._make_report()
        report.pk = 5
        report.source_documents = MagicMock()
        report.source_documents.exists.return_value = True
        report.source_documents.all.return_value = ["sd1"]
        mock_get.return_value = report

        # create_version returns the SAME report (pk matches)
        unchanged = MagicMock(version_number=1)
        unchanged.pk = 5
        unchanged.id = "v1"
        unchanged.source_documents = MagicMock()
        mock_saved.create_version.return_value = unchanged

        request = self._authed_request(
            "post",
            data={
                "title": "T",
                "content_md": "body",
            },
        )
        views.update_saved_report(request, report_id=1)

        # `set()` should not have been called (`new_version.pk` == `report.pk`)
        unchanged.source_documents.set.assert_not_called()
