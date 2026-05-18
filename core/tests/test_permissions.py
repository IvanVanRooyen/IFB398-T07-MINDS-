from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from core.models import Document, Organisation, UserProfile
from core.permissions import (
    can_approve_workflow,
    clearance_required,
    get_user_ip,
    log_view_access,
    organisation_access_required,
    role_required,
)


class PermissionsTestBase(TestCase):
    """Shared fixtures for permission tests"""

    @classmethod
    def _make_user_with_profile(cls, username, **profile_fields):
        """
        Profile creation wrapper function to update a user's User and UserProfile before refreshing the
        database entry.
        """
        user = User.objects.create_user(username, password="x")
        UserProfile.objects.filter(user=user).update(**profile_fields)

        # update fields
        user.refresh_from_db()
        return user

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="Test Mining Co")

        cls.admin_user = cls._make_user_with_profile(
            "admin",
            organisation=cls.org,
            role=UserProfile.RoleChoices.ADMIN,
            clearance_level=UserProfile.ClearanceLevel.JORC_APPROVED,
            can_approve_jorc=True,
            can_approve_valmin=True,
        )

        # cls.field_lead = User.objects.create_user("lead", password="x")
        cls.field_lead = cls._make_user_with_profile(
            "lead",
            organisation=cls.org,
            role=UserProfile.RoleChoices.FIELD_LEAD,
            clearance_level=UserProfile.ClearanceLevel.CONFIDENTIAL,
        )

        # cls.basic_user = User.objects.create_user("basic", password="x")
        cls.basic_user = cls._make_user_with_profile(
            "basic",
            organisation=cls.org,
            role=UserProfile.RoleChoices.VIEWER,
            clearance_level=UserProfile.ClearanceLevel.PUBLIC,
        )

        # clean out any profiles that get automatically created by signals
        cls.profileless_user = User.objects.create_user("noprofile", password="x")
        UserProfile.objects.filter(user=cls.profileless_user).delete()

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self, user, path="/test/"):
        request = self.factory.get(path)
        request.user = user
        return request


class RoleRequiredTests(PermissionsTestBase):
    def setUp(self):
        super().setUp()

        @role_required(UserProfile.RoleChoices.ADMIN, UserProfile.RoleChoices.FIELD_LEAD)
        def dummy_view(request):
            return "ok"

        self.view = dummy_view

    def test_allowed_role_passes(self):
        request = self._make_request(self.admin_user)
        self.assertEqual(self.view(request), "ok")

    def test_disallowed_role_denied(self):
        request = self._make_request(self.basic_user)
        with self.assertRaises(PermissionDenied):
            self.view(request)

    def test_anonymous_user_denied(self):
        request = self._make_request(AnonymousUser())
        with self.assertRaises(PermissionDenied):
            self.view(request)

    def test_user_without_profile_denied(self):
        request = self._make_request(self.profileless_user)
        with self.assertRaises(PermissionDenied):
            self.view(request)


class OrganisationAccessTests(PermissionsTestBase):
    def setUp(self):
        super().setUp()

        @organisation_access_required
        def dummy_view(request):
            return request.user_organisation

        self.view = dummy_view

    def test_attaches_organisation_to_request(self):
        request = self._make_request(self.field_lead)
        result = self.view(request)
        self.assertEqual(result, self.org)

    def test_anonymous_denied(self):
        with self.assertRaises(PermissionDenied):
            self.view(self._make_request(AnonymousUser()))

    def test_no_profile_denied(self):
        with self.assertRaises(PermissionDenied):
            self.view(self._make_request(self.profileless_user))


class ClearanceRequiredTests(PermissionsTestBase):
    def _build_view(self, level):
        @clearance_required(level)
        def view(request):
            return "ok"

        return view

    def test_higher_clearance_passes(self):
        view = self._build_view(UserProfile.ClearanceLevel.INTERNAL)

        # admin has JORC_APPROVED (above INTERNAL)
        self.assertEqual(view(self._make_request(self.admin_user)), "ok")

    def test_equal_clearance_passes(self):
        view = self._build_view(UserProfile.ClearanceLevel.CONFIDENTIAL)

        # field_lead has CONFIDENTIAL
        self.assertEqual(view(self._make_request(self.field_lead)), "ok")

    def test_insufficient_clearance_denied(self):
        view = self._build_view(UserProfile.ClearanceLevel.JORC_APPROVED)
        with self.assertRaises(PermissionDenied):
            view(self._make_request(self.basic_user))


class LogViewAccessTests(PermissionsTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.document = Document.objects.create(title="Test doc", organisation=cls.org)

    @patch("core.permissions.log_audit")
    def test_logs_audit_entry_on_view(self, mock_log_audit):
        @log_view_access(Document)
        def view(request, pk):
            return "ok"

        request = self.factory.get(
            "/docs/1/",
            HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2",
            HTTP_USER_AGENT="pytest-agent",
        )
        request.user = self.field_lead

        view(request, pk=self.document.pk)

        mock_log_audit.assert_called_once()
        kwargs = mock_log_audit.call_args.kwargs
        self.assertEqual(kwargs["user"], self.field_lead)
        self.assertEqual(kwargs["obj"], self.document)
        self.assertEqual(kwargs["ip_address"], "10.0.0.1")
        self.assertEqual(kwargs["user_agent"], "pytest-agent")

    @patch("core.permissions.log_audit")
    def test_creates_document_view_for_document_model(self, _mock_log_audit):
        from core.models import DocumentView

        @log_view_access(Document)
        def view(request, pk):
            return "ok"

        request = self._make_request(self.field_lead)
        view(request, pk=self.document.pk)

        self.assertTrue(
            DocumentView.objects.filter(user=self.field_lead, document=self.document).exists()
        )

    @patch("core.permissions.log_audit")
    def test_silently_skips_logging_when_object_missing(self, mock_log_audit):
        @log_view_access(Document)
        def view(request, pk):
            return "ok"

        request = self._make_request(self.field_lead)
        # Should not raise even though pk=99999 doesn't exist
        result = view(request, pk=99999)

        self.assertEqual(result, "ok")
        mock_log_audit.assert_not_called()

    @patch("core.permissions.log_audit")
    def test_skips_logging_for_anonymous_user(self, mock_log_audit):
        @log_view_access(Document)
        def view(request, pk):
            return "ok"

        request = self.factory.get("/docs/1/")
        request.user = AnonymousUser()
        view(request, pk=self.document.pk)

        mock_log_audit.assert_not_called()


class CanApproveWorkflowTests(PermissionsTestBase):
    def test_jorc_approver_returns_true(self):
        from core.models import ApprovalWorkflow

        self.assertTrue(can_approve_workflow(self.admin_user, ApprovalWorkflow.WorkflowType.JORC))

    def test_non_jorc_approver_returns_false(self):
        from core.models import ApprovalWorkflow

        self.assertFalse(can_approve_workflow(self.field_lead, ApprovalWorkflow.WorkflowType.JORC))

    def test_general_workflow_uses_role(self):
        from core.models import ApprovalWorkflow

        # Field lead has approving role, basic user doesn't
        self.assertTrue(
            can_approve_workflow(self.field_lead, ApprovalWorkflow.WorkflowType.GENERAL)
        )
        self.assertFalse(
            can_approve_workflow(self.basic_user, ApprovalWorkflow.WorkflowType.GENERAL)
        )

    def test_user_without_profile_returns_false(self):
        from core.models import ApprovalWorkflow

        self.assertFalse(
            can_approve_workflow(self.profileless_user, ApprovalWorkflow.WorkflowType.JORC)
        )


class GetUserIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_x_forwarded_for_when_present(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        self.assertEqual(get_user_ip(request), "1.2.3.4")

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get("/", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(get_user_ip(request), "9.9.9.9")
