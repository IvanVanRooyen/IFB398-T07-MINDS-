"""
Tests for document search and filtering functionality.
 
Covers core/views.py::documents() and the DocumentSearchForm.
 
Run with:
docker compose exec web python manage.py test core.tests.test_search --verbosity=2
<<<<<<< HEAD
"""

=======

"""
>>>>>>> a68a026 (Added tests for search functionality)
import datetime
from django.test import TestCase, Client
from django.urls import reverse
 
from core.models import Document, Organisation, Process

# Shared fixture helpers
def make_org(name="Test Org", mode="EXPLORATION"):
    return Organisation.objects.create(name=name, mode=mode)
 
 
def make_process(org, name="Test Project", mode="PROJECT", commodity=None):
    return Process.objects.create(
        organisation=org,
        name=name,
        mode=mode,
        commodity=commodity,
    )
 
 
def make_doc(title, **kwargs):
    """
    Create a Document with sensible defaults.
    File field is left blank (empty string) — the search view doesn't
    need a real file to exercise filtering logic.
    """
    defaults = dict(
        file="",
        doc_type="",
        confidentiality="internal",
        extracted_text="",
        tags=[],
        timestamp=None,
        organisation=None,
        process=None,
        checksum_sha256="",
    )
    defaults.update(kwargs)
    return Document.objects.create(title=title, **defaults)

class KeywordSearchTests(TestCase):
    """The q parameter searches across title, doc_type, confidentiality,
    process name, organisation name, and extracted_text."""
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
        self.org = make_org("GoldCorp")
        self.process = make_process(self.org, name="Alpha Project")
 
        self.doc_title = make_doc(
            "Uranium Feasibility Study",
            organisation=self.org,
        )
        self.doc_type = make_doc(
            "Quarterly Summary",
            doc_type="Geophysics Report",
            organisation=self.org,
        )
        self.doc_extracted = make_doc(
            "Field Notes",
            extracted_text="The borehole intersected a magnetite skarn at 340m depth.",
            organisation=self.org,
        )
        self.doc_project = make_doc(
            "Project Overview",
            process=self.process,
            organisation=self.org,
        )
        self.doc_org = make_doc(
            "Annual Review",
            organisation=self.org,
        )
        self.unrelated = make_doc("Completely Unrelated Document")
 
    def _get(self, q):
        response = self.client.get(self.url, {"q": q})
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_search_by_title(self):
        results = self._get("Uranium")
        self.assertIn("Uranium Feasibility Study", results)
        self.assertNotIn("Quarterly Summary", results)
 
    def test_search_by_title_case_insensitive(self):
        results = self._get("uranium feasibility")
        self.assertIn("Uranium Feasibility Study", results)
 
    def test_search_by_doc_type(self):
        results = self._get("Geophysics")
        self.assertIn("Quarterly Summary", results)
        self.assertNotIn("Uranium Feasibility Study", results)
 
    def test_search_by_extracted_text(self):
        results = self._get("magnetite skarn")
        self.assertIn("Field Notes", results)
        self.assertNotIn("Uranium Feasibility Study", results)
 
    def test_search_by_process_name(self):
        results = self._get("Alpha Project")
        self.assertIn("Project Overview", results)
        self.assertNotIn("Uranium Feasibility Study", results)
 
    def test_search_by_organisation_name(self):
        results = self._get("GoldCorp")
        # All docs linked to GoldCorp should appear
        self.assertIn("Uranium Feasibility Study", results)
        self.assertIn("Quarterly Summary", results)
        self.assertNotIn("Completely Unrelated Document", results)
 
    def test_empty_query_returns_all(self):
        results = self._get("")
        self.assertIn("Uranium Feasibility Study", results)
        self.assertIn("Completely Unrelated Document", results)
 
    def test_no_match_returns_empty(self):
        results = self._get("xyzzy_no_such_term")
        self.assertEqual(results, [])
<<<<<<< HEAD
=======
 
    def test_partial_word_match(self):
        # icontains should match substrings
        results = self._get("Uran")
        self.assertIn("Uranium Feasibility Study", results)
>>>>>>> a68a026 (Added tests for search functionality)

class ProjectFilterTests(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
        self.org = make_org()
        self.proj_a = make_process(self.org, name="Project Alpha")
        self.proj_b = make_process(self.org, name="Project Beta")
 
        self.doc_a = make_doc("Doc in Alpha", process=self.proj_a, organisation=self.org)
        self.doc_b = make_doc("Doc in Beta",  process=self.proj_b, organisation=self.org)
        self.doc_none = make_doc("No Project Doc", organisation=self.org)
 
    def _get(self, process_id):
        response = self.client.get(self.url, {"process": str(process_id)})
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_filter_by_project_returns_only_that_project(self):
        results = self._get(self.proj_a.pk)
        self.assertIn("Doc in Alpha", results)
        self.assertNotIn("Doc in Beta", results)
        self.assertNotIn("No Project Doc", results)
<<<<<<< HEAD
=======
 
    def test_filter_by_other_project(self):
        results = self._get(self.proj_b.pk)
        self.assertIn("Doc in Beta", results)
        self.assertNotIn("Doc in Alpha", results)
>>>>>>> a68a026 (Added tests for search functionality)

class DateRangeFilterTests(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
 
        self.doc_jan = make_doc("January Report", timestamp=datetime.date(2024, 1, 15))
        self.doc_jun = make_doc("June Report",    timestamp=datetime.date(2024, 6, 10))
        self.doc_dec = make_doc("December Report", timestamp=datetime.date(2024, 12, 20))
        self.doc_no_date = make_doc("Undated Report")
 
    def _get(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_date_from_excludes_earlier(self):
        results = self._get(date_from="2024-06-01")
        self.assertIn("June Report", results)
        self.assertIn("December Report", results)
        self.assertNotIn("January Report", results)
 
    def test_date_to_excludes_later(self):
        results = self._get(date_to="2024-06-30")
        self.assertIn("January Report", results)
        self.assertIn("June Report", results)
        self.assertNotIn("December Report", results)
 
    def test_date_range_inclusive_boundaries(self):
        # Exact boundary dates should be included
        results = self._get(date_from="2024-06-10", date_to="2024-06-10")
        self.assertIn("June Report", results)
        self.assertNotIn("January Report", results)
        self.assertNotIn("December Report", results)
 
    def test_combined_date_range(self):
        results = self._get(date_from="2024-02-01", date_to="2024-11-30")
        self.assertIn("June Report", results)
        self.assertNotIn("January Report", results)
        self.assertNotIn("December Report", results)
 
    def test_no_date_filter_returns_all(self):
        results = self._get()
        self.assertIn("January Report", results)
        self.assertIn("June Report", results)
        self.assertIn("December Report", results)

class DocTypeFilterTests(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
 
        self.doc_geo = make_doc("Geo Report", doc_type="Geophysics")
        self.doc_drill = make_doc("Drill Summary", doc_type="Drill Log")
        self.doc_none = make_doc("No Type Doc", doc_type="")
 
    def _get(self, doc_type):
        response = self.client.get(self.url, {"doc_type": doc_type})
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_filter_by_doc_type(self):
        results = self._get("Geophysics")
        self.assertIn("Geo Report", results)
        self.assertNotIn("Drill Summary", results)
 
    def test_doc_type_filter_case_insensitive(self):
        # View uses iexact
        results = self._get("geophysics")
        self.assertIn("Geo Report", results)
 
    def test_empty_doc_type_returns_all(self):
        results = self._get("")
        self.assertIn("Geo Report", results)
        self.assertIn("Drill Summary", results)

class ConfidentialityFilterTests(TestCase):
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
 
        self.doc_pub  = make_doc("Public Report",        confidentiality="public")
        self.doc_int  = make_doc("Internal Report",      confidentiality="internal")
        self.doc_conf = make_doc("Confidential Report",  confidentiality="confidential")
 
    def _get(self, confidentiality):
        response = self.client.get(self.url, {"confidentiality": confidentiality})
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_filter_public(self):
        results = self._get("public")
        self.assertIn("Public Report", results)
        self.assertNotIn("Internal Report", results)
        self.assertNotIn("Confidential Report", results)
 
    def test_filter_internal(self):
        results = self._get("internal")
        self.assertIn("Internal Report", results)
        self.assertNotIn("Public Report", results)
 
    def test_filter_confidential(self):
        results = self._get("confidential")
        self.assertIn("Confidential Report", results)
        self.assertNotIn("Public Report", results)
 
    def test_no_filter_returns_all(self):
        results = self._get("")
        self.assertIn("Public Report", results)
        self.assertIn("Internal Report", results)
        self.assertIn("Confidential Report", results)

class TagFilterTests(TestCase):
    """Tags are stored as an integer ArrayField.
    The view filters using tags__contains=[int(tag)]."""
 
    def setUp(self):
        self.client = Client()
        self.url = reverse("documents")
<<<<<<< HEAD

        self.doc_exploration = make_doc("Exploration Doc", tags=[10])          
        self.doc_drill       = make_doc("Drill Doc",       tags=[11])          
        self.doc_multi       = make_doc("Multi-tag Doc",   tags=[10, 12])     
=======
 
        # Tag IDs from core/tagging.py
        self.doc_exploration = make_doc("Exploration Doc", tags=[10])          # Exploration Report
        self.doc_drill       = make_doc("Drill Doc",       tags=[11])          # Drill Logs
        self.doc_multi       = make_doc("Multi-tag Doc",   tags=[10, 12])      # Exploration + Assay
>>>>>>> a68a026 (Added tests for search functionality)
        self.doc_no_tags     = make_doc("Untagged Doc",    tags=[])
 
    def _get(self, tag):
        response = self.client.get(self.url, {"tag": str(tag)})
        self.assertEqual(response.status_code, 200)
        return [d.title for d in response.context["page"].object_list]
 
    def test_filter_by_single_tag(self):
        results = self._get(10)
        self.assertIn("Exploration Doc", results)
<<<<<<< HEAD
        self.assertIn("Multi-tag Doc", results)      
=======
        self.assertIn("Multi-tag Doc", results)      # has tag 10 among others
>>>>>>> a68a026 (Added tests for search functionality)
        self.assertNotIn("Drill Doc", results)
        self.assertNotIn("Untagged Doc", results)
 
    def test_filter_by_different_tag(self):
        results = self._get(11)
        self.assertIn("Drill Doc", results)
        self.assertNotIn("Exploration Doc", results)
 
    def test_filter_by_tag_on_multitag_doc(self):
        # Tag 12 only appears on multi-tag doc
        results = self._get(12)
        self.assertIn("Multi-tag Doc", results)
        self.assertNotIn("Exploration Doc", results)
 
    def test_no_tag_filter_returns_all(self):
        results = self._get("")
        self.assertIn("Exploration Doc", results)
        self.assertIn("Untagged Doc", results)