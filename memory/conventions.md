# Conventions

## Folder structure

```
/
├── config/              Django project settings, root URL config, WSGI/ASGI
│   ├── settings.py
│   ├── urls.py          Only registers admin, auth login/logout, and include("core.urls")
│   ├── asgi.py
│   └── wsgi.py
├── core/                Sole Django app — all business logic lives here
│   ├── models.py        All 15+ models in one file
│   ├── views.py         All view functions in one file
│   ├── urls.py          All URL patterns in one file
│   ├── forms.py         All ModelForms and Forms
│   ├── permissions.py   RBAC/ABAC decorators and helper functions
│   ├── tagging.py       Centralized tag constants (TAG_CHOICES, TAG_LABEL)
│   ├── utils.py         SHA-256 hashing, PDF/DOCX text extraction, text chunking
│   ├── admin.py         Django admin registrations
│   ├── apps.py          AppConfig
│   ├── geo_utils.py     Geospatial utility helpers
│   ├── importers.py     Drillhole Excel import logic
│   ├── instrument.py    OTEL instrumentation setup
│   ├── telemetry.py     Telemetry helpers
│   ├── ai/
│   │   ├── granite_client.py   LLM HTTP client (Ollama or HuggingFace)
│   │   ├── retrieval.py        RAG chunk retrieval and formatting
│   │   └── report_service.py  Report generation orchestration
│   ├── migrations/      Django migrations (0001–0021 + merge 0015)
│   ├── tests/
│   │   ├── test_models.py
│   │   └── test_search.py
│   └── management/commands/
│       ├── seed_test_data.py
│       ├── generate_fixtures.py
│       ├── load_fixture_data.py
│       ├── import_drillhole_excel.py
│       └── seeding/         (constants, handlers, pdf_generator, utils)
├── templates/           Project-level templates (override or supplement core/templates/)
│   └── core/
│       ├── home.html
│       ├── dashboard.html (implied)
│       ├── report_detail.html
│       ├── report_history.html
│       ├── report_editor.html
│       ├── document_analysis_detail.html
│       └── partials/
│           └── stats.html   HTMX partial for dashboard stats refresh
├── static/              Static assets (logo, etc.)
├── infra/
│   ├── web/Dockerfile
│   └── telemetry/       Grafana Alloy, Tempo, Loki, Prometheus configs + ollama exporter
├── fixtures/            JSON fixtures and generated test PDFs
├── docs/                Project documentation PDFs
├── media/               Local dev media (not used in Docker — MinIO is used instead)
├── docker-compose.yml
├── pyproject.toml
├── manage.py
└── CLAUDE.md
```

## Naming conventions

| Thing | Convention | Example |
|-------|-----------|---------|
| Python files | snake_case | `report_service.py`, `granite_client.py` |
| Django models | PascalCase | `Organisation`, `SavedReport`, `DocLink` |
| DB table names | Django default (`core_<model>`) or explicit `db_table` | `user_profiles`, `audit_logs`, `saved_reports` |
| DB column names | snake_case (Django default) | `created_at`, `checksum_sha256`, `is_latest` |
| View functions | snake_case | `upload_doc`, `project_detail`, `geojson_projects` |
| URL names | snake_case with underscores | `"project_detail"`, `"audit_log"`, `"generate_report"` |
| Template files | snake_case, `.html` extension | `report_editor.html`, `document_analysis_detail.html` |
| Template partials | kept in `partials/` subdirectory | `partials/stats.html` |
| Form classes | PascalCase + `Form` suffix | `DocumentForm`, `DocumentSearchForm`, `ProspectForm` |
| Cache keys | colon-delimited namespaced strings | `"docs:unfiltered:page1:v1:{org_id}"`, `"report:v1:{process_id}:{clearance}:{ts}"` |
| Private helpers in views | leading underscore | `_org_qs_filter`, `_docs_cache_key`, `_paginate` |

## Import conventions

- Standard library imports first, then Django imports, then third-party, then local (`from .models import ...`, `from .utils import ...`).
- Lazy imports inside functions are used for heavy or circular-import-prone modules (e.g. `from .models import DocumentChunk` inside `views.upload_doc` to avoid circular imports).
- No path aliases (`@/`) — standard relative imports (`from .models import X`) throughout.

## Component patterns

**Views:**
- All function-based views (FBV) — no class-based views.
- Decorated with `@login_required` + optional RBAC decorators in stack order: `@login_required` → `@role_required(...)` → `@require_GET` / `@require_http_methods(...)`.
- HTTP method dispatch done via `if request.method == "POST":` inside the same function.
- Organisation scoping applied via `_org_qs_filter(request)` — a `Q()` object passed to `.filter()`. Superusers bypass it.
- Pagination via `_paginate(queryset, request, per_page=20)`.

**Models:**
- All domain model PKs are `UUIDField(primary_key=True, default=uuid.uuid4)`.
- All domain models have `created_at` (auto_now_add) and `updated_at` (auto_now).
- `ValidatedChoiceModel` abstract base class (`ChoiceValidationMixin` + `AutoCleanMixin`) used for models with choice fields that need DB-level constraint enforcement (Organisation, Process).
- `UserProfile` is auto-created via `post_save` signal on `User`.
- Document versioning: `is_latest` boolean flag + `parent_document` FK; use `Document.create_version()` classmethod to cut new versions.
- SavedReport versioning: `parent_version` FK; use `SavedReport.create_version()` classmethod.

**Forms:**
- All forms are `ModelForm` subclasses with explicit `fields` list.
- Organisation-scoped querysets injected via `__init__` parameter (e.g. `organisation=None`).
- Geometry set in `_post_clean()` override (not a form field) to work around GeoDjango + full_clean interaction.

**Templates:**
- Tailwind CSS via CDN (no build step).
- HTMX for partial updates (e.g. stats refresh on dashboard, document picker modals).
- Leaflet.js for the map.

## Error handling

**Backend:**
- `get_object_or_404(Model, pk=pk)` used in detail views — raises Http404 on missing object.
- Permission failures raise `PermissionDenied` (403) from decorators in `core/permissions.py`.
- `PermissionDenied` and `Http404` bubble up to Django's default error handlers.
- LLM errors (Granite unavailable) are caught with bare `except Exception: pass` in upload view's cache-warming block — the report is generated on first view request instead.
- File deletion errors in `Document.delete()` are logged (`logger.warning`) but do not prevent record deletion.
- `ValidationError` is raised in model `clean()` methods (Prospect validates non-empty hypothesis/objective/geom; `ValidatedChoiceModel` validates choice fields).

**Frontend:**
- Form validation errors rendered inline via Django's `{{ form.errors }}` template tag.
- Flash messages via `django.contrib.messages` (success/error banners).
- No client-side JS validation beyond what HTML5 provides (dates, required fields).

## Data fetching patterns

- **Server-rendered HTML**: most data is fetched in the view and passed as template context.
- **HTMX partials**: a few endpoints return partial HTML fragments (e.g. `stats_partial`, `doc_link_picker`, `drillhole_link_picker`).
- **GeoJSON AJAX**: map page fetches GeoJSON from `/api/geojson/*` endpoints via JavaScript `fetch()` on page load.
- **Redis caching**: report Markdown (`cache.get/set`, 24h TTL), document list (2min TTL), GeoJSON responses (300s default from settings).
- No React, no SWR, no React Query — pure Django template rendering + HTMX.

## Testing conventions

- Tests live in `core/tests/`, named `test_*.py`.
- Use `django.test.TestCase` for all tests (real DB, transactional rollback).
- `setUpTestData` used for class-level fixtures that don't mutate data.
- `setUp` used for per-test fixture data that may mutate.
- Tests import directly from `core.models` — no mocking of the database.
- Run with: `docker compose exec web python manage.py test core.tests --verbosity=2`

## Things to always do

- Filter document querysets with `is_latest=True` when showing current documents to users.
- Apply `_org_qs_filter(request)` to all querysets that return multi-tenant data.
- Log audit events via `log_audit(user, action, obj, ...)` for all CREATE/EDIT/DELETE/APPROVE/REJECT/DOWNLOAD actions.
- Set `created_by = request.user` on any new Document, SavedReport, or DocLink.
- Use `Document.create_version()` (not `Document.objects.create()`) when replacing a file.
- Use `sha256_file()` before saving a Document to detect duplicates before writing to MinIO.
- Check `not isinstance(cached, dict)` when reading LLM report cache to handle legacy string-cached values.

## Things to never do

- Do not use `Document.objects.create()` to upload a new version of an existing document — use `Document.create_version()`.
- Do not filter documents without `is_latest=True` unless specifically building version history UI.
- Do not store file content on disk — always use the MinIO-backed `file` field.
- Do not bypass `sha256_file()` deduplication on upload.
- Do not use class-based views — the codebase is function-based views throughout.
- Do not add Node.js or a JS build pipeline — Tailwind is CDN-only.
- Do not mock the database in tests — integration tests use a real PostgreSQL (PostGIS) database.
