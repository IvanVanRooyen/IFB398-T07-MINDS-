"""
Coverage:
    Helpers:        _get_model, _count_model, _paginate, _org_qs_filter
    Views:          home, dashboard, stats_partial
    Cache keys:     _docs_cache_key
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.test import RequestFactory, TestCase

from core import views

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class GetModelTests(TestCase):
    """``_get_model`` should swallow LookupError and return None."""

    def test_returns_model_when_app_and_name_resolve(self):
        # auth.User is guaranteed to exist in any Django project.
        model = views._get_model("auth", "User")
        self.assertIsNotNone(model)
        self.assertEqual(model.__name__, "User")

    def test_returns_none_for_unknown_app(self):
        self.assertIsNone(views._get_model("nope_app", "Whatever"))

    def test_returns_none_for_unknown_model_in_known_app(self):
        self.assertIsNone(views._get_model("auth", "DefinitelyNotAModel"))

    @patch("core.views.apps.get_model")
    def test_lookup_error_is_swallowed(self, mock_get_model):
        mock_get_model.side_effect = LookupError("boom")
        self.assertIsNone(views._get_model("anything", "anything"))

    @patch("core.views.apps.get_model")
    def test_other_exceptions_propagate(self, mock_get_model):
        # The function only catches LookupError — anything else should bubble.
        mock_get_model.side_effect = RuntimeError("explode")
        with self.assertRaises(RuntimeError):
            views._get_model("a", "b")


class CountModelTests(TestCase):
    """``_count_model`` returns 0 if the model is missing, otherwise .count()."""

    @patch("core.views._get_model")
    def test_returns_zero_when_model_is_none(self, mock_get_model):
        mock_get_model.return_value = None
        self.assertEqual(views._count_model("core", "Ghost"), 0)

    @patch("core.views._get_model")
    def test_returns_objects_count_when_model_present(self, mock_get_model):
        mdl = MagicMock()
        mdl.objects.count.return_value = 7
        mock_get_model.return_value = mdl

        self.assertEqual(views._count_model("core", "Real"), 7)
        mdl.objects.count.assert_called_once_with()

    @patch("core.views._get_model")
    def test_where_clause_argument_is_accepted_but_unused(self, mock_get_model):
        # The current implementation ignores ``where_clause`` — pin that
        # behaviour so accidental changes get flagged.
        mdl = MagicMock()
        mdl.objects.count.return_value = 3
        mdl.objects.filter = MagicMock()
        mock_get_model.return_value = mdl

        result = views._count_model("core", "Real", where_clause="x=1")

        self.assertEqual(result, 3)
        mdl.objects.filter.assert_not_called()


class PaginateTests(TestCase):
    """``_paginate`` is a thin wrapper around Paginator.get_page()."""

    def setUp(self):
        self.factory = RequestFactory()
        # Paginator happily accepts any sliceable + len()-able sequence.
        self.qs = list(range(55))

    def test_default_per_page_is_20(self):
        request = self.factory.get("/")
        page = views._paginate(self.qs, request)
        self.assertEqual(len(page.object_list), 20)
        self.assertEqual(page.number, 1)

    def test_respects_custom_per_page(self):
        request = self.factory.get("/", {"page": "1"})
        page = views._paginate(self.qs, request, per_page=10)
        self.assertEqual(len(page.object_list), 10)
        self.assertEqual(page.paginator.num_pages, 6)  # 55 / 10 rounded up

    def test_specific_page_number(self):
        request = self.factory.get("/", {"page": "2"})
        page = views._paginate(self.qs, request, per_page=20)
        self.assertEqual(page.number, 2)
        self.assertEqual(page.object_list, list(range(20, 40)))

    def test_missing_page_param_defaults_to_first(self):
        request = self.factory.get("/")
        page = views._paginate(self.qs, request)
        self.assertEqual(page.number, 1)

    def test_non_integer_page_falls_back_to_first(self):
        # Paginator.get_page() coerces invalid input to page 1.
        request = self.factory.get("/", {"page": "not-a-number"})
        page = views._paginate(self.qs, request)
        self.assertEqual(page.number, 1)

    def test_out_of_range_page_falls_back_to_last(self):
        # get_page() returns the last page when the requested one is too high.
        request = self.factory.get("/", {"page": "9999"})
        page = views._paginate(self.qs, request, per_page=20)
        self.assertEqual(page.number, page.paginator.num_pages)


class OrgQsFilterTests(TestCase):
    """``_org_qs_filter`` returns a Q() per role/auth state."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request_with(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_superuser_returns_unrestricted_q(self):
        user = MagicMock()
        user.is_superuser = True

        result = views._org_qs_filter(self._request_with(user))
        self.assertEqual(result, Q())

    def test_anonymous_user_returns_empty_set_q(self):
        result = views._org_qs_filter(self._request_with(AnonymousUser()))
        self.assertEqual(result, Q(pk__in=[]))

    def test_authenticated_user_with_org_scopes_to_org(self):
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        org = MagicMock(name="Org")
        user.profile.organisation = org

        result = views._org_qs_filter(self._request_with(user))
        self.assertEqual(result, Q(organisation=org))

    def test_authenticated_user_with_no_org_sees_nothing(self):
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        user.profile.organisation = None

        result = views._org_qs_filter(self._request_with(user))
        self.assertEqual(result, Q(pk__in=[]))

    def test_authenticated_user_without_profile_sees_nothing(self):
        # ``spec`` ensures hasattr(user, "profile") returns False.
        user = MagicMock(spec=["is_superuser", "is_authenticated"])
        user.is_superuser = False
        user.is_authenticated = True

        result = views._org_qs_filter(self._request_with(user))
        self.assertEqual(result, Q(pk__in=[]))


# ---------------------------------------------------------------------------
# Views — home, dashboard, stats_partial
# ---------------------------------------------------------------------------


class _ViewTestBase(TestCase):
    """Shared fixtures: a logged-in user, request factory, query-set mocks."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="alice", password="pw", email="alice@example.com"
        )

    def _authed_get(self, path="/"):
        request = self.factory.get(path)
        request.user = self.user
        return request

    @staticmethod
    def _chainable_qs(result):
        """
        Build a MagicMock that responds to ``.filter(...).order_by(...)[:N]``
        and ``.filter(...).count()`` so view code can chain freely.
        """
        qs = MagicMock(name="QuerySet")
        qs.filter.return_value = qs
        qs.order_by.return_value = qs
        qs.count.return_value = len(result) if hasattr(result, "__len__") else 0
        qs.__getitem__.side_effect = lambda key: result[key]
        return qs


class HomeViewTests(_ViewTestBase):
    @patch("core.views.render")
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter")
    def test_renders_home_template_with_projects_and_docs(
        self, mock_filter, mock_process, mock_document, mock_render
    ):
        mock_filter.return_value = Q()
        mock_process.objects = self._chainable_qs(["p1", "p2"])
        mock_document.objects = self._chainable_qs(["d1", "d2"])
        mock_render.return_value = MagicMock(status_code=200)

        views.home(self._authed_get())

        mock_render.assert_called_once()
        args, _ = mock_render.call_args
        _, template, context = args
        self.assertEqual(template, "core/home.html")
        self.assertEqual(list(context["projects"]), ["p1", "p2"])
        self.assertEqual(list(context["docs"]), ["d1", "d2"])

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter")
    def test_applies_org_filter_to_both_querysets(
        self, mock_filter, mock_process, mock_document, _mock_render
    ):
        org_q = Q(organisation=42)
        mock_filter.return_value = org_q
        mock_process.objects = self._chainable_qs([])
        mock_document.objects = self._chainable_qs([])

        views.home(self._authed_get())

        # Process filtered with just the org filter.
        mock_process.objects.filter.assert_called_with(org_q)
        # Document filtered with org filter AND is_latest=True.
        mock_document.objects.filter.assert_called_with(org_q, is_latest=True)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_limits_results_to_ten(self, _mock_filter, mock_process, mock_document, _mock_render):
        proc_qs = self._chainable_qs(list(range(50)))
        doc_qs = self._chainable_qs(list(range(50)))
        mock_process.objects = proc_qs
        mock_document.objects = doc_qs

        views.home(self._authed_get())

        # The slice [:10] is invoked on the order_by() result.
        proc_qs.__getitem__.assert_called_with(slice(None, 10, None))
        doc_qs.__getitem__.assert_called_with(slice(None, 10, None))

    def test_unauthenticated_redirected_by_login_required(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        response = views.home(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url.lower())

    def test_post_request_rejected_by_require_GET(self):
        request = self.factory.post("/")
        request.user = self.user
        response = views.home(request)
        self.assertEqual(response.status_code, 405)


class DashboardViewTests(_ViewTestBase):
    @patch("core.views.render")
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._get_model")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_metrics_present_when_all_optional_models_exist(
        self, _mock_filter, mock_get_model, mock_process, mock_document, mock_render
    ):
        # Distinct mock per optional model, each with its own count.
        prospect = MagicMock()
        prospect.objects = self._chainable_qs(list(range(3)))
        drill = MagicMock()
        drill.objects = self._chainable_qs(list(range(4)))
        ten = MagicMock()
        ten.objects = self._chainable_qs(list(range(5)))
        mock_get_model.side_effect = lambda app, name: {
            "Prospect": prospect,
            "Drillhole": drill,
            "Tenement": ten,
        }[name]

        mock_process.objects = self._chainable_qs(list(range(11)))
        mock_document.objects = self._chainable_qs(list(range(2)))
        mock_render.return_value = MagicMock()

        views.dashboard(self._authed_get())

        _, kwargs = mock_render.call_args, mock_render.call_args.kwargs
        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["metrics"]["project_count"], 11)
        self.assertEqual(ctx["metrics"]["document_count"], 2)
        self.assertEqual(ctx["metrics"]["prospect_count"], 3)
        self.assertEqual(ctx["metrics"]["drillhole_count"], 4)
        self.assertEqual(ctx["metrics"]["tenement_count"], 5)
        self.assertEqual(mock_render.call_args[0][1], "core/dashboard.html")

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_optional_models_default_to_zero_when_missing(
        self, _f, _g, mock_process, mock_document, mock_render
    ):
        mock_process.objects = self._chainable_qs([])
        mock_document.objects = self._chainable_qs([])

        views.dashboard(self._authed_get())

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["metrics"]["prospect_count"], 0)
        self.assertEqual(ctx["metrics"]["drillhole_count"], 0)
        self.assertEqual(ctx["metrics"]["tenement_count"], 0)

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_recent_docs_filtered_and_limited_to_eight(
        self, _f, _g, _p, mock_document, _mock_render
    ):
        doc_qs = self._chainable_qs(list(range(20)))
        mock_document.objects = doc_qs

        views.dashboard(self._authed_get())

        # is_latest=True is enforced for the recent_docs list.
        called_kwargs = [c.kwargs for c in mock_document.objects.filter.call_args_list]
        self.assertTrue(any(kw.get("is_latest") is True for kw in called_kwargs))
        # The slice [:8] is invoked.
        doc_qs.__getitem__.assert_any_call(slice(None, 8, None))

    def test_unauthenticated_redirected(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        self.assertEqual(views.dashboard(request).status_code, 302)

    def test_post_rejected(self):
        request = self.factory.post("/")
        request.user = self.user
        self.assertEqual(views.dashboard(request).status_code, 405)


class StatsPartialViewTests(_ViewTestBase):
    @patch("core.views.render")
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._get_model")
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_renders_partial_with_full_metric_set(
        self, _f, mock_get_model, mock_process, mock_document, mock_render
    ):
        prospect = MagicMock()
        prospect.objects = self._chainable_qs(list(range(1)))
        drill = MagicMock()
        drill.objects = self._chainable_qs(list(range(2)))
        ten = MagicMock()
        ten.objects = self._chainable_qs(list(range(3)))
        mock_get_model.side_effect = lambda app, name: {
            "Prospect": prospect,
            "Drillhole": drill,
            "Tenement": ten,
        }[name]
        mock_process.objects = self._chainable_qs(list(range(9)))
        mock_document.objects = self._chainable_qs(list(range(7)))
        mock_render.return_value = MagicMock()

        views.stats_partial(self._authed_get())

        args = mock_render.call_args[0]
        self.assertEqual(args[1], "core/partials/stats.html")
        ctx = args[2]
        self.assertEqual(
            ctx,
            {
                "project_count": 9,
                "document_count": 7,
                "prospect_count": 1,
                "drillhole_count": 2,
                "tenement_count": 3,
            },
        )

    @patch("core.views.render", return_value=MagicMock())
    @patch("core.views.Document")
    @patch("core.views.Process")
    @patch("core.views._get_model", return_value=None)
    @patch("core.views._org_qs_filter", return_value=Q())
    def test_missing_optional_models_yield_zero_counts(
        self, _f, _g, mock_process, mock_document, mock_render
    ):
        mock_process.objects = self._chainable_qs([])
        mock_document.objects = self._chainable_qs([])

        views.stats_partial(self._authed_get())

        ctx = mock_render.call_args[0][2]
        for key in ("prospect_count", "drillhole_count", "tenement_count"):
            self.assertEqual(ctx[key], 0, msg=key)

    def test_unauthenticated_redirected(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        self.assertEqual(views.stats_partial(request).status_code, 302)

    def test_post_rejected(self):
        request = self.factory.post("/")
        request.user = self.user
        self.assertEqual(views.stats_partial(request).status_code, 405)


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------


class DocsCacheKeyTests(TestCase):
    """``_docs_cache_key`` must scope cache keys per-org, with special cases."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request_with(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_superuser_uses_global_all_key(self):
        user = MagicMock()
        user.is_superuser = True
        self.assertEqual(
            views._docs_cache_key(self._request_with(user)),
            "docs:unfiltered:page1:v1:all",
        )

    def test_user_with_org_keyed_by_org_id(self):
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        user.profile.organisation.id = 1234

        self.assertEqual(
            views._docs_cache_key(self._request_with(user)),
            "docs:unfiltered:page1:v1:1234",
        )

    def test_user_with_uuid_org_id_stringifies_correctly(self):
        # Defends against orgs that use UUID PKs.
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        user.profile.organisation.id = "abc-123-uuid"

        self.assertEqual(
            views._docs_cache_key(self._request_with(user)),
            "docs:unfiltered:page1:v1:abc-123-uuid",
        )

    def test_authenticated_user_without_org_uses_noorg(self):
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        user.profile.organisation = None

        self.assertEqual(
            views._docs_cache_key(self._request_with(user)),
            "docs:unfiltered:page1:v1:noorg",
        )

    def test_authenticated_user_without_profile_uses_noorg(self):
        user = MagicMock(spec=["is_superuser", "is_authenticated"])
        user.is_superuser = False
        user.is_authenticated = True

        self.assertEqual(
            views._docs_cache_key(self._request_with(user)),
            "docs:unfiltered:page1:v1:noorg",
        )

    def test_anonymous_user_uses_noorg(self):
        self.assertEqual(
            views._docs_cache_key(self._request_with(AnonymousUser())),
            "docs:unfiltered:page1:v1:noorg",
        )

    def test_two_different_orgs_produce_different_keys(self):
        u1 = MagicMock()
        u1.is_superuser = False
        u1.is_authenticated = True
        u1.profile.organisation.id = 1

        u2 = MagicMock()
        u2.is_superuser = False
        u2.is_authenticated = True
        u2.profile.organisation.id = 2

        self.assertNotEqual(
            views._docs_cache_key(self._request_with(u1)),
            views._docs_cache_key(self._request_with(u2)),
        )


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class CacheConstantsTests(TestCase):
    """Pin the cache-key constants so accidental edits trip a test."""

    def test_docs_cache_key_constant(self):
        self.assertEqual(views.DOCS_CACHE_KEY, "docs:unfiltered:page1:v1")

    def test_docs_cache_ttl_is_two_minutes(self):
        self.assertEqual(views.DOCS_CACHE_TTL, 120)
