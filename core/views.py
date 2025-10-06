# core/views.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import DocumentForm
from .models import Document, ProjectOp
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


def _count_model(app_label: str, model_name: str) -> int:
    mdl = _get_model(app_label, model_name)
    return mdl.objects.count() if mdl else 0


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
    projects = ProjectOp.objects.order_by("-created_at")[:10]
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
        "project_count": ProjectOp.objects.count(),
        "document_count": Document.objects.count(),
        "prospect_count": _count_model("core", "Prospect"),     # optional model
        "drillhole_count": _count_model("core", "Drillhole"),   # optional model
        "tenement_count": _count_model("core", "Tenement"),     # optional model
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
        "project_count": ProjectOp.objects.count(),
        "document_count": Document.objects.count(),
        "prospect_count": _count_model("core", "Prospect"),
        "drillhole_count": _count_model("core", "Drillhole"),
        "tenement_count": _count_model("core", "Tenement"),
    }
    # Render a small snippet template like core/partials/stats.html
    return render(request, "core/partials/stats.html", ctx)


# ---------- Documents ----------

@login_required
@require_http_methods(["GET", "POST"])
def upload_doc(request):
    """
    Upload with SHA-256 de-duplication (your original logic, with tiny polish).
    """
    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc: Document = form.save(commit=False)
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
            form.save_m2m()
            return redirect("upload")
    else:
        form = DocumentForm()

    docs = Document.objects.order_by("-created_at")[:20]
    return render(request, "core/upload.html", {"form": form, "docs": docs})


@require_GET
def documents(request):
    """
    Document library with search + pagination.
    """
    q = request.GET.get("q", "").strip()
    qs = Document.objects.all().order_by("-created_at")
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(project__name__icontains=q)
        )
    page = _paginate(qs, request, per_page=24)
    return render(request, "core/documents.html", {"page": page, "q": q})


@require_GET
def document_detail(request, pk: int):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "core/document_detail.html", {"doc": doc})


# ---------- Projects / Domain pages (safe even if models are missing) ----------

@require_GET
def prospects(request):
    Prospect = _get_model("core", "Prospect")
    qs = Prospect.objects.all().order_by("-id") if Prospect else []
    page = _paginate(qs, request) if Prospect else None
    return render(
        request,
        "core/prospects.html",
        {"page": page, "model_exists": Prospect is not None},
    )


@require_GET
def drillholes(request):
    Drillhole = _get_model("core", "Drillhole")
    qs = Drillhole.objects.all().order_by("-id") if Drillhole else []
    page = _paginate(qs, request) if Drillhole else None
    return render(
        request,
        "core/drillholes.html",
        {"page": page, "model_exists": Drillhole is not None},
    )


@require_GET
def tenements(request):
    Tenement = _get_model("core", "Tenement")
    qs = Tenement.objects.all().order_by("-id") if Tenement else []
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
            "recent_projects": ProjectOp.objects.order_by("-created_at")[:8],
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