# core/views.py
from __future__ import annotations
from pydoc import doc

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django.shortcuts import render, redirect
from django.contrib import messages

from core.ai.report_service import generate_project_report
from .ai.granite_client import GraniteClient

import logging

from .forms import DocumentForm, DocumentSearchForm
from .models import Document, Process
from .utils import sha256_file, extract_text, chunk_text

from .tagging import TAG_LABEL


# ---------- Helpers ----------


def _get_model(app_label: str, model_name: str):
    """
    Best-effort dynamic model fetch (lets views work even if model doesn’t exist yet).
    """
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _count_model(app_label: str, model_name: str, where_clause: str = None) -> int:
    mdl = _get_model(app_label, model_name)
    if mdl is None:
        return 0
    return mdl.objects.count()


def _paginate(queryset, request, per_page: int = 20):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


# ---------- Landing / Dashboard ----------


@require_GET
def home(request):
    """
    Simple landing that shows recent Projects & Documents (as per your snippet).
    """
    projects = Process.objects.order_by("-created_at")[:10]
    docs = Document.objects.order_by("-created_at")[:10]
    return render(
        request,
        "core/home.html",
        {"projects": projects, "docs": docs},
    )


@require_GET
def dashboard(request):
    """
    Dashboard cards + quick links. Works even if domain models aren’t ready yet.
    """
    metrics = {
        "project_count": Process.objects.count(),
        "document_count": Document.objects.count(),
        "prospect_count": _count_model("core", "Prospect"),  # optional model
        "drillhole_count": _count_model("core", "Drillhole"),  # optional model
        "tenement_count": _count_model("core", "Tenement"),  # optional model
    }
    recent_docs = Document.objects.order_by("-created_at")[:8]
    return render(
        request,
        "core/dashboard.html",
        {"metrics": metrics, "recent_docs": recent_docs},
    )


# Optional: HTMX endpoint to refresh stats without reloading the whole page
@require_GET
def stats_partial(request):
    ctx = {
        "project_count": Process.objects.count(),
        "document_count": Document.objects.count(),
        "prospect_count": _count_model("core", "Prospect"),
        "drillhole_count": _count_model("core", "Drillhole"),
        "tenement_count": _count_model("core", "Tenement"),
    }
    # Render a small snippet template like core/partials/stats.html
    return render(request, "core/partials/stats.html", ctx)


# ---------- Documents ----------

log = logging.getLogger(__name__)

# @login_required
@require_http_methods(["GET", "POST"])
def upload_doc(request):
    """
    Upload with SHA-256 de-duplication (your original logic, with tiny polish).
    """
    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        log.debug("FILES keys: %s", list(request.FILES.keys()))  # debug: ensure 'file' is present
        if form.is_valid():
            doc = form.save(commit=False)
            # Only set if user is authenticated (created_by is nullable)
            if request.user.is_authenticated:
                doc.created_by = request.user
            
            # Give extracted text a safe default in case extraction fails, to avoid null issues in search
            doc.extracted_text = ""

            if doc.file:
                # Important: call sha256_file on the uploaded file *before* saving
                doc.checksum_sha256 = sha256_file(doc.file)
                doc.extracted_text = extract_text(doc.file) or ""

            if doc.checksum_sha256 and Document.objects.filter(
                checksum_sha256=doc.checksum_sha256
            ).exists():
                # Duplicate detected — re-render with error + keep their form state
                docs = Document.objects.order_by("-created_at")[:20]
                return render(
                    request,
                    "core/upload.html",
                    {
                        "form": form,
                        "docs": docs,
                        "error": "Duplicate file detected (checksum match).",
                    },
                )

            doc.extracted_text = doc.extracted_text or ""

            #Debug
            print("BEFORE SAVE extracted_text:", repr(doc.extracted_text))
            print("BEFORE SAVE type:", type(doc.extracted_text))
            print("BEFORE SAVE dict:", {
                "title": doc.title,
                "doc_type": doc.doc_type,
                "confidentiality": doc.confidentiality,
                "organisation_id": doc.organisation_id,
                "process_id": doc.process_id,
                "created_by_id": doc.created_by_id,
                "extracted_text": repr(doc.extracted_text),
            })

            doc.save()
            # form.save_m2m()
            # Build text chunks for RAG retrieval
            if doc.extracted_text:
                from .models import DocumentChunk
                chunks = chunk_text(doc.extracted_text)
                DocumentChunk.objects.bulk_create([
                    DocumentChunk(
                    document=doc,
                    chunk_index=i,
                    text=chunk,
                    process=doc.process,
                    doc_type=doc.doc_type,
                    timestamp=doc.timestamp,
                    )
                    for i, chunk in enumerate(chunks)
                ])
                
            return redirect("upload")
        else:
            # Show validation errors + keep the recent docs list
            # Show *why* it failed
            log.warning("Upload invalid: %s", form.errors)
            docs = Document.objects.order_by("-created_at")[:20]
            return render(
                request,
                "core/upload.html",
                {"form": form, "docs": docs, "error": "Please correct the errors below."},
            )
    
    # GET
    form = DocumentForm()
    docs = Document.objects.order_by("-created_at")[:20]
    return render(request, "core/upload.html", {"form": form, "docs": docs})


@require_GET
def documents(request):
    """
    Document library with search + tag + pagination.
    """
    # Build doc_type choices from whatever is actually in the DB
    existing_types = (
        Document.objects
        .exclude(doc_type="")
        .exclude(doc_type__isnull=True)
        .values_list("doc_type", flat=True)
        .distinct()
        .order_by("doc_type")
    )

    type_choices = [("", "All types")] + [(t, t) for t in existing_types]

    form = DocumentSearchForm(request.GET or None, doc_type_choices=type_choices)
    qs = Document.objects.select_related("process", "organisation").order_by("-created_at")

    q_value = ""
    if form.is_valid():

        # Full-text : title, doc_type, confidentiality, project name, org
        q = form.cleaned_data.get("q", "").strip()

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(doc_type__icontains=q)
                | Q(confidentiality__icontains=q)
                | Q(process__name__icontains=q)
                | Q(organisation__name__icontains=q)
                | Q(extracted_text__icontains=q)
            )

        # Project
        process = form.cleaned_data.get("process")
        if process:
            qs = qs.filter(process=process)
 
        # Date range (inclusive, on the document's own date)
        date_from = form.cleaned_data.get("date_from")
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
 
        date_to = form.cleaned_data.get("date_to")
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)
 
        # Metadata
        doc_type = form.cleaned_data.get("doc_type")
        if doc_type:
            qs = qs.filter(doc_type__iexact=doc_type)
 
        confidentiality = form.cleaned_data.get("confidentiality")
        if confidentiality:
            qs = qs.filter(confidentiality__iexact=confidentiality)
 
        tag = form.cleaned_data.get("tag")
        if tag:
            try:
                qs = qs.filter(tags__contains=[int(tag)])
            except (TypeError, ValueError):
                pass
 
    filters_active = any(request.GET.get(f) for f in
                         ["q", "process", "date_from", "date_to", "doc_type", "confidentiality", "tag"])
    
    page = _paginate(qs, request, per_page=24)

    return render(request, "core/documents.html", {
        "form": form,
        "page": page,
        "q": q_value,
        "filters_active": filters_active,
    })


@require_GET
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    # Resolve tag integers to their human-readable labels
    tag_labels = [TAG_LABEL.get(t, f"Tag {t}") for t in (doc.tags or [])]
    return render(request, "core/document_detail.html", {
        "doc": doc,
        "tag_labels": tag_labels,
        })


@require_http_methods(["POST", "DELETE"])
def delete_document(request, pk):
    """
    Delete a document and its associated file from storage (MinIO).
    """
    doc = get_object_or_404(Document, pk=pk)

    # Store title for success message
    doc_title = doc.title

    try:
        # The delete() method on the model will handle file deletion from MinIO
        doc.delete()

        # Return JSON response for HTMX/AJAX requests
        if request.headers.get('HX-Request'):
            return JsonResponse({
                "success": True,
                "message": f"Document '{doc_title}' deleted successfully."
            })

        # Redirect for regular form submissions
        return redirect("upload")

    except Exception as e:
        if request.headers.get('HX-Request'):
            return JsonResponse({
                "success": False,
                "message": f"Error deleting document: {str(e)}"
            }, status=500)

        # For regular requests, redirect with error (would need messages framework)
        return redirect("upload")


# ---------- Projects / Domain pages (safe even if models are missing) ----------


@require_GET
def prospects(request):
    Prospect = _get_model("core", "Prospect")
    qs = Prospect.objects.all().order_by("-created_at") if Prospect else []
    page = _paginate(qs, request) if Prospect else None
    return render(
        request,
        "core/prospects.html",
        {"page": page, "model_exists": Prospect is not None},
    )


@require_GET
def drillholes(request):
    Drillhole = _get_model("core", "Drillhole")
    qs = Drillhole.objects.all().order_by("-created_at") if Drillhole else []
    page = _paginate(qs, request) if Drillhole else None
    return render(
        request,
        "core/drillholes.html",
        {"page": page, "model_exists": Drillhole is not None},
    )


@require_GET
def tenements(request):
    Tenement = _get_model("core", "Tenement")
    qs = Tenement.objects.all().order_by("-created_at") if Tenement else []
    page = _paginate(qs, request) if Tenement else None
    return render(
        request,
        "core/tenements.html",
        {"page": page, "model_exists": Tenement is not None},
    )


# ---------- AI / Map / Utilities ----------


@require_GET
def ai_insights(request):
    """
    Placeholder page for AI features (report generation, summarization, etc.).
    """
    # You can pass recent docs/projects for prompts, etc.
    return render(
        request,
        "core/ai_insights.html",
        {
            "recent_docs": Document.objects.order_by("-created_at")[:12],
            "recent_projects": Process.objects.order_by("-created_at")[:8],
        },
    )


@require_GET
def map_view(request):
    """
    Simple map page that we should consider wiring to Leaflet / PostGIS endpoints.
    """
    return render(request, "core/map.html")


@require_GET
def healthcheck(request):
    """
    Lightweight container health endpoint (used by k8s/docker healthchecks later).
    """
    return JsonResponse({"status": "ok"})


@require_GET
def project_report(request, process_id: str):
    # Validate the project exists early
    if not Process.objects.filter(pk=process_id).exists():
        raise Http404("Project not found")

    md = generate_project_report(process_id)

    # Choose JSON if requested
    if request.GET.get("format") == "json":
        return JsonResponse({"markdown": md})

    # Minimal HTML wrapper
    return HttpResponse(
        f"<html><body><pre style='white-space:pre-wrap'>{md}</pre></body></html>",
        content_type="text/html",
    )

# ---------- GeoJSON API Endpoints for Map Viewer ----------


@require_GET
def geojson_projects(request):
    """
    GeoJSON endpoint for Process (projects/operations) with spatial data
    Returns all processes with geometry for da map
    """
    from django.core.serializers import serialize
    from .models import Process

    # Only include processes with geometry
    processes = Process.objects.filter(geom__isnull=False).select_related('organisation')

    if not processes.exists():
        return JsonResponse({"type": "FeatureCollection", "features": []})

    # Use GeoDjangos built in serialiser (lets us take coordinates and translate into GeoJSOn text for geodata)
    geojson_data = serialize(
        'geojson',
        processes,
        geometry_field='geom',
        fields=('name', 'mode', 'commodity', 'organisation')
    )

    # Parse and return as JSON (serialise returns a string )
    import json
    return JsonResponse(json.loads(geojson_data), safe=False)


@require_GET
def geojson_tenements(request):
    """
    GeoJSON endpoint for Tenement boundaries.
    Returns all tenements with geometry for map visualisation
    """
    from django.core.serializers import serialize
    from .models import Tenement

    tenements = Tenement.objects.filter(geom__isnull=False).select_related('organisation', 'process')

    if not tenements.exists():
        return JsonResponse({"type": "FeatureCollection", "features": []})

    geojson_data = serialize(
        'geojson',
        tenements,
        geometry_field='geom',
        fields=('name', 'organisation', 'process')
    )

    import json
    return JsonResponse(json.loads(geojson_data), safe=False)


@require_GET
def geojson_prospects(request):
    """
    GeoJSON endpoint for Prospect locations
    Returns all prospects with geometry 
    """
    from django.core.serializers import serialize
    from .models import Prospect

    prospects = Prospect.objects.filter(geom__isnull=False).select_related('organisation', 'process')

    if not prospects.exists():
        return JsonResponse({"type": "FeatureCollection", "features": []})

    geojson_data = serialize(
        'geojson',
        prospects,
        geometry_field='geom',
        fields=('name', 'organisation', 'process')
    )

    import json
    return JsonResponse(json.loads(geojson_data), safe=False)


@require_GET
def geojson_drillholes(request):
    """
    GeoJSON endpoint for Drillhole collar locations.
    Returns all drillholes with collar locations 
    """
    from django.core.serializers import serialize
    from .models import Drillhole

    drillholes = Drillhole.objects.filter(collar_location__isnull=False).select_related('organisation', 'process')

    if not drillholes.exists():
        return JsonResponse({"type": "FeatureCollection", "features": []})

    geojson_data = serialize(
        'geojson',
        drillholes,
        geometry_field='collar_location',
        fields=('name', 'depth', 'azimuth', 'dip', 'organisation', 'process')
    )

    import json
    return JsonResponse(json.loads(geojson_data), safe=False)

# ---------- AI Report Generation & Document Analysis Pages ----------
def report_list_page(request):
    return render(request, "core/report_list.html", {
        "recent_reports": [],
        "recent_projects": [],
    })


def generate_report(request):
    if request.method == "POST":
        messages.success(request, "Report generation started.")
    return redirect("report_list")


def report_detail(request, report_id):
    return render(request, "core/report_detail.html", {
        "report_id": report_id,
    })


def document_analysis_page(request):
    return render(request, "core/document_analysis.html", {
        "recent_docs": [],
    })


def analyze_document(request, pk):
    if request.method == "POST":
        messages.success(request, f"Analysis started for document {pk}.")
    return redirect("ai_insights")


def document_analysis_detail(request, pk):
    return render(request, "core/document_analysis_detail.html", {
        "doc_id": pk,
    })