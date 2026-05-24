# Database schema

## Database technology

PostgreSQL 16 + PostGIS 3.4, accessed via Django ORM with `django.contrib.gis.db.backends.postgis` engine. Migrations managed by Django's migration system (`core/migrations/`). Run with `python manage.py migrate`.

## Tables

### `core_organisation`
Represents a mining/exploration company. One org can have many projects, users, and documents.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(32) | YES | — | |
| mode | VARCHAR | NOT NULL | EXPLORATION | EXPLORATION or MINING |
| created_at | TIMESTAMPTZ | NOT NULL | now() | auto_now_add |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | auto_now |

**Constraints:** `valid_organisation_mode` CHECK (mode IN ['EXPLORATION', 'MINING'])

---

### `core_process`
A project or operation (campaign) belonging to an organisation. Has optional geospatial boundary.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | YES | — | |
| organisation_id | UUID | YES | — | FK → core_organisation |
| mode | VARCHAR | NOT NULL | PROJECT | PROJECT or OPERATION |
| geom | MULTIPOLYGON (SRID 4326) | YES | — | |
| commodity | VARCHAR(64) | YES | — | e.g. Gold, Copper |
| created_at | TIMESTAMPTZ | NOT NULL | now() | auto_now_add |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | auto_now |

**Constraints:** `valid_process_mode` CHECK (mode IN ['PROJECT', 'OPERATION'])
**Relations:** organisation_id → core_organisation.id (CASCADE)

---

### `core_prospect`
An exploration prospect (a specific point of interest within a project). Requires hypothesis and objective text.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | NOT NULL | — | |
| organisation_id | UUID | NOT NULL | — | FK → core_organisation |
| process_id | UUID | NOT NULL | — | FK → core_process |
| hypothesis | TEXT | NOT NULL | — | geological hypothesis (required) |
| objective | TEXT | NOT NULL | — | exploration objective (required) |
| geom | POINT (SRID 4326) | YES | — | location (required by clean()) |
| area_geom | POLYGON (SRID 4326) | YES | — | optional area boundary drawn by user |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (CASCADE)

---

### `core_tenement`
A mining lease or exploration license boundary (polygon).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | NOT NULL | — | e.g. EPM 27431 |
| organisation_id | UUID | NOT NULL | — | FK → core_organisation |
| process_id | UUID | NOT NULL | — | FK → core_process |
| geom | MULTIPOLYGON (SRID 4326) | YES | — | lease/license boundary |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (CASCADE)

---

### `core_drillhole`
A drillhole with collar location, survey data, and extended metadata. Can be linked to a prospect.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | NOT NULL | — | |
| organisation_id | UUID | NOT NULL | — | FK → core_organisation |
| process_id | UUID | NOT NULL | — | FK → core_process |
| prospect_id | UUID | YES | — | FK → core_prospect (SET_NULL) |
| collar_location | POINT (SRID 4326) | YES | — | |
| depth | FLOAT | YES | — | total depth in metres |
| azimuth | FLOAT | YES | — | bearing true north (0–360) |
| dip | FLOAT | YES | — | dip angle (-90 to 90) |
| drill_type | VARCHAR(8) | YES | — | RC, DDH, RAB, AC |
| company | VARCHAR(128) | YES | — | |
| drill_company | VARCHAR(128) | YES | — | |
| current_epm | VARCHAR(64) | YES | — | |
| original_epm | VARCHAR(64) | YES | — | |
| year_report | SMALLINT | YES | — | |
| company_report | VARCHAR(64) | YES | — | |
| elevation | FLOAT | YES | — | collar RL in metres |
| date_commenced | DATE | YES | — | |
| date_completed | DATE | YES | — | |
| hole_id_original | VARCHAR(64) | YES | — | |
| comments | TEXT | YES | — | |
| source_crs | VARCHAR(32) | YES | — | e.g. EPSG:28356 |
| source_easting | FLOAT | YES | — | raw coordinate before WGS84 transform |
| source_northing | FLOAT | YES | — | raw coordinate before WGS84 transform |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (CASCADE), prospect_id → core_prospect.id (SET_NULL)

---

### `core_drillholesurvey`
Down-hole survey readings for a drillhole (azimuth/dip by depth).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| drillhole_id | UUID | NOT NULL | — | FK → core_drillhole (CASCADE) |
| depth | FLOAT | NOT NULL | — | metres down hole |
| dip | FLOAT | YES | — | degrees |
| azimuth_tn | FLOAT | YES | — | azimuth true north (0–360) |
| azimuth_mag | FLOAT | YES | — | azimuth magnetic (0–360) |
| comment | VARCHAR(128) | YES | — | |

**Ordering:** drillhole, depth

---

### `core_lithologyinterval`
Lithology log intervals for a drillhole.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| drillhole_id | UUID | NOT NULL | — | FK → core_drillhole (CASCADE) |
| from_depth | FLOAT | NOT NULL | — | |
| to_depth | FLOAT | NOT NULL | — | |
| lithology | VARCHAR(128) | YES | — | |
| description | TEXT | YES | — | |
| mineralisation | VARCHAR(128) | YES | — | |
| hardness | VARCHAR(64) | YES | — | |
| weathering | VARCHAR(64) | YES | — | |
| acid_reaction | VARCHAR(64) | YES | — | |
| colour | VARCHAR(64) | YES | — | |
| oxidation | VARCHAR(64) | YES | — | |
| mineralisation_b | VARCHAR(128) | YES | — | second mineralisation column |
| mineralisation_2 | VARCHAR(128) | YES | — | |
| alteration | VARCHAR(128) | YES | — | |
| alteration_2 | VARCHAR(128) | YES | — | |
| veins | VARCHAR(128) | YES | — | |
| recovery_pct | VARCHAR(32) | YES | — | |
| core_size | VARCHAR(32) | YES | — | |

**Ordering:** drillhole, from_depth

---

### `core_assayresult`
Geochemical assay results per interval for a drillhole.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| drillhole_id | UUID | NOT NULL | — | FK → core_drillhole (CASCADE) |
| from_depth | FLOAT | NOT NULL | — | |
| to_depth | FLOAT | NOT NULL | — | |
| lab_batch_number | VARCHAR(64) | YES | — | |
| sample_number | VARCHAR(64) | YES | — | |
| comment | VARCHAR(256) | YES | — | |
| au_ppm | FLOAT | YES | — | gold (ppm) |
| au_ppm_check1 | FLOAT | YES | — | |
| au_ppm_check2 | FLOAT | YES | — | |
| cu_ppm | FLOAT | YES | — | copper (ppm) |
| pb_ppm | FLOAT | YES | — | lead (ppm) |
| zn_ppm | FLOAT | YES | — | zinc (ppm) |
| ag_ppm | FLOAT | YES | — | silver (ppm) |
| as_ppm | FLOAT | YES | — | arsenic (ppm) |
| bi_ppm | FLOAT | YES | — | bismuth (ppm) |
| cd_ppm | FLOAT | YES | — | cadmium (ppm) |
| sb_ppm | FLOAT | YES | — | antimony (ppm) |
| mn_ppm | FLOAT | YES | — | manganese (ppm) |
| mo_ppm | FLOAT | YES | — | molybdenum (ppm) |
| pt_ppb | FLOAT | YES | — | platinum (ppb) |
| pd_ppb | FLOAT | YES | — | palladium (ppb) |
| laboratory | VARCHAR(64) | YES | — | |
| au_method ... pd_method | VARCHAR(32) each | YES | — | analytical method per element |

**Ordering:** drillhole, from_depth

---

### `core_document`
An uploaded document file (PDF or DOCX). Supports versioning, full-text search, and MinIO storage.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| title | VARCHAR(64) | NOT NULL | — | |
| file | FILE (MinIO key) | NOT NULL | — | stored via django-storages |
| extracted_text | TEXT | NOT NULL | "" | from pdfplumber/python-docx |
| analysis_text | TEXT | NOT NULL | "" | AI-generated analysis |
| organisation_id | UUID | YES | — | FK → core_organisation (CASCADE) |
| process_id | UUID | YES | — | FK → core_process (SET_NULL) |
| tags | INTEGER[] | NOT NULL | [] | tag IDs from tagging.py |
| timestamp | DATE | YES | — | document date |
| doc_type | VARCHAR(64) | YES | — | |
| confidentiality | VARCHAR(64) | NOT NULL | "internal" | public/internal/confidential/jorc_restricted |
| created_by_id | INT | YES | — | FK → auth_user (PROTECT) |
| checksum_sha256 | VARCHAR(64) | YES | — | SHA-256 of file; used for deduplication |
| search_tsv | TSVECTOR | YES | — | populated by DB trigger for full-text search |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |
| version_number | INT | NOT NULL | 1 | |
| parent_document_id | UUID | YES | — | FK → core_document (SET_NULL); self-referential |
| is_latest | BOOLEAN | NOT NULL | True | indexed; always filter by this for current docs |
| tenement_id | UUID | YES | — | FK → core_tenement (SET_NULL) |
| commodity | VARCHAR(64) | YES | — | |
| reporting_stage | VARCHAR(32) | YES | — | EARLY_EXPLORATION / RESOURCE_DEFINITION / etc. |
| author_name | VARCHAR(128) | YES | — | free-text, for imported/legacy docs |

**Indexes:** checksum_sha256 (db_index), is_latest (db_index)
**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (SET_NULL), created_by_id → auth_user.id (PROTECT), parent_document_id → core_document.id (SET_NULL), tenement_id → core_tenement.id (SET_NULL)

---

### `core_documentchunk`
Text chunks of a document for RAG retrieval. 500-word chunks with 50-word overlap.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK (not UUID) |
| document_id | UUID | NOT NULL | — | FK → core_document (CASCADE) |
| chunk_index | INT (unsigned) | NOT NULL | — | position within document |
| text | TEXT | NOT NULL | — | chunk content |
| process_id | UUID | YES | — | FK → core_process (SET_NULL); copied from doc for fast filter |
| doc_type | VARCHAR(64) | YES | — | copied from doc |
| timestamp | DATE | YES | — | copied from doc |

**Indexes:** process (core_docume_process_f5b3f3_idx), doc_type (core_docume_doc_typ_499972_idx), timestamp (core_docume_timesta_294cd6_idx)
**Ordering:** document, chunk_index
**Relations:** document_id → core_document.id (CASCADE), process_id → core_process.id (SET_NULL)

---

### `user_profiles`
Extended user attributes for RBAC/ABAC governance. Auto-created via Django signal on User creation.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK |
| user_id | INT | NOT NULL | — | OneToOne → auth_user (CASCADE) |
| organisation_id | UUID | YES | — | FK → core_organisation (CASCADE) |
| role | VARCHAR(32) | NOT NULL | VIEWER | see RoleChoices |
| clearance_level | VARCHAR(32) | NOT NULL | INTERNAL | PUBLIC/INTERNAL/CONFIDENTIAL/JORC_APPROVED |
| department | VARCHAR(64) | YES | "" | |
| phone | VARCHAR(32) | YES | "" | |
| employee_id | VARCHAR(32) | YES (unique) | NULL | |
| can_approve_jorc | BOOLEAN | NOT NULL | False | JORC workflow approval permission |
| can_approve_valmin | BOOLEAN | NOT NULL | False | VALMIN workflow approval permission |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Relations:** user_id → auth_user.id (CASCADE, OneToOne), organisation_id → core_organisation.id (CASCADE)

---

### `saved_reports`
AI-generated project reports with version history and approval workflow linkage.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| process_id | UUID | YES | — | FK → core_process (SET_NULL) |
| prospect_id | UUID | YES | — | FK → core_prospect (SET_NULL) |
| organisation_id | UUID | YES | — | FK → core_organisation (SET_NULL) |
| title | VARCHAR(256) | NOT NULL | — | |
| content_md | TEXT | NOT NULL | — | Markdown report content |
| search_tsv | TSVECTOR | YES | — | populated by DB trigger; title (A) + content_md (B); GIN index |
| clearance_level | VARCHAR(32) | NOT NULL | INTERNAL | |
| created_by_id | INT | YES | — | FK → auth_user (SET_NULL) |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |
| version_number | INT | NOT NULL | 1 | |
| content_hash | VARCHAR(64) | YES | "" | SHA-256 of content_md; prevents duplicate saves |
| change_reason | VARCHAR(16) | NOT NULL | GENERATED | GENERATED/MANUAL_EDIT/REGENERATED |
| change_summary | TEXT | YES | "" | |
| parent_version_id | UUID | YES | — | FK → saved_reports.id (SET_NULL); self-referential |
| status | VARCHAR(16) | NOT NULL | DRAFT | DRAFT/UNDER_REVIEW/APPROVED/PUBLISHED |
| approval_workflow_id | INT | YES | — | FK → approval_workflows.id (SET_NULL); OneToOne |

**Ordering:** -created_at
**Relations:** approval_workflow_id → approval_workflows.id (OneToOne, SET_NULL)
**M2M:** source_documents → core_document (via `cited_in_reports`)

---

### `audit_logs`
Immutable audit trail for all user actions (JORC/VALMIN compliance).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK |
| user_id | INT | YES | — | FK → auth_user (SET_NULL) |
| action | VARCHAR(16) | NOT NULL | — | CREATE/VIEW/EDIT/APPROVE/REJECT/DELETE/DOWNLOAD |
| content_type_id | INT | NOT NULL | — | FK → django_content_type (CASCADE) |
| object_id | UUID | NOT NULL | — | UUID of the audited object |
| description | TEXT | YES | "" | |
| ip_address | INET | YES | — | |
| user_agent | TEXT | YES | "" | truncated to 500 chars |
| timestamp | TIMESTAMPTZ | NOT NULL | now() | |

**Indexes:** (content_type, object_id) — audit_logs_content_b0ef47_idx; (user, action) — audit_logs_user_id_d685f3_idx; timestamp — audit_logs_timesta_423be6_idx
**Ordering:** -timestamp

---

### `approval_workflows`
JORC/VALMIN/General approval request records. Generic FK allows attaching to any model.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK |
| content_type_id | INT | NOT NULL | — | FK → django_content_type |
| object_id | UUID | NOT NULL | — | UUID of the item under review |
| workflow_type | VARCHAR(16) | NOT NULL | — | JORC/VALMIN/GENERAL |
| status | VARCHAR(16) | NOT NULL | PENDING | PENDING/APPROVED/REJECTED/REVISION |
| submitted_by_id | INT | NOT NULL | — | FK → auth_user (CASCADE) |
| approved_by_id | INT | YES | — | FK → auth_user (SET_NULL) |
| submission_notes | TEXT | YES | "" | |
| approval_notes | TEXT | YES | "" | |
| submitted_at | TIMESTAMPTZ | NOT NULL | now() | |
| reviewed_at | TIMESTAMPTZ | YES | — | |

**Ordering:** -submitted_at

---

### `document_views`
Tracks every time a user views a document (separate from the audit log, for analytics).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK |
| user_id | INT | NOT NULL | — | FK → auth_user (CASCADE) |
| document_id | UUID | NOT NULL | — | FK → core_document (CASCADE) |
| viewed_at | TIMESTAMPTZ | NOT NULL | now() | |
| ip_address | INET | YES | — | |

**Indexes:** (document, user) — document_vi_documen_dcb332_idx; viewed_at — document_vi_viewed__659188_idx
**Ordering:** -viewed_at

---

### `doc_links`
Generic document-to-entity attachment (Confluence-style traceability). Unique per (document, entity).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | BIGINT | NOT NULL | auto | PK |
| document_id | UUID | NOT NULL | — | FK → core_document (CASCADE) |
| content_type_id | INT | NOT NULL | — | FK → django_content_type |
| object_id | UUID | NOT NULL | — | UUID of the linked entity |
| created_by_id | INT | YES | — | FK → auth_user (SET_NULL) |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |

**Indexes:** (content_type, object_id) — doc_links_ct_obj_idx; document — doc_links_document_idx
**Constraints:** unique_doc_link UNIQUE (document, content_type, object_id)

---

## Enums and custom types

All choice fields are implemented as Django TextChoices (VARCHAR columns with CHECK constraints or model-level validation):

- **Organisation.mode**: `EXPLORATION`, `MINING`
- **Process.mode**: `PROJECT`, `OPERATION`
- **Drillhole.drill_type**: `RC`, `DDH`, `RAB`, `AC`
- **Document.confidentiality**: `public`, `internal`, `confidential`, `jorc_restricted` (lowercase strings)
- **Document.reporting_stage**: `EARLY_EXPLORATION`, `RESOURCE_DEFINITION`, `FEASIBILITY`, `DEVELOPMENT`, `REHABILITATION`
- **Document.tags**: `INTEGER[]` array using tag IDs defined in `core/tagging.py` (10=Exploration Report, 11=Drill Logs, 12=Assay Results, 13=Tenement Docs, 14=Environment, 15=Finance/Commercial)
- **UserProfile.role**: `GEOLOGIST_EXPL`, `FIELD_LEAD`, `DATA_MANAGER`, `GEOLOGIST_MINE`, `METALLURGIST`, `OPS_MANAGER`, `ADMIN`, `VIEWER`, `COMPETENT_PERSON`
- **UserProfile.clearance_level**: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `JORC_APPROVED`
- **SavedReport.change_reason**: `GENERATED`, `MANUAL_EDIT`, `REGENERATED`
- **SavedReport.status**: `DRAFT`, `UNDER_REVIEW`, `APPROVED`, `PUBLISHED`
- **ApprovalWorkflow.workflow_type**: `JORC`, `VALMIN`, `GENERAL`
- **ApprovalWorkflow.status**: `PENDING`, `APPROVED`, `REJECTED`, `REVISION`
- **AuditLog.action**: `CREATE`, `VIEW`, `EDIT`, `APPROVE`, `REJECT`, `DELETE`, `DOWNLOAD`

### `core_sample`
Field or drillhole sample (rock chip, RC chip, core plug, stream sediment, etc.) belonging to a project and optionally a prospect.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | NOT NULL | — | |
| organisation_id | UUID | NOT NULL | — | FK → core_organisation |
| process_id | UUID | NOT NULL | — | FK → core_process |
| prospect_id | UUID | YES | — | FK → core_prospect (SET_NULL); related_name="samples" |
| sample_type | VARCHAR(16) | NOT NULL | ROCK | ROCK/RC_CHIP/CORE/STREAM_SED/SOIL/OTHER |
| sample_number | VARCHAR(64) | YES | — | lab or field sample number |
| depth | FLOAT | YES | — | depth in metres (for drillhole samples) |
| description | TEXT | YES | — | |
| collected_by | VARCHAR(128) | YES | — | geologist or contractor name |
| collected_at | DATE | YES | — | collection date |
| laboratory | VARCHAR(128) | YES | — | assay laboratory name |
| location | POINT (SRID 4326) | YES | — | GPS location of sample |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Ordering:** -created_at
**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (CASCADE), prospect_id → core_prospect.id (SET_NULL)

---

### `core_survey`
Geophysical or geological survey (e.g. magnetics, CSAMT, soil grid, mapping programme).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | UUID | NOT NULL | uuid4 | PK |
| name | VARCHAR(64) | NOT NULL | — | |
| organisation_id | UUID | NOT NULL | — | FK → core_organisation |
| process_id | UUID | NOT NULL | — | FK → core_process |
| prospect_id | UUID | YES | — | FK → core_prospect (SET_NULL); related_name="surveys" |
| survey_type | VARCHAR(16) | NOT NULL | GEOPHYSICS | GEOPHYSICS/SOIL_GRID/MAPPING/REMOTE |
| contractor | VARCHAR(128) | YES | — | survey contractor name |
| date_from | DATE | YES | — | survey start date |
| date_to | DATE | YES | — | survey end date |
| description | TEXT | YES | — | |
| geom | POLYGON (SRID 4326) | YES | — | optional coverage area drawn on map |
| created_at | TIMESTAMPTZ | NOT NULL | now() | |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | |

**Ordering:** -created_at
**Relations:** organisation_id → core_organisation.id (CASCADE), process_id → core_process.id (CASCADE), prospect_id → core_prospect.id (SET_NULL)

---

## Migration notes

- Migrations live in `core/migrations/`. Currently 23 numbered migrations (0001–0023) plus one merge migration (0015).
- Run: `python manage.py migrate` (or inside Docker: `docker compose exec web python manage.py migrate`)
- There is a database trigger on `core_document` that populates `search_tsv` (added in migration `0012_document_search_tsv`/`0014_document_search_tsv` after a merge resolution in `0015`).
- Drillhole Excel import available via `python manage.py import_drillhole_excel`.

## Soft deletes / audit fields

- No soft-delete pattern — records are hard-deleted. `Document.delete()` is overridden to also delete the MinIO file.
- All domain models have `created_at` (auto_now_add) and `updated_at` (auto_now) timestamps.
- `AuditLog` and `DocumentView` provide audit history (immutable append-only records, not soft deletes).
- Document versioning uses `is_latest` flag + `parent_document` FK chain; old versions are retained.
- SavedReport versioning uses `parent_version` FK + `version_number`; old versions are retained.
