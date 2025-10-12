# core/views.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.ai.report_service import generate_project_report
from .ai.granite_client import GraniteClient

import logging

from .forms import DocumentForm
from .models import Document, Process
from .utils import sha256_file


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


    return 0 if not mdl.objects.count() else mdl.objects.count()


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

            if doc.file:
                # Important: call sha256_file on the uploaded file *before* saving
                doc.checksum_sha256 = sha256_file(doc.file)

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

            doc.save()
            # form.save_m2m()
            return redirect("upload")
        else:
            # Show validation errors + keep the recent docs list
            # Show *why* it failed
            log.warning("Upload invalid: %s", form.errors)
            docs = Document.objects.order_by("created_at")[:20]
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
    q = request.GET.get("q", "").strip()
    tag = request.GET.get("tag")
    qs = Document.objects.all().order_by("-created_at")
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(doc_type__icontains=q)
            | Q(confidentiality__icontains=q)
            | Q(process__name__icontains=q)
            | Q(organisation__name__icontains=q)
        )
    if tag:
        try: 
            qs = qs.filter(tags__contains=[int(tag)])
        except (TypeError, ValueError):
            pass

    page = _paginate(qs, request, per_page=24)
    return render(request, "core/documents.html", {"page": page, "q": q})


@require_GET
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "core/document_detail.html", {"doc": doc})


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
    Simple map page that you can wire to Leaflet / PostGIS endpoints.
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