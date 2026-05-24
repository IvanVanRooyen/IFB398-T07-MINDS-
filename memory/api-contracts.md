# API contracts

## Base URL and versioning

No API versioning prefix. All routes are at the root. The app is primarily server-rendered HTML (Django templates + HTMX). A small set of JSON API endpoints exist under `/api/` for the map viewer. Authentication is session-based (not token-based).

## Authentication header

Session cookie (`sessionid`). All views require `@login_required`. There is no `Authorization` header — this is not a REST API with token auth. All requests must carry a valid Django session.

CSRF token required on all POST/PUT/DELETE requests (Django middleware enforces this). HTMX requests include the CSRF token automatically via the `X-CSRFToken` header when configured.

## Standard response envelope

No standard JSON envelope. Most views return rendered HTML (200) or redirect (302). JSON responses (`JsonResponse`) are used only for the GeoJSON endpoints and a few HTMX partial endpoints.

---

## Endpoints

### Authentication

#### `GET /auth/login/`
**Auth required:** no
**Description:** Django login page

#### `POST /auth/login/`
**Auth required:** no
**Description:** Authenticate user; redirects to `/` on success, re-renders form on failure.

#### `GET|POST /auth/logout/`
**Auth required:** no
**Description:** Log out; redirects to `/auth/login/`.

---

### Dashboard

#### `GET /`
**Auth required:** yes
**Description:** Dashboard with metric counts and recent documents.

#### `GET /home/`
**Auth required:** yes
**Description:** Landing page with recent projects and documents.

---

### Projects (Process)

#### `GET /projects/`
**Auth required:** yes
**Description:** List all projects scoped to user's organisation.

#### `GET /projects/<uuid:pk>/`
**Auth required:** yes
**Description:** Project detail page with associated documents, drillholes, tenements.

#### `GET|POST /projects/<uuid:pk>/edit-boundary/`
**Auth required:** yes
**Description:** Edit the geospatial boundary (MultiPolygon) of a project.

---

### Prospects

#### `GET /prospects/`
**Auth required:** yes
**Description:** List prospects.

#### `GET|POST /prospects/new/`
**Auth required:** yes
**Description:** Create a new prospect (requires map pin placement via hidden lat/lng fields).

#### `GET /prospects/<uuid:pk>/`
**Auth required:** yes
**Description:** Prospect detail page showing linked drillholes, documents, reports.

#### `GET|POST /prospects/<uuid:pk>/edit/`
**Auth required:** yes
**Description:** Edit prospect metadata, hypothesis, objective, location.

#### `GET|POST /prospects/<uuid:pk>/generate-report/`
**Auth required:** yes
**Description:** Trigger AI report generation for a prospect; saves a SavedReport.

---

### Tenements

#### `GET /tenements/`
**Auth required:** yes
**Description:** List tenements.

#### `GET|POST /tenements/new/`
**Auth required:** yes
**Description:** Create a tenement with GeoJSON boundary drawn on the map.

#### `GET /tenements/<uuid:pk>/`
**Auth required:** yes
**Description:** Tenement detail page.

#### `GET|POST /tenements/<uuid:pk>/edit/`
**Auth required:** yes
**Description:** Edit tenement name, project assignment, and boundary.

---

### Drillholes

#### `GET /drillholes/`
**Auth required:** yes
**Description:** List drillholes.

#### `GET /drillholes/<uuid:pk>/`
**Auth required:** yes
**Description:** Drillhole detail: collar, survey data, lithology, assay results.

#### `GET|POST /drillholes/import/`
**Auth required:** yes
**Description:** Upload Excel file to bulk-import drillhole collar data via `run_drillhole_import`.

#### `GET /drillholes/link-picker/`
**Auth required:** yes
**Description:** HTMX partial — returns drillhole list for the prospect link picker UI.

#### `POST /drillholes/link/`
**Auth required:** yes
**Description:** Link a single drillhole to a prospect.

#### `POST /drillholes/bulk-link/`
**Auth required:** yes
**Description:** Link multiple drillholes to a prospect in one request.

#### `POST /drillholes/bulk-assign/`
**Auth required:** yes
**Description:** Bulk assign drillholes to a prospect.

#### `POST /drillholes/<uuid:pk>/unlink/`
**Auth required:** yes
**Description:** Remove a drillhole's prospect link.

---

### Documents

#### `GET /documents/`
**Auth required:** yes
**Description:** Document library with full-text search, tag/type/date filters, and pagination. Supports PostgreSQL FTS via `SearchQuery`/`SearchRank`.

#### `GET /documents/<uuid:pk>/`
**Auth required:** yes
**Description:** Document detail page; creates `DocumentView` record + `AuditLog` entry.

#### `GET|POST /upload/`
**Auth required:** yes (GEOLOGIST_EXPL, FIELD_LEAD, DATA_MANAGER, GEOLOGIST_MINE, METALLURGIST, OPS_MANAGER, ADMIN only)
**Description:** Upload a new document with SHA-256 deduplication, text extraction, chunk generation, and report cache warming.

#### `POST /documents/<uuid:pk>/delete/`
**Auth required:** yes
**Description:** Delete document and its MinIO file; logs audit entry.

#### `GET /documents/<uuid:pk>/download/`
**Auth required:** yes
**Description:** Redirect to a MinIO signed URL for the file; logs `DOWNLOAD` audit entry.

#### `GET|POST /documents/<uuid:pk>/replace/`
**Auth required:** yes
**Description:** Upload a new file version for an existing document (increments version_number, marks parent as non-latest).

---

### DocLinks

#### `GET /doclinks/picker/`
**Auth required:** yes
**Description:** HTMX partial — document picker for attaching docs to entities.

#### `POST /doclinks/create/`
**Auth required:** yes
**Description:** Create a DocLink (generic document-to-entity attachment).

#### `POST /doclinks/<int:pk>/delete/`
**Auth required:** yes
**Description:** Delete a DocLink.

---

### Map

#### `GET /map/`
**Auth required:** yes
**Description:** Leaflet map page; loads GeoJSON via AJAX from the four `/api/geojson/` endpoints.

---

### GeoJSON API (for map viewer)

All GeoJSON endpoints return `application/json` in GeoJSON FeatureCollection format. Responses are cached in Redis (key prefix `orefox`, default 300s TTL from settings).

#### `GET /api/geojson/projects/`
**Auth required:** yes
**Description:** All Process geometries (MultiPolygon) for the user's organisation.

#### `GET /api/geojson/tenements/`
**Auth required:** yes
**Description:** All Tenement geometries (MultiPolygon).

#### `GET /api/geojson/prospects/`
**Auth required:** yes
**Description:** All Prospect geometries (Point). Properties include `area_geom_geojson` (nested GeoJSON Polygon object) when the prospect has an area boundary set.

#### `GET /api/geojson/drillholes/`
**Auth required:** yes
**Description:** All Drillhole collar locations (Point).

#### `GET /api/spatial-search/`
**Auth required:** yes
**Description:** Spatial search — accepts a bounding box or point and returns entities within range.

---

### AI — Report Generation

#### `GET /ai/insights/`
**Auth required:** yes
**Description:** AI insights landing page.

#### `GET /ai/reports/`
**Auth required:** yes
**Description:** Generate-report UI. Lists recent reports in sidebar filtered by clearance level. Accepts `?q=` to FTS-filter the sidebar recent_reports list (up to 20 results).

#### `GET|POST /ai/reports/generate/`
**Auth required:** yes
**Description:** Generate a new AI report (calls Granite LLM, saves a SavedReport).

#### `GET /ai/reports/<uuid:report_id>/`
**Auth required:** yes
**Description:** View a saved report (renders Markdown as HTML).

#### `GET /ai/reports/history/`
**Auth required:** yes
**Description:** All reports history grouped by project. Accepts `?q=` for full-text search across title (A weight) and content_md (B weight) using PostgreSQL TSV; falls back to `title__icontains` for unindexed rows. Passes `q` and `total` (int or None) to template.

#### `GET /ai/reports/editor/<uuid:process_id>/`
**Auth required:** yes
**Description:** Report editor for a project — loads/generates Markdown for editing.

#### `GET /ai/reports/<uuid:report_id>/view/`
**Auth required:** yes
**Description:** Load an existing saved report into the editor.

#### `POST /ai/reports/save/`
**Auth required:** yes
**Description:** Save a new report (creates SavedReport v1).

#### `POST /ai/reports/<uuid:report_id>/update/`
**Auth required:** yes
**Description:** Save an edited version of an existing report (creates new version).

#### `GET /ai/report/<uuid:process_id>/pdf/`
**Auth required:** yes
**Description:** Download LLM-generated report as a PDF (via reportlab).

#### `GET /ai/report/<uuid:process_id>/docx/`
**Auth required:** yes
**Description:** Download LLM-generated report as a DOCX (via python-docx).

#### `POST /ai/reports/export/`
**Auth required:** yes
**Description:** Export editor content (posted Markdown) as PDF or DOCX.

---

#### `POST /ai/reports/<uuid:report_id>/assign-prospect/`
**Auth required:** yes
**Description:** Assign or clear a prospect FK on a `SavedReport`. POST body: `prospect_id` (UUID string or empty string to clear). Returns `{"ok": true}` on success or `{"error": "..."}` on failure.

---

### Samples

#### `GET /samples/`
**Auth required:** yes
**Description:** List samples scoped to user's organisation with pagination.

#### `GET|POST /samples/new/`
**Auth required:** yes (GEOLOGIST_EXPL, FIELD_LEAD, DATA_MANAGER, ADMIN)
**Description:** Create a new sample. Accepts optional `?prospect=<uuid>` to pre-populate prospect. Logs `CREATE` audit entry.

#### `GET /samples/<uuid:pk>/`
**Auth required:** yes
**Description:** Sample detail page showing all metadata fields.

---

### Surveys

#### `GET /surveys/`
**Auth required:** yes
**Description:** List surveys scoped to user's organisation with pagination.

#### `GET|POST /surveys/new/`
**Auth required:** yes (GEOLOGIST_EXPL, FIELD_LEAD, DATA_MANAGER, ADMIN)
**Description:** Create a new survey. Accepts optional `?prospect=<uuid>` to pre-populate prospect. Coverage area is a MapLibre GL polygon drawn by the user (submitted as GeoJSON via hidden `geom_geojson` field). Logs `CREATE` audit entry.

#### `GET /surveys/<uuid:pk>/`
**Auth required:** yes
**Description:** Survey detail page with optional coverage area map (MapLibre GL).

---

### AI — Report Approval Workflow

#### `POST /ai/reports/<uuid:report_id>/submit/`
**Auth required:** yes
**Description:** Submit a report for review; creates `ApprovalWorkflow` and sets report status to `UNDER_REVIEW`.

#### `POST /ai/reports/<uuid:report_id>/approve/`
**Auth required:** yes (requires `can_approve_jorc` or appropriate role)
**Description:** Approve a report; sets workflow status to `APPROVED`, report status to `APPROVED`.

#### `POST /ai/reports/<uuid:report_id>/reject/`
**Auth required:** yes (requires approval permission)
**Description:** Reject a report with notes; sets status to `REJECTED`.

#### `POST /ai/reports/<uuid:report_id>/publish/`
**Auth required:** yes
**Description:** Publish an approved report (status → `PUBLISHED`).

#### `GET /ai/approvals/`
**Auth required:** yes
**Description:** List all approval workflows (for reviewers/admins).

---

### AI — Document Analysis

#### `GET /ai/documents/analysis/`
**Auth required:** yes
**Description:** Document analysis listing page.

#### `POST /ai/documents/<uuid:pk>/analyze/`
**Auth required:** yes
**Description:** Run Granite LLM analysis on a document; saves result to `Document.analysis_text`.

#### `GET /ai/documents/<uuid:pk>/analysis/`
**Auth required:** yes
**Description:** View the analysis results for a document.

#### `POST /ai/documents/<uuid:pk>/analysis/save/`
**Auth required:** yes
**Description:** Save edited analysis text.

#### `GET /ai/documents/<uuid:pk>/analysis/export/`
**Auth required:** yes
**Description:** Export document analysis as PDF or DOCX.

---

### Report History

#### `GET /process/<uuid:process_id>/reports/history/`
**Auth required:** yes
**Description:** Version history for all reports in a project.

#### `GET /reports/<uuid:report_id>/version/`
**Auth required:** yes
**Description:** View a specific version of a report (read-only).

---

### Admin / Compliance

#### `GET /admin/audit-log/`
**Auth required:** yes
**Description:** Paginated audit log viewer (all user actions, scoped to user's org).

#### `GET /admin/` (Django admin)
**Auth required:** yes (superuser)
**Description:** Django admin interface.

---

## Webhooks

None.

## Rate limiting

None configured.
