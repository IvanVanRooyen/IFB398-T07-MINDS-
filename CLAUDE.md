# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Orefox KMS** is a Knowledge Management System proof-of-concept for the mining & exploration industry. It centralizes documents (PDFs of exploration reports) and geospatial datasets (projects, tenements, drillholes, prospects) with a web interface powered by geospatial intelligence and AI-generated project reports.

**Stack:**
- Django 5.x + GeoDjango for geospatial ORM
- PostgreSQL + PostGIS for spatial queries
- MinIO for S3-compatible object storage
- HTMX for lightweight frontend interactivity
- Tailwind CSS (via CDN, no build step)
- Ollama + Granite 3.2 LLM for AI report generation
- Docker Compose for orchestration

## Development Commands

### Running the Application

```bash
# Start all services (database, MinIO, web app)
docker compose up --build

# Start in detached mode
docker compose up -d

# View logs
docker compose logs -f web
docker compose logs -f db
```

### Database Operations

```bash
# Create migrations after model changes
docker compose run --rm web bash -lc "python manage.py makemigrations"

# Apply migrations
docker compose run --rm web bash -lc "python manage.py migrate"

# Both in one command
docker compose run --rm web bash -lc "python manage.py makemigrations && python manage.py migrate"

# Create superuser for admin access
docker compose exec web bash -lc "python manage.py createsuperuser"

# Access database shell
docker compose exec db psql -U postgres -d orefox

# Seed database with test data
python seed-db.py  # Note: requires local psycopg2 or run via nix-shell
```

### Container Management

```bash
# Rebuild web container after Dockerfile/requirements changes
docker compose build --no-cache web

# Execute Django management commands
docker compose exec web bash -lc "python manage.py <command>"

# Shell access to web container
docker compose exec web bash
```

### Running Tests

```bash
# Run Django tests
docker compose exec web bash -lc "python manage.py test"

# Run specific test module
docker compose exec web bash -lc "python manage.py test core.tests.test_models"
```

## Architecture & Code Structure

### Core Domain Models

The system is built around a hierarchical domain model (defined in `core/models.py`):

1. **Organisation** - Top-level entity (exploration vs mining company)
   - Has a mode: EXPLORATION or MINING
   - Parent to all other entities

2. **Process** - Projects or Operations under an Organisation
   - Stores geospatial boundaries (`geom` MultiPolygonField)
   - Contains commodity information
   - Note: May be renamed to "Campaign" or "Activity" (see TODO in models.py:84)

3. **Prospect, Tenement, Drillhole** - Domain-specific entities
   - All link to Organisation and Process
   - Currently basic structures, ready for expansion

4. **Document** - File storage with metadata
   - Stores PDFs and files in MinIO via S3 API
   - SHA-256 checksums prevent duplicates (see `core/views.py:121`)
   - Links to Organisation and optionally Process
   - Uses ArrayField for tags (PostgreSQL-specific)

### Key Design Patterns

**Model Validation Mixins** (`core/models.py:11-48`):
- `ChoiceValidationMixin` - Automatic validation of choice fields
- `AutoCleanMixin` - Runs `full_clean()` before save
- `ValidatedChoiceModel` - Combines both for robust choice field handling

**File Upload & Deduplication** (`core/views.py:110-148`):
- `upload_doc()` view computes SHA-256 before saving
- Checks for existing documents with same checksum
- Uses `core/utils.py:sha256_file()` utility

**Dynamic Model Loading** (`core/views.py:31-45`):
- Views use `_get_model()` helper to safely handle missing models
- Allows templates to work even when domain models aren't fully implemented
- Example: prospects, drillholes, tenements views

### AI Report Generation System

Located in `core/ai/`, this module generates automated project reports using LLMs:

**Components:**
- `granite_client.py` - Backend-agnostic LLM client
  - Supports Ollama (default) and Hugging Face Inference API
  - Configured via environment variables (GRANITE_BACKEND, OLLAMA_URL, GRANITE_MODEL)
  - Default model: granite3.2:8b-instruct-fp16

- `report_service.py` - Report generation orchestration
  - `fetch_process_bundle()` - Gathers Process and related Documents from DB
  - `build_structured_context()` - Converts DB records to LLM-friendly format
  - `build_prompt()` - Creates structured prompt with section outline
  - `generate_project_report()` - Main entry point, returns Markdown report
  - Graceful fallback when LLM is unavailable

**Usage:**
- Endpoint: `/ai/report/<process_id>/` (see `core/views.py:254`)
- Returns HTML-wrapped Markdown by default
- Add `?format=json` for JSON response

**Environment Configuration:**
```bash
GRANITE_BACKEND=ollama          # or "hf"
OLLAMA_URL=http://localhost:11434
GRANITE_MODEL=granite3.2:8b-instruct-fp16
GRANITE_TIMEOUT=120
```

For Hugging Face:
```bash
GRANITE_BACKEND=hf
HF_INFERENCE_URL=https://api-inference.huggingface.co/models/ibm-granite/...
HF_TOKEN=your_token_here
```

### GeoDjango & Spatial Data

- Database engine: `django.contrib.gis.db.backends.postgis` (config/settings.py:57)
- Spatial fields use SRID 4326 (WGS84)
- Process model has `MultiPolygonField` for area boundaries
- Admin interface includes map widget for drawing/editing polygons (core/admin.py)

### MinIO/S3 Storage

Configuration in `config/settings.py:69-75`:
- Uses `django-storages` with S3Boto3Storage backend
- Endpoint: MinIO service in Docker (http://minio:9000)
- Credentials from environment variables
- Files uploaded to configurable bucket (default: "documents")

### Templates & Frontend

**Structure:**
- Base layout: `templates/base.html`
- App templates: `templates/core/` (dashboard, upload, documents, etc.)
- HTMX integration via `django-htmx` middleware
- Tailwind loaded from Play CDN - no build pipeline required

**URL Routing:**
- Project URLs: `config/urls.py` (admin + core app includes)
- Core app URLs: `core/urls.py` (dashboard, upload, domain pages, AI endpoints)

### Environment Configuration

All configuration via `.env` file:
- Database credentials (POSTGRES_*, DB_*)
- MinIO credentials (MINIO_*)
- Django settings (SECRET_KEY, DJANGO_DEBUG)
- AI/LLM settings (GRANITE_*, OLLAMA_*, HF_*)
- **Never commit secrets or use hardcoded values**

## Important Notes

1. **Migrations**: Always create and commit migrations after model changes. Run `makemigrations` before pushing.

2. **GeoDjango Requirements**: This uses PostGIS spatial extensions. Standard PostgreSQL won't work.

3. **Container-Based Development**: No local Python environment needed. All commands run through Docker.

4. **File Storage**: Documents are stored in MinIO (object storage), not the database. Database only holds metadata and file references.

5. **SHA-256 Deduplication**: The upload view prevents duplicate documents by comparing checksums. This happens at upload time in `core/views.py:124-139`.

6. **Model Naming**: The `Process` model may be renamed to `Campaign` or `Activity` in future iterations (see comment in `core/models.py:84`).

7. **UUID Primary Keys**: All domain models use UUID primary keys for better distributed system compatibility.

8. **AI Report Generation**: Requires Ollama running locally or a valid HuggingFace API endpoint. The system gracefully degrades if the LLM is unavailable, returning a minimal fallback report.

9. **LLM Context Window**: Report generation fetches up to 50 documents per process to stay within typical context limits (see `core/ai/report_service.py:28`).

## Services & Ports

- **Web App**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin
- **MinIO Console**: http://localhost:9001
- **PostgreSQL**: localhost:5432
- **Ollama** (external): http://localhost:11434 (if using local Ollama)

## Common Workflows

### Adding a New Model

1. Define model in `core/models.py`
2. Consider using `ValidatedChoiceModel` base for choice fields
3. Add timestamp fields (`created_at`, `updated_at`)
4. Run: `docker compose run --rm web bash -lc "python manage.py makemigrations"`
5. Apply: `docker compose run --rm web bash -lc "python manage.py migrate"`
6. Register in `core/admin.py` if admin access needed
7. Add views/templates/URLs as needed

### Adding Geospatial Fields

1. Use `models.PointField`, `models.PolygonField`, or `models.MultiPolygonField`
2. Always specify `srid=4326` for consistency
3. GeoDjango admin provides map widgets automatically
4. Use spatial queries via ORM (e.g., `.filter(geom__distance_lt=...)`)

### Modifying File Upload Logic

File upload handling is in `core/views.py:upload_doc()`. Key touchpoints:
- Form validation: `core/forms.py:DocumentForm`
- SHA-256 calculation: `core/utils.py:sha256_file()`
- Storage backend: configured in `config/settings.py:70`

### Extending AI Report Generation

To modify report structure or add new data sources:
1. Update `fetch_process_bundle()` in `core/ai/report_service.py` to include additional models
2. Modify `build_structured_context()` to format new data for LLM
3. Adjust `REPORT_SYSTEM_INSTRUCTIONS` or `build_prompt()` to change report structure
4. Test with different LLM backends by changing `GRANITE_BACKEND` environment variable

### Working with Ollama

To use local Ollama for development:
```bash
# Install Ollama (outside Docker)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the Granite model
ollama pull granite3.2:8b-instruct-fp16

# Verify it's running
curl http://localhost:11434/api/tags
```

Then set in `.env`:
```bash
GRANITE_BACKEND=ollama
OLLAMA_URL=http://host.docker.internal:11434  # Use host.docker.internal from Docker
GRANITE_MODEL=granite3.2:8b-instruct-fp16
```
