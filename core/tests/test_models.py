from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    ApprovalWorkflow,
    Document,
    Drillhole,
    Organisation,
    Process,
    UserProfile,
    AuditLog,
    log_audit
)


class ChoiceValidationTests(TestCase):
    def test_valid_mode_saves_successfully(self):
        org = Organisation(name="Test Org", mode="EXPLORATION")

        org.save()
        self.assertEqual(Organisation.objects.count(), 1)

    def test_invalid_mode_raises_validation_error(self):
        org = Organisation(name="Invalid Org", mode="INVALID_MODE")
        with self.assertRaises(ValidationError) as ctx:
            org.save()

        self.assertIn("mode", ctx.exception.message_dict)

    def test_process_invalid_mode_rejected(self):
        org = Organisation.objects.create(name="Test Org", mode="MINING")
        proc = Process(name="Invalid Process", organisation=org, mode="INVALID_MODE")

        with self.assertRaises(ValidationError):
            proc.save()


class OrganisationModelTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", mode="MINING")

    def test_str_with_name(self):
        self.assertEqual(str(self.org), "Test Org (MINING)")

    def test_str_without_name(self):
        with self.assertRaises(ValidationError):
            Organisation.objects.create(name=None, mode="EXPLORATION")

    def test_default_mode_is_exploration(self):
        org = Organisation.objects.create(name="Defaults")
        self.assertEqual(org.mode, "EXPLORATION")

    def test_timestamps_auto_populated(self):
        self.assertIsNotNone(self.org.created_at)
        self.assertIsNotNone(self.org.updated_at)


class ProcessModelTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", mode="EXPLORATION")
        self.process = Process.objects.create(
            name="Gold Search",
            organisation=self.org,
            mode="PROJECT",
            commodity="Gold",
        )

    def test_process_linked_to_organisation(self):
        self.assertEqual(self.process.organisation, self.org)

    def test_cascade_delete_removes_processes(self):
        self.org.delete()
        self.assertEqual(Process.objects.count(), 0)

    def test_str_with_name(self):
        self.assertEqual(str(self.process), "Gold Search")

    def test_str_without_name(self):
        with self.assertRaises(ValidationError):
            Process.objects.create(organisation=self.org, name=None)


class DrillholeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(name="Drillhole Org", mode="MINING")
        cls.process = Process.objects.create(
            name="Phase 1", organisation=cls.org, mode="OPERATION"
        )

    def test_drillhole_creation_with_survey_data(self):
        dh = Drillhole.objects.create(
            name="DH-001",
            organisation=self.org,
            process=self.process,
            depth=150.5,
            azimuth=270.0,
            dip=-60.0,
        )

        dh.refresh_from_db()
        self.assertEqual(dh.depth, 150.5)
        self.assertEqual(dh.azimuth, 270.0)
        self.assertEqual(dh.dip, -60.0)

    def test_drillhole_optional_fields_nullable(self):
        dh = Drillhole.objects.create(
            name="DH-002",
            organisation=self.org,
            process=self.process,
        )

        self.assertIsNone(dh.depth)
        self.assertIsNone(dh.collar_location)

    def test_cascade_from_organisation(self):
        Drillhole.objects.create(
            name="DH-003", organisation=self.org, process=self.process
        )

        self.org.delete()
        self.assertEqual(Drillhole.objects.count(), 0)


class UserProfileSignalTests(TestCase):
    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user("geologist1", password="password123")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_profile_defaults(self):
        user = User.objects.create_user("newuser", password="password123")
        profile = user.profile
        self.assertEqual(profile.role, UserProfile.RoleChoices.VIEWER)
        self.assertEqual(profile.clearance_level, UserProfile.ClearanceLevel.INTERNAL)
        self.assertFalse(profile.can_approve_jorc)

    def test_fixture_loading_skips_signal(self):
        """
        tested implictly when loading fixtures (which pass `raw=True`) that don't contain matching
        UserProfile rows. the signal doesn't fire in this case, which would throw (?) an exception.
        """
        pass


class UserProfileRoleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password123")
        self.profile = self.user.profile

    def test_is_exploration_role(self):
        self.profile.role = UserProfile.RoleChoices.GEOLOGIST_EXPL
        self.assertTrue(self.profile.is_exploration_role())

    def test_is_mining_role(self):
        self.profile.role = UserProfile.RoleChoices.METALLURGIST
        self.assertTrue(self.profile.is_mining_role())

    def test_viewer_is_neither(self):
        self.profile.role = UserProfile.RoleChoices.VIEWER
        self.assertFalse(self.profile.is_exploration_role())
        self.assertFalse(self.profile.is_mining_role())


class DocumentAccessControlTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="AccessControl Org", mode="MINING")
        self.user = User.objects.create_user("accessor", password="password123")
        self.profile = self.user.profile
        self.profile.organisation = self.org

        self.profile.save()

    def _make_doc(self, confidentiality="internal", org=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return Document.objects.create(
            title="Test Doc",
            file=SimpleUploadedFile("test.txt", b"content"),
            organisation=org or self.org,
            confidentiality=confidentiality,
        )

    def test_internal_user_can_access_public_doc(self):
        doc = self._make_doc(confidentiality="public")
        self.profile.clearance_level = UserProfile.ClearanceLevel.INTERNAL
        self.assertTrue(self.profile.can_access_document(doc))

    def test_internal_user_cannot_access_confidential_doc(self):
        doc = self._make_doc(confidentiality="confidential")
        self.profile.clearance_level = UserProfile.ClearanceLevel.INTERNAL
        self.assertFalse(self.profile.can_access_document(doc))

    def test_cross_org_access_denied(self):
        other_org = Organisation.objects.create(name="Other", mode="EXPLORATION")
        doc = self._make_doc(confidentiality="public", org=other_org)
        self.assertFalse(self.profile.can_access_document(doc))

    def test_jorc_approved_can_access_restricted(self):
        doc = self._make_doc(confidentiality="jorc_restricted")
        self.profile.clearance_level = UserProfile.ClearanceLevel.JORC_APPROVED
        self.assertTrue(self.profile.can_access_document(doc))


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.submitter = User.objects.create_user("submitter", password="password")
        self.approver = User.objects.create_user("approver", password="password")
        self.org = Organisation.objects.create(name="Org", mode="MINING")

        self.approver.profile.can_approve_jorc = True
        self.approver.profile.role = UserProfile.RoleChoices.ADMIN
        self.approver.profile.save()

        self.workflow = ApprovalWorkflow.objects.create(
            content_type=ContentType.objects.get_for_model(Document),
            object_id=self.org.pk,
            workflow_type=ApprovalWorkflow.WorkflowType.JORC,
            submitted_by=self.submitter,
        )

    def test_default_status_is_pending(self):
        self.assertEqual(self.workflow.status, ApprovalWorkflow.Status.PENDING)

    def test_jorc_approver_can_approve(self):
        self.assertTrue(self.workflow.can_approve(self.approver))

    def test_regular_user_cannot_approve_jorc(self):
        self.assertFalse(self.workflow.can_approve(self.submitter))

    def test_general_workflow_allowed_for_field_lead(self):
        self.workflow.workflow_type = ApprovalWorkflow.WorkflowType.GENERAL
        self.approver.profile.role = UserProfile.RoleChoices.FIELD_LEAD
        self.approver.profile.save()
        self.assertTrue(self.workflow.can_approve(self.approver))


class AuditLogTests(TestCase):
    def test_log_audit_creates_entry(self):
        user = User.objects.create_user("auditor", password="password")
        org = Organisation.objects.create(name="Audited Org", mode="MINING")

        log_audit(
            user=user,
            action=AuditLog.ActionType.CREATE,
            obj=org,
            description="Created org",
            ip_address="192.168.1.1",
        )

        log = AuditLog.objects.get()
        self.assertEqual(log.user, user)
        self.assertEqual(log.action, "CREATE")
        self.assertEqual(log.object_id, org.pk)
        self.assertIn("192.168.1.1", log.ip_address)

    def test_audit_log_ordering_newest_first(self):
        user = User.objects.create_user("auditor", password="pass")
        org = Organisation.objects.create(name="Org", mode="MINING")
        for action in ["CREATE", "VIEW", "EDIT"]:
            log_audit(user=user, action=action, obj=org)

        logs = AuditLog.objects.all()
        self.assertTrue(logs[0].timestamp >= logs[1].timestamp)


