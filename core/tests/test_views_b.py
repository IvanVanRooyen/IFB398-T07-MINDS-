"""
Coverage:
    Helpers:    _get_clearance_level, _report_cache_key,
                _get_cached_report_bundle, _get_cached_report_md
    Views:      upload_doc, documents, document_detail,
                delete_document, download_document, replace_document
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.test import RequestFactory, TestCase
from django.utils.datastructures import MultiValueDict

from core import views

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class GetClearanceLevelTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_with(self, user):
        r = self.factory.get("/")
        r.user = user
        return r

    def test_returns_profile_clearance_for_authenticated_user(self):
        user = MagicMock()
        user.is_authenticated = True
        user.profile.clearance_level = "CONFIDENTIAL"

        self.assertEqual(
            views._get_clearance_level(self._request_with(user)), "CONFIDENTIAL"
        )

    def test_defaults_to_public_for_anonymous_user(self):
        self.assertEqual(
            views._get_clearance_level(self._request_with(AnonymousUser())), "PUBLIC"
        )

    def test_defaults_to_public_when_profile_missing(self):
        user = MagicMock(spec=["is_authenticated"])
        user.is_authenticated = True
        # No ``profile`` attribute on this user.
        self.assertEqual(views._get_clearance_level(self._request_with(user)), "PUBLIC")


class ReportCacheKeyTests(TestCase):
    def test_key_includes_microsecond_precision_timestamp(self):
        ts = datetime(2026, 5, 16, 12, 34, 56, 123456)
        key = views._report_cache_key("proc-1", "PUBLIC", ts)
        self.assertEqual(key, "report:v1:proc-1:PUBLIC:20260516123456123456")

    def test_key_uses_empty_when_timestamp_is_none(self):
        self.assertEqual(
            views._report_cache_key("proc-1", "PUBLIC", None),
            "report:v1:proc-1:PUBLIC:empty",
        )

    def test_different_clearance_levels_produce_different_keys(self):
        ts = datetime(2026, 1, 1)
        self.assertNotEqual(
            views._report_cache_key("p", "PUBLIC", ts),
            views._report_cache_key("p", "RESTRICTED", ts),
        )

    def test_different_process_ids_produce_different_keys(self):
        ts = datetime(2026, 1, 1)
        self.assertNotEqual(
            views._report_cache_key("a", "PUBLIC", ts),
            views._report_cache_key("b", "PUBLIC", ts),
        )


class GetCachedReportBundleTests(TestCase):
    """Cache-or-generate-and-cache logic for project reports."""

    @patch("core.views.cache")
    @patch("core.views.generate_project_report")
    @patch("core.views.Document")
    def test_returns_cached_dict_without_regenerating(
        self, mock_document, mock_generate, mock_cache
    ):
        # Mock the queryset chain that finds the latest doc timestamp.
        ts = datetime(2026, 1, 1)
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.values_list.return_value = chain
        chain.first.return_value = ts
        mock_document.objects.filter.return_value = chain

        mock_cache.get.return_value = {"md": "cached body", "doc_ids": ["d1"]}

        result = views._get_cached_report_bundle("proc-1", "PUBLIC")

        self.assertEqual(result, {"md": "cached body", "doc_ids": ["d1"]})
        mock_generate.assert_not_called()
        mock_cache.set.assert_not_called()

    @patch("core.views.cache")
    @patch("core.views.generate_project_report")
    @patch("core.views.Document")
    def test_generates_and_caches_when_missing(
        self, mock_document, mock_generate, mock_cache
    ):
        ts = datetime(2026, 1, 1)
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.values_list.return_value = chain
        chain.first.return_value = ts
        mock_document.objects.filter.return_value = chain

        mock_cache.get.return_value = None
        mock_generate.return_value = ("# Report", ["doc-a", "doc-b"])

        result = views._get_cached_report_bundle("proc-1", "PUBLIC")

        self.assertEqual(result, {"md": "# Report", "doc_ids": ["doc-a", "doc-b"]})
        mock_generate.assert_called_once_with("proc-1", clearance_level="PUBLIC")
        # 24-hour TTL is the documented contract — pin it.
        mock_cache.set.assert_called_once()
        _, args, kwargs = mock_cache.set.mock_calls[0]
        self.assertEqual(args[1], {"md": "# Report", "doc_ids": ["doc-a", "doc-b"]})
        self.assertEqual(args[2], 86400)

    @patch("core.views.cache")
    @patch("core.views.generate_project_report")
    @patch("core.views.Document")
    def test_regenerates_when_cached_value_is_legacy_non_dict(
        self, mock_document, mock_generate, mock_cache
    ):
        # Legacy: cache previously stored a bare markdown string or a tuple.
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.values_list.return_value = chain
        chain.first.return_value = datetime(2026, 1, 1)
        mock_document.objects.filter.return_value = chain

        for legacy in ("# old string", ("tuple", ["x"]), 42):
            mock_cache.reset_mock()
            mock_generate.reset_mock()
            mock_generate.return_value = ("fresh", ["d1"])
            mock_cache.get.return_value = legacy

            result = views._get_cached_report_bundle("p", "PUBLIC")

            self.assertEqual(result, {"md": "fresh", "doc_ids": ["d1"]})
            mock_generate.assert_called_once()
            mock_cache.set.assert_called_once()

    @patch("core.views.cache")
    @patch("core.views.generate_project_report")
    @patch("core.views.Document")
    def test_empty_timestamp_still_produces_valid_cache_key(
        self, mock_document, mock_generate, mock_cache
    ):
        # No documents yet -> latest_doc_ts is None -> key uses "empty".
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.values_list.return_value = chain
        chain.first.return_value = None
        mock_document.objects.filter.return_value = chain
        mock_cache.get.return_value = None
        mock_generate.return_value = ("body", [])

        views._get_cached_report_bundle("p", "PUBLIC")

        cache_key_used = mock_cache.get.call_args[0][0]
        self.assertEqual(cache_key_used, "report:v1:p:PUBLIC:empty")


class GetCachedReportMdTests(TestCase):
    @patch("core.views._get_cached_report_bundle")
    def test_returns_only_md_field(self, mock_bundle):
        mock_bundle.return_value = {"md": "the body", "doc_ids": ["a", "b"]}
        self.assertEqual(views._get_cached_report_md("p", "PUBLIC"), "the body")
        mock_bundle.assert_called_once_with("p", "PUBLIC")


# ---------------------------------------------------------------------------
# Shared test base
# ---------------------------------------------------------------------------


class _ViewTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="alice", password="pw", email="alice@example.com"
        )

        self.org = MagicMock(name="Org", id=7)
        self.profile = MagicMock(
            organisation=self.org, role="ADMIN", clearance_level="PUBLIC"
        )

        self._profile_patcher = patch.object(
            User, "profile", new_callable=lambda: property(lambda self: None)
        )

    def _authed_request(self, method="get", path="/", files=None, **kwargs):
        request = getattr(self.factory, method)(path, **kwargs)
        request.user = self.user
        type(request.user).profile = property(lambda s, p=self.profile: p)
        if files is not None:
            normalised = {
                k: (v if isinstance(v, list) else [v]) for k, v in files.items()
            }

            request._post = QueryDict()
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
            "annotate",
            "distinct",
            "values_list",
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
# upload_doc
# ---------------------------------------------------------------------------


class UploadDocGetTests(_ViewTestBase):
    @patch("core.views.render")
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_get_renders_upload_template_with_form_and_recent_docs(
        self, _f, mock_form_cls, mock_document, mock_render
    ):
        mock_form_cls.return_value = MagicMock(name="form-instance")
        mock_document.objects = self._chainable_qs(["d1", "d2"])
        mock_render.return_value = MagicMock()

        views.upload_doc(self._authed_request("get"))

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/upload.html")
        self.assertIn("form", args[2])
        self.assertIn("docs", args[2])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_form_constructed_with_users_organisation(
        self, _f, mock_form_cls, mock_document, _r
    ):
        mock_document.objects = self._chainable_qs([])

        views.upload_doc(self._authed_request("get"))

        # The form should be told the user's org so it can scope choices.
        _, kwargs = mock_form_cls.call_args
        self.assertEqual(kwargs.get("organisation"), self.org)


class UploadDocPostTests(_ViewTestBase):
    """POST flow: validation, dedup, save, audit, cache, redirect."""

    def _build_form_mock(self, valid=True, doc=None):
        form = MagicMock(name="form")
        form.is_valid.return_value = valid
        form.errors = {} if valid else {"file": ["required"]}
        form.save.return_value = doc or MagicMock()
        return form

    @patch("core.views.chunk_text", return_value=["c1", "c2"])
    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.generate_project_report", return_value=("md", ["d1"]))
    @patch("core.views.extract_text", return_value="hello world")
    @patch("core.views.sha256_file", return_value="abc123")
    @patch("core.views.redirect")
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_valid_post_saves_doc_logs_audit_invalidates_cache_redirects(
        self,
        _f,
        mock_form_cls,
        mock_document,
        mock_redirect,
        mock_sha,
        mock_extract,
        _gen,
        mock_log_audit,
        mock_cache,
        _chunk,
    ):

        doc = MagicMock(
            checksum_sha256="abc123",
            title="My Doc",
            extracted_text="hello world",
            process=MagicMock(),
            process_id="proc-1",
            created_at=datetime(2026, 1, 1),
        )
        doc.file = MagicMock()
        form = self._build_form_mock(valid=True, doc=doc)
        mock_form_cls.return_value = form

        dup_qs = MagicMock()
        dup_qs.exists.return_value = False
        mock_document.objects.filter.return_value = dup_qs

        # DocumentChunk import inside the function:
        with patch("core.models.DocumentChunk") as mock_chunk_model:
            mock_chunk_model.objects.bulk_create = MagicMock()
            mock_redirect.return_value = MagicMock(status_code=302)

            request = self._authed_request("post", files={"file": MagicMock()})
            views.upload_doc(request)

        # The doc was saved.
        doc.save.assert_called_once()

        # An audit entry was written.
        mock_log_audit.assert_called_once()

        # The doc list cache was invalidated.
        self.assertTrue(
            any("docs:" in str(c.args[0]) for c in mock_cache.delete.mock_calls),
            "Document list cache should be invalidated after successful upload.",
        )

        # And we redirected to the upload page.
        mock_redirect.assert_called_with("upload")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.extract_text", return_value="")
    @patch("core.views.sha256_file", return_value="dup-hash")
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_duplicate_checksum_renders_error_does_not_save(
        self,
        _f,
        mock_form_cls,
        mock_document,
        _sha,
        _extract,
        mock_render,
    ):
        doc = MagicMock(checksum_sha256="dup-hash", file=MagicMock())
        form = self._build_form_mock(valid=True, doc=doc)
        mock_form_cls.return_value = form

        dup_qs = MagicMock()
        dup_qs.exists.return_value = True
        recent_qs = self._chainable_qs(["a", "b"])
        mock_document.objects.filter.side_effect = [dup_qs, recent_qs, recent_qs]

        # instead of e.g.:
        # ```
        #   request = self._authed_request("post")
        #   request._files = MagicMock()
        #   views.upload_doc(request)
        # ```
        # which Django's handler processing does not like, we call the 
        # `_authed_request` method instead.
        request = self._authed_request("post", files={"file": MagicMock()})
        views.upload_doc(request)

        doc.save.assert_not_called()
        ctx = mock_render.call_args[0][2]
        self.assertIn("Duplicate", ctx["error"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_invalid_form_re_renders_with_error_message(
        self, _f, mock_form_cls, mock_document, mock_render
    ):
        form = self._build_form_mock(valid=False)
        mock_form_cls.return_value = form
        mock_document.objects.filter.return_value = self._chainable_qs([])

        request = self._authed_request("post", files={"file": MagicMock()})
        views.upload_doc(request)

        ctx = mock_render.call_args[0][2]
        self.assertIn("error", ctx)
        self.assertIn("correct the errors", ctx["error"])

    @patch("core.views.chunk_text", return_value=["c1"])
    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.generate_project_report")
    @patch("core.views.extract_text", return_value="text")
    @patch("core.views.sha256_file", return_value="hash")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.DocumentForm")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_report_warmup_failure_is_swallowed(
        self,
        _f,
        mock_form_cls,
        mock_document,
        _redir,
        _sha,
        _ext,
        mock_generate,
        _audit,
        _cache,
        _chunk,
    ):
        # The warm-cache report call raises — the upload must still succeed.
        mock_generate.side_effect = RuntimeError("Granite down")

        doc = MagicMock(
            checksum_sha256="hash",
            extracted_text="t",
            process=MagicMock(),
            process_id="proc-1",
            created_at=datetime(2026, 1, 1),
        )
        doc.file = MagicMock()
        form = self._build_form_mock(valid=True, doc=doc)
        mock_form_cls.return_value = form

        dup_qs = MagicMock()
        dup_qs.exists.return_value = False
        mock_document.objects.filter.return_value = dup_qs

        with patch("core.models.DocumentChunk"):
            request = self._authed_request("post", files={"file": MagicMock()})

            # No exception should escape.
            response = views.upload_doc(request)

        # Save still happened despite the report failure.
        doc.save.assert_called_once()
        self.assertIsNotNone(response)


# ---------------------------------------------------------------------------
# documents (library view)
# ---------------------------------------------------------------------------


class DocumentsViewTests(_ViewTestBase):
    """The library view's many filter branches deserve isolated coverage."""

    @patch("core.views.cache")
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.DocumentSearchForm")
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_unfiltered_first_page_served_from_cache_when_present(
        self,
        _f,
        mock_document,
        mock_form_cls,
        mock_paginate,
        mock_render,
        mock_cache,
    ):
        # No filters in GET; cache holds a serialised page.
        mock_form_cls.return_value = MagicMock(
            is_valid=MagicMock(return_value=False),
        )
        # The doc_type choices query — return an empty chainable.
        mock_document.objects.filter.return_value = self._chainable_qs([])

        mock_cache.get.return_value = {
            "docs": ["doc-1", "doc-2"],
            "num_pages": 1,
            "has_next": False,
            "has_previous": False,
            "next_page_number": None,
            "prev_page_number": None,
        }

        views.documents(self._authed_request("get"))

        # We took the cache branch — _paginate was NOT called.
        mock_paginate.assert_not_called()
        # And the rendered page is the proxy reconstructed from cache.
        ctx = mock_render.call_args[0][2]
        self.assertEqual(list(ctx["page"].object_list), ["doc-1", "doc-2"])
        self.assertEqual(ctx["filters_active"], False)

    @patch("core.views.cache")
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.DocumentSearchForm")
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_unfiltered_first_page_writes_cache_on_miss(
        self,
        _f,
        mock_document,
        mock_form_cls,
        mock_paginate,
        mock_render,
        mock_cache,
    ):
        mock_form_cls.return_value = MagicMock(
            is_valid=MagicMock(return_value=False),
        )
        mock_document.objects.filter.return_value = self._chainable_qs([])

        page = MagicMock()
        page.object_list = ["x"]
        page.paginator.num_pages = 1
        page.has_next.return_value = False
        page.has_previous.return_value = False
        mock_paginate.return_value = page

        mock_cache.get.return_value = None

        views.documents(self._authed_request("get"))

        # We populated the cache with the page-1 results.
        mock_cache.set.assert_called_once()
        args = mock_cache.set.call_args[0]
        self.assertEqual(args[1]["docs"], ["x"])
        self.assertEqual(args[2], views.DOCS_CACHE_TTL)

    @patch("core.views.cache")
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.DocumentSearchForm")
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_filtered_request_bypasses_cache(
        self,
        _f,
        mock_document,
        mock_form_cls,
        mock_paginate,
        mock_render,
        mock_cache,
    ):
        mock_form_cls.return_value = MagicMock(
            is_valid=MagicMock(return_value=False),
        )
        mock_document.objects.filter.return_value = self._chainable_qs([])
        mock_paginate.return_value = MagicMock(
            object_list=[], paginator=MagicMock(num_pages=1)
        )

        # Any of the filter params being set must skip the cache entirely.
        request = self._authed_request("get", path="/?q=hello")
        views.documents(request)

        mock_cache.get.assert_not_called()
        mock_cache.set.assert_not_called()

    @patch("core.views.cache")
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views._paginate")
    @patch("core.views.DocumentSearchForm")
    @patch("core.views.Document")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_page_two_bypasses_cache(
        self,
        _f,
        mock_document,
        mock_form_cls,
        mock_paginate,
        _r,
        mock_cache,
    ):
        mock_form_cls.return_value = MagicMock(
            is_valid=MagicMock(return_value=False),
        )
        mock_document.objects.filter.return_value = self._chainable_qs([])
        mock_paginate.return_value = MagicMock(
            object_list=[], paginator=MagicMock(num_pages=1)
        )

        views.documents(self._authed_request("get", path="/?page=2"))

        mock_cache.get.assert_not_called()
        mock_cache.set.assert_not_called()


# ---------------------------------------------------------------------------
# document_detail
# ---------------------------------------------------------------------------


class DocumentDetailTests(_ViewTestBase):
    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_superuser_sees_any_doc_regardless_of_org(self, mock_get, mock_render):
        self.user.is_superuser = True
        self.user.save()
        doc = MagicMock(
            organisation=MagicMock(name="other org"),
            tags=[],
            get_version_family=MagicMock(return_value=[]),
        )
        mock_get.return_value = doc

        response = views.document_detail(self._authed_request("get"), pk=1)

        self.assertIsNotNone(response)  # no PermissionDenied raised
        self.assertEqual(mock_render.call_args[0][1], "core/document_detail.html")

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked_with_permission_denied(self, mock_get):
        other_org = MagicMock(name="other org")
        doc = MagicMock(organisation=other_org)
        mock_get.return_value = doc

        with self.assertRaises(PermissionDenied):
            views.document_detail(self._authed_request("get"), pk=1)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_same_org_user_can_view(self, mock_get, mock_render):
        doc = MagicMock(
            organisation=self.org,
            tags=[1, 2],
            get_version_family=MagicMock(return_value=[]),
        )
        mock_get.return_value = doc

        views.document_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["doc"], doc)
        self.assertEqual(len(ctx["tag_labels"]), 2)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_latest_version_is_last_in_family(self, mock_get, mock_render):
        v1, v2, v3 = MagicMock(name="v1"), MagicMock(name="v2"), MagicMock(name="v3")
        doc = MagicMock(
            organisation=self.org,
            tags=[],
            get_version_family=MagicMock(return_value=[v1, v2, v3]),
        )
        mock_get.return_value = doc

        views.document_detail(self._authed_request("get"), pk=1)

        ctx = mock_render.call_args[0][2]
        self.assertIs(ctx["latest_version"], v3)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_can_upload_version_flag_only_set_for_privileged_roles(
        self, mock_get, mock_render
    ):
        doc = MagicMock(
            organisation=self.org,
            tags=[],
            get_version_family=MagicMock(return_value=[]),
        )
        mock_get.return_value = doc

        # Geologist role should NOT see the upload button.
        self.profile.role = views.UserProfile.RoleChoices.GEOLOGIST_EXPL
        views.document_detail(self._authed_request("get"), pk=1)
        ctx = mock_render.call_args[0][2]
        self.assertFalse(ctx["can_upload_version"])

        # Field lead SHOULD.
        self.profile.role = views.UserProfile.RoleChoices.FIELD_LEAD
        views.document_detail(self._authed_request("get"), pk=1)
        ctx = mock_render.call_args[0][2]
        self.assertTrue(ctx["can_upload_version"])


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------


class DeleteDocumentTests(_ViewTestBase):
    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock(status_code=302))
    @patch("core.views.get_object_or_404")
    def test_post_deletes_and_redirects(
        self, mock_get, mock_redirect, mock_audit, mock_cache
    ):
        doc = MagicMock(organisation=self.org, title="Bye")
        mock_get.return_value = doc

        request = self._authed_request("post")
        views.delete_document(request, pk=1)

        doc.delete.assert_called_once()
        mock_audit.assert_called_once()
        mock_cache.delete.assert_called_once()
        mock_redirect.assert_called_with("upload")

    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_htmx_request_gets_json_success(self, mock_get, _audit, _cache):
        doc = MagicMock(organisation=self.org, title="Bye")
        mock_get.return_value = doc

        request = self._authed_request("post")
        request.META["HTTP_HX_REQUEST"] = "true"
        # RequestFactory rolls headers into META, but the view reads via
        # request.headers — patch that directly.
        request.headers = {"HX-Request": "true"}

        response = views.delete_document(request, pk=1)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)

    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_htmx_request_gets_json_error_on_exception(self, mock_get, _audit, _cache):
        doc = MagicMock(organisation=self.org, title="Bye")
        doc.delete.side_effect = RuntimeError("storage down")
        mock_get.return_value = doc

        request = self._authed_request("post")
        request.headers = {"HX-Request": "true"}

        response = views.delete_document(request, pk=1)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 500)

    @patch("core.views.get_object_or_404")
    def test_cross_org_user_blocked(self, mock_get):
        doc = MagicMock(organisation=MagicMock(name="other org"), title="x")
        mock_get.return_value = doc

        with self.assertRaises(PermissionDenied):
            views.delete_document(self._authed_request("post"), pk=1)


# ---------------------------------------------------------------------------
# download_document
# ---------------------------------------------------------------------------


class DownloadDocumentTests(_ViewTestBase):
    @patch("core.views.redirect", return_value=MagicMock(status_code=302))
    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_allowed_user_redirected_to_file_url(
        self, mock_get, mock_audit, mock_redirect
    ):
        self.profile.can_access_document.return_value = True
        doc = MagicMock(title="Report.pdf")
        doc.file.url = "https://files.example.com/report.pdf"
        mock_get.return_value = doc

        request = self._authed_request("get")
        views.download_document(request, pk=1)

        mock_audit.assert_called_once()
        mock_redirect.assert_called_with("https://files.example.com/report.pdf")

    @patch("core.views.get_object_or_404")
    def test_user_without_access_blocked(self, mock_get):
        self.profile.can_access_document.return_value = False
        doc = MagicMock()
        doc.file.url = "https://x/y"
        mock_get.return_value = doc

        with self.assertRaises(PermissionDenied):
            views.download_document(self._authed_request("get"), pk=1)

    @patch("core.views.redirect", return_value=MagicMock(status_code=302))
    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_superuser_bypasses_access_check(self, mock_get, _audit, mock_redirect):
        self.user.is_superuser = True
        self.user.save()
        # Profile would say "no", but superuser skips the check entirely.
        self.profile.can_access_document.return_value = False
        doc = MagicMock()
        doc.file.url = "https://x/y"
        mock_get.return_value = doc

        views.download_document(self._authed_request("get"), pk=1)
        mock_redirect.assert_called_with("https://x/y")

    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.log_audit")
    @patch("core.views.get_object_or_404")
    def test_audit_log_truncates_long_user_agent(self, mock_get, mock_audit, _redir):
        self.profile.can_access_document.return_value = True
        doc = MagicMock()
        doc.file.url = "https://x"
        doc.title = "t"
        mock_get.return_value = doc

        request = self._authed_request("get")
        request.META["HTTP_USER_AGENT"] = "A" * 1000
        views.download_document(request, pk=1)

        # The audit log truncates UA to 500 chars.
        _, kwargs = mock_audit.call_args
        self.assertLessEqual(len(kwargs.get("user_agent", "")), 500)


# ---------------------------------------------------------------------------
# replace_document
# ---------------------------------------------------------------------------


class ReplaceDocumentTests(_ViewTestBase):
    @patch("core.views.messages")
    @patch("core.views.cache")
    @patch("core.views.log_audit")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.get_object_or_404")
    def test_successful_replace_creates_version_and_invalidates_cache(
        self,
        mock_get,
        mock_document,
        mock_redirect,
        mock_audit,
        mock_cache,
        mock_messages,
    ):
        parent = MagicMock(title="Parent")
        mock_get.return_value = parent
        new_doc = MagicMock(pk=99, version_number=2)
        mock_document.create_version.return_value = new_doc

        upload_file = MagicMock(name="upload")

        request = self._authed_request("post", files={"file": upload_file})
        views.replace_document(request, pk=1)

        mock_document.create_version.assert_called_once_with(
            parent, upload_file, request.user
        )
        mock_audit.assert_called_once()
        mock_cache.delete.assert_called_once()
        mock_messages.success.assert_called_once()
        mock_redirect.assert_called_with("document_detail", pk=99)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.get_object_or_404")
    def test_missing_file_redirects_with_error_message(
        self, mock_get, mock_redirect, mock_messages
    ):
        parent = MagicMock()
        mock_get.return_value = parent

        request = self._authed_request("post", files={})
        views.replace_document(request, pk=1)

        mock_messages.error.assert_called_once()
        mock_redirect.assert_called_with("document_detail", pk=1)

    @patch("core.views.messages")
    @patch("core.views.redirect", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.get_object_or_404")
    def test_create_version_value_error_surfaces_to_user(
        self, mock_get, mock_document, mock_redirect, mock_messages
    ):
        parent = MagicMock()
        mock_get.return_value = parent
        mock_document.create_version.side_effect = ValueError("checksum dup")

        request = self._authed_request("post", files={"file": MagicMock()})
        views.replace_document(request, pk=1)

        # The user-facing message carries the exception text.
        args, _ = mock_messages.error.call_args
        self.assertIn("checksum dup", args[1])
        # And we go back to the detail page (not the new doc, since there isn't one).
        mock_redirect.assert_called_with("document_detail", pk=1)

    def test_get_request_rejected(self):
        # @require_POST should 405 a GET.
        request = self._authed_request("get")
        response = views.replace_document(request, pk=1)
        self.assertEqual(response.status_code, 405)
