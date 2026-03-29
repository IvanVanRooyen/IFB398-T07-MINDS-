from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Drillhole, Organisation, Process


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
