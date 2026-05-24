# Decisions

## Decision log

---

### 2026-05-10 — Memory system initialised
**Decision:** Memory system created and all seven /memory/ files populated from code audit.
**Reason:** CLAUDE.md mandates the memory system; all files were [UNPOPULATED] at start.
**Alternatives considered:** N/A — first init run.
**Consequences / tradeoffs:** Future sessions should load these 7 files before writing code.

---

### [undated] — All models in a single models.py file
**Decision:** All 15+ models (domain, document, governance) live in `core/models.py` rather than split into separate files or a `models/` package.
**Reason:** Simplicity for a single-app project; avoids import complexity.
**Alternatives considered:** `core/models/` package with one file per domain group.
**Consequences / tradeoffs:** `models.py` is large (930+ lines). No functional downside for this codebase size, but will need splitting if the model count grows significantly.

---

### [undated] — Function-based views only (no CBVs)
**Decision:** All views are function-based views (FBV). Django's class-based views (CBV) are not used anywhere.
**Reason:** FBVs are more explicit and easier to reason about for the team. HTMX partial endpoints don't benefit from CBV mixins.
**Alternatives considered:** Django's generic CBVs (ListView, DetailView, etc.).
**Consequences / tradeoffs:** Some boilerplate repetition (pagination, org filtering) handled by private helper functions (`_paginate`, `_org_qs_filter`).

---

### [undated] — IBM Granite LLM with dual backend (Ollama / HuggingFace)
**Decision:** The LLM integration supports two backends selected by `GRANITE_BACKEND` env var: local Ollama (default) and HuggingFace Inference API. The same `GraniteClient` class handles both.
**Reason:** Local Ollama is free and private for development; HuggingFace provides a cloud fallback when Ollama is unavailable or for deployment.
**Alternatives considered:** OpenAI API, other models.
**Consequences / tradeoffs:** Model outputs may differ between backends. Cache keys are not backend-aware — if the backend changes, cached reports from the old backend will still be served until they expire.

---

### [undated] — LLM report cache keyed by (process_id, clearance_level, latest_doc_timestamp)
**Decision:** The Redis cache key for generated reports includes the user's clearance level and the timestamp of the most recently uploaded document for that project.
**Reason:** Different clearance levels see different documents (confidential docs excluded for lower-clearance users). Including the latest doc timestamp ensures the cache auto-invalidates when new documents are added, without requiring explicit cache busting.
**Alternatives considered:** Explicit cache invalidation on document upload; no caching.
**Consequences / tradeoffs:** One cache entry per (project × clearance level × doc upload event). If many documents are uploaded in quick succession, old cache entries are abandoned rather than deleted (they expire after 24h). This is acceptable.

---

### [undated] — Report cache pre-warmed at upload time
**Decision:** When a document is uploaded, the view immediately calls `generate_project_report()` and caches the result (in addition to saving the document). Granite errors during pre-warming are silently caught.
**Reason:** Shifts the LLM wait time from the first report-viewer to the uploader, improving perceived performance for readers.
**Alternatives considered:** Background task (Celery); lazy generation on first view.
**Consequences / tradeoffs:** Upload requests take longer (120s timeout). No Celery/task queue dependency needed.

---

### [undated] — SHA-256 deduplication before MinIO upload
**Decision:** `sha256_file()` is called on the uploaded file before writing it to MinIO. If a matching checksum already exists, the upload is rejected with an error message.
**Reason:** Prevents accidental re-upload of the same document, which would waste storage and confuse search results.
**Alternatives considered:** Filename deduplication (fragile); no deduplication.
**Consequences / tradeoffs:** Two identical files with different names cannot both be stored. This is intentional.

---

### [undated] — Document versioning via is_latest flag + parent_document FK
**Decision:** New document versions are created as separate `Document` records linked via `parent_document` FK. The `is_latest` boolean flag marks which record is the current version.
**Reason:** Preserves the full audit trail of file changes without modifying the original record. Keeps all versions in the same table.
**Alternatives considered:** Separate `DocumentVersion` table; overwrite-in-place.
**Consequences / tradeoffs:** All querysets over "current documents" must include `is_latest=True` filter. `Document.get_version_family()` traverses the chain; could be slow for long version chains.

---

### [undated] — Clearance level mismatch: Document uses lowercase strings, UserProfile uses uppercase
**Decision:** `Document.confidentiality` stores lowercase strings (`public`, `internal`, `confidential`, `jorc_restricted`). `UserProfile.clearance_level` stores uppercase strings (`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `JORC_APPROVED`). Mapping between them is done in `UserProfile.can_access_document()`, `retrieval.py`, and `report_service.py`.
**Reason:** Historical — confidentiality strings on Document were set before the `UserProfile.ClearanceLevel` enum was introduced. Never migrated for consistency.
**Alternatives considered:** Standardising both to uppercase or a shared enum.
**Consequences / tradeoffs:** Three separate dictionaries maintain the mapping (`doc_clearance_hierarchy`, `_CONFIDENTIALITY_MAP`, `CONFIDENTIALITY_MAP`). Any future clearance level addition must be added in all three places. This is a known tech debt.

---

### [undated] — Tailwind CSS via CDN only (no build step)
**Decision:** Tailwind CSS is loaded from a CDN link in templates. There is no Node.js, no `npm`, no PostCSS, no build pipeline.
**Reason:** Reduces toolchain complexity for a Django-only project. Avoids Node.js in the Docker container.
**Alternatives considered:** Standalone Tailwind CLI; django-tailwind.
**Consequences / tradeoffs:** All Tailwind classes must be available in the CDN version (Play CDN). Cannot use custom Tailwind config or plugins. Tree-shaking is not applied — full Tailwind bundle is loaded.

---

### [undated] — ValidatedChoiceModel abstract base for choice-field models
**Decision:** `Organisation` and `Process` inherit from `ValidatedChoiceModel` (which composes `ChoiceValidationMixin` + `AutoCleanMixin`) rather than using DB-level CHECK constraints alone.
**Reason:** Django's `full_clean()` is not called by `save()` by default. The mixin ensures `clean()` runs on every save and raises `ValidationError` for invalid choices, in addition to the DB CHECK constraints that provide a safety net.
**Alternatives considered:** DB CHECK constraints only; custom `save()` override per model.
**Consequences / tradeoffs:** Every `Organisation.save()` and `Process.save()` runs `full_clean()`, which is slightly slower. Tests must use `.save()` (not `.objects.create()` without `.save()`) to trigger validation.

---

### [undated] — Full observability stack in Docker Compose (not production-ready)
**Decision:** The `docker-compose.yml` includes a full Grafana stack (Alloy, Tempo, Loki, Prometheus, Grafana) and three metric exporters. Grafana anonymous admin access is enabled.
**Reason:** Provides observability during development and demo without additional infrastructure.
**Alternatives considered:** External observability service (Datadog, etc.); no observability.
**Consequences / tradeoffs:** `docker compose up` starts 13 containers. The anonymous Grafana admin config is explicitly marked in comments as not suitable for production. Alloy ports (4317, 4318, 12345) are bound to `0.0.0.0` without auth — also noted in comments as a dev-only config.

---

### 2026-05-10 — FTS search on SavedReport uses icontains fallback for unindexed rows
**Decision:** The `all_reports_history` and `report_list_page` FTS filter uses `Q(search_tsv=sq) | Q(title__icontains=q)` rather than `filter(search_tsv=sq)` alone.
**Reason:** Reports that existed before migration 0022 have `search_tsv = NULL` until the trigger fires on their next `INSERT OR UPDATE`. A pure FTS filter would silently exclude those rows. The `title__icontains` fallback ensures they remain discoverable by title until the trigger backfills them. The backfill SQL in the migration handles rows that exist at migration time; the fallback handles any edge case where a row slips through.
**Alternatives considered:** FTS-only (cleaner query, but silently drops rows); explicit Python-side backfill on app start (fragile); eager `save()` on all reports post-migration (wasteful).
**Consequences / tradeoffs:** Slightly more complex ORM query. The `icontains` path runs on every search even after all rows are indexed, but it is bounded to the user's org queryset and not hot-path enough to matter. Can be removed once the codebase is confident all rows are indexed.

---

### 2026-05-10 — core.urls must be included before admin.site.urls in config/urls.py
**Decision:** `path("", include("core.urls"))` is ordered before `path("admin/", admin.site.urls)` in `config/urls.py`.
**Reason:** Django's URL resolver matches patterns in order. `admin.site.urls` registers a catch-all that intercepts every URL beginning with `admin/` and returns a 404 for anything it doesn't recognise internally. The app has a custom `admin/audit-log/` route in core.urls; placing core.urls first ensures this route is matched before Django admin can intercept it.
**Alternatives considered:** Rename the route to a non-`admin/` prefix (e.g. `compliance/audit-log/`) — rejected because it changes the user-facing URL unnecessarily.
**Consequences / tradeoffs:** Any future custom route placed under the `admin/` prefix in core.urls will automatically work for the same reason. The Django admin panel (`admin/`, `admin/core/`, etc.) continues to work because those paths are not defined in core.urls and fall through to admin.site.urls.

---

<!-- Add new entries above this line, newest first -->
