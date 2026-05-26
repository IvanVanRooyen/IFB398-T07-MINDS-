# Orefox KMS — Knowledge Management System

**IFB399 Capstone Project — Team T07**

A web-based Knowledge Management System built for the mining and exploration industry. It provides a centralised platform for managing documents, geospatial datasets, drillhole data, and AI-generated reports.

---

## Features

| Feature | Description | -
|---|---|
| Document Management | Upload, search, version, and delete PDFs/DOCX files with SHA-256 deduplication |
| Full-Text Search | PostgreSQL `tsvector` search across documents and saved reports |
| Geospatial Data | Prospects, tenements, drillholes stored with WGS84 geometry (PostGIS) |
| AI Reports | Granite LLM generates project summaries from document context via RAG |
| Role-Based Access | Nine roles (Geologist, Field Lead, Admin, etc.) with clearance levels |
| Audit Trail | Every create/view/edit/delete action is logged for compliance |
| Drillhole Import | Bulk import from Excel with collar, survey, lithology, and assay data |
| Approval Workflows | JORC/VALMIN approval chains on documents and reports |
| Observability | Grafana dashboards backed by Prometheus, Loki, and Tempo |

---

## Technology Stack

**Backend**
- [Django 5.x](https://www.djangoproject.com/) — web framework, ORM, auth
- [GeoDjango](https://docs.djangoproject.com/en/stable/ref/contrib/gis/) — geospatial model fields and queries
- [PostgreSQL 16 + PostGIS 3.4](https://postgis.net/) — relational database with spatial extensions
- [Redis](https://redis.io/) — caching for document lists and AI report results
- [MinIO](https://min.io/) — S3-compatible object storage for uploaded files

**AI**
- [IBM Granite](https://www.ibm.com/granite) via [Ollama](https://ollama.com/) — local LLM for report generation
- RAG (Retrieval-Augmented Generation) over `DocumentChunk` records

**Frontend**
- [HTMX](https://htmx.org/) — dynamic page updates without a JavaScript framework
- [Tailwind CSS](https://tailwindcss.com/) — utility-first CSS loaded via CDN (no build step)
- [Leaflet.js](https://leafletjs.com/) — interactive maps for prospects and tenements

**Infrastructure**
- [Docker + Docker Compose](https://docs.docker.com/compose/) — containerised development environment
- [Grafana Alloy](https://grafana.com/oss/alloy/) — OpenTelemetry collector
- [Grafana](https://grafana.com/), [Prometheus](https://prometheus.io/), [Loki](https://grafana.com/oss/loki/), [Tempo](https://grafana.com/oss/tempo/) — metrics, logs, traces

---

## Project Structure

```
IFB398-T07-MINDS/
├── config/                     # Django project configuration
│   ├── settings.py             # Database, storage, middleware, caching
│   ├── urls.py                 # Root URL routing
│   └── wsgi.py / asgi.py       # Server entry points
│
├── core/                       # Main Django application
│   ├── models.py               # All database models
│   ├── views.py                # Request handlers and business logic
│   ├── urls.py                 # App-level URL routing
│   ├── forms.py                # Django forms
│   ├── utils.py                # SHA-256 hashing, text extraction, chunking
│   ├── permissions.py          # Role and clearance decorators
│   ├── tagging.py              # Document tag definitions
│   ├── instrument.py           # OpenTelemetry tracing decorator
│   ├── importers.py            # Drillhole Excel import logic
│   ├── ai/
│   │   ├── granite_client.py   # Ollama/HuggingFace LLM client
│   │   ├── report_service.py   # Report generation orchestration
│   │   └── retrieval.py        # RAG chunk retrieval
│   ├── migrations/             # Database migration history
│   ├── management/commands/    # Custom manage.py commands
│   └── tests/                  # Unit and integration tests
│
├── templates/                  # HTML templates (Jinja-style Django)
│   ├── base.html               # Shared layout with sidebar
│   └── core/                   # Per-feature page templates
│
├── infra/
│   ├── web/                    # Django Dockerfile and requirements
│   └── telemetry/              # Grafana, Prometheus, Loki, Tempo config
│
├── fixtures/                   # Seed data and sample documents
├── static/                     # Static assets (logo, favicon)
├── docker-compose.yml          # Full multi-container stack
├── pyproject.toml              # Python project metadata and dependencies
└── .env                        # Environment variables 
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Ollama](https://ollama.com/) installed locally (for AI report generation)

### 1. Clone the repository

```bash
git clone <repo-url>
cd IFB398-T07-MINDS-
```

### 2. Pull the Granite model

```bash
ollama pull granite4:350m
```

### 3. Create your `.env` file

Copy the example below and fill in values (see [Environment Variables](#environment-variables)):

```bash
cp .env.example .env   # or create .env manually
```

### 4. Start the full stack

```bash
docker compose up --build
```

This will start PostgreSQL, Redis, MinIO, and the Django web server. Migrations run automatically on startup.

The application will be available at **http://localhost:8000**.

---

## Environment Variables

Create a `.env` file in the project root with the following:

```env
# Django
SECRET_KEY=your-long-random-secret-key-here
DJANGO_DEBUG=1

# PostgreSQL
POSTGRES_DB=orefox
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DB_NAME=orefox
DB_USER=postgres
DB_PASS=postgres
DB_HOST=db
DB_PORT=5432

# MinIO (object storage)
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio12345
MINIO_BUCKET=documents
MINIO_ENDPOINT=minio:9000
MINIO_EXTERNAL_ENDPOINT=localhost:9000
MINIO_USE_SSL=0

# Redis
REDIS_URL=redis://redis:6379/0

# Granite AI (Ollama)
GRANITE_BACKEND=ollama
GRANITE_MODEL=granite4:350m
OLLAMA_URL=http://host.docker.internal:11434

# Grafana DB reader (used by migration 0011 to create a read-only PG user)
GF_PG_READER_USER=grafana
GF_PG_READER_PASS=grafana
```

---

## Running the Application

Once the stack is running with `docker compose up`, the services are available at:

| Service | URL |
|---|---|
| Django web app | http://localhost:8000 |
| Django admin | http://localhost:8000/admin |
| MinIO console | http://localhost:9001 |
| Grafana | http://localhost:3000 |

### Create a superuser

```bash
docker compose exec web python manage.py createsuperuser
```

---

## Loading Seed Data

To populate the database with sample organisations, projects, documents, and drillholes:

```bash
docker compose exec web python manage.py load_fixture_data
```

Sample PDF documents will be loaded from `fixtures/media/docs/` into MinIO automatically.

---

## Observability (Grafana Stack)

The `docker-compose.yml` includes a full observability stack:

- **Grafana** (`:3000`) — dashboards for all metrics and logs
- **Prometheus** (scrapes Django, Redis, Postgres, Ollama metrics)
- **Loki** — log aggregation
- **Tempo** — distributed tracing (OpenTelemetry)
- **Grafana Alloy** — OTEL collector routing data to the above

Django views and utility functions are instrumented with the `@instrument` decorator (`core/instrument.py`), which emits traces to Alloy on every request.


---

## Running Tests

```bash
docker compose exec web python manage.py test core
```

Tests live in `core/tests/` and cover models, permissions, views, search, and utilities.

