# Architecture

## What this application does

Orefox KMS (Knowledge Management System) is a web application for mining and mineral exploration companies. It manages project/campaign data, geospatial assets (tenements, prospects, drillholes), uploaded documents (PDFs, DOCX), and AI-generated project reports. It enforces JORC/VALMIN governance compliance via role-based access control, clearance levels, approval workflows, and a full audit trail. Users can view spatial data on an interactive Leaflet map and ask IBM Granite (LLM) to generate structured Markdown reports from their document corpus using RAG retrieval.

## System overview

```
Browser (Tailwind CSS + HTMX)
  │
  └─▶ Django 5.x (port 8000)
        │  function-based views, GeoDjango, @login_required + RBAC/ABAC decorators
        │
        ├─▶ PostgreSQL 16 + PostGIS 3.4 (port 5432)
        │     spatial types: POINT, MULTIPOLYGON (SRID 4326)
        │     full-text search: SearchVectorField + DB trigger
        │
        ├─▶ Redis 7 (port 6379)
        │     cache: GeoJSON API responses, per-org doc lists, LLM report cache (24h TTL)
        │
        ├─▶ MinIO (port 9000 / console 9001)
        │     S3-compatible object storage for uploaded document files
        │     accessed via django-storages S3Boto3Storage backend
        │
        └─▶ IBM Granite LLM (via Ollama or HuggingFace Inference)
              Ollama: http://host.docker.internal:11434 (local, default)
              HuggingFace: HF_INFERENCE_URL (cloud)
              selected by GRANITE_BACKEND env var

Observability stack (all in Docker Compose, not production-facing):
  Grafana Alloy (OTEL collector, port 4317/4318) → Tempo (traces) + Loki (logs) + Prometheus (metrics)
  Grafana dashboard (port 3000)
  Exporters: redis-exporter (9121), postgres-exporter (9187), ollama-exporter (9110)
```

## Services and components

| Component | Purpose | Location / hosting |
|-----------|---------|-------------------|
| Django web app | All views, business logic, API, forms | `infra/web/Dockerfile`, port 8000 |
| PostgreSQL 16 + PostGIS 3.4 | Primary relational + geospatial DB | Docker: `postgis/postgis:16-3.4`, port 5432 |
| Redis 7 | Cache (GeoJSON, document lists, LLM reports) | Docker: `redis:alpine`, port 6379 |
| MinIO | S3-compatible file storage for uploaded documents | Docker: `minio/minio:latest`, ports 9000/9001 |
| IBM Granite LLM (Ollama) | Local LLM for AI report generation | Host machine (Ollama), default `http://host.docker.internal:11434` |
| IBM Granite LLM (HuggingFace) | Cloud fallback for LLM | `HF_INFERENCE_URL` env var |
| Grafana Alloy | OTEL collector — routes traces/logs/metrics | Docker, ports 4317, 4318, 12345 |
| Grafana Tempo | Distributed tracing backend | Docker, port 3200 |
| Grafana Loki | Log aggregation | Docker, port 3100 |
| Prometheus | Metrics collection | Docker |
| Grafana | Dashboard UI for telemetry | Docker, port 3000 |
| redis-exporter | Prometheus exporter for Redis | Docker, port 9121 |
| postgres-exporter | Prometheus exporter for PostgreSQL | Docker, port 9187 |
| ollama-exporter | Prometheus exporter for Ollama | Docker, port 9110 |

## Key third-party integrations

| Service | Purpose | Notes |
|---------|---------|-------|
| IBM Granite (Ollama) | AI report generation + document analysis | `GRANITE_BACKEND=ollama`, model set by `GRANITE_MODEL` |
| IBM Granite (HuggingFace) | Cloud LLM fallback | `GRANITE_BACKEND=hf`, needs `HF_TOKEN` and `HF_INFERENCE_URL` |
| MinIO | Document file storage (S3-compatible) | `django-storages` S3Boto3Storage backend |
| pdfplumber | PDF text extraction for RAG | Used in `core/utils.py:extract_text()` |
| python-docx | DOCX text extraction + report export | Used in `core/utils.py` and views for DOCX export |
| reportlab | PDF report export | Used in views for PDF download |
| Leaflet.js | Interactive map for spatial data | Served from CDN in templates |
| Grafana stack | Observability (traces, logs, metrics) | OTEL instrumentation in `core/instrument.py` and `core/telemetry.py` |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | Debug mode toggle (default: True) |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL user |
| `DB_PASS` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port |
| `REDIS_URL` | Redis connection string (default: `redis://redis:6379/0`) |
| `MINIO_ROOT_USER` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | MinIO secret key |
| `MINIO_BUCKET` | MinIO bucket name for documents |
| `MINIO_ENDPOINT` | MinIO internal endpoint (e.g. `minio:9000`) |
| `MINIO_EXTERNAL_ENDPOINT` | MinIO public endpoint for file URLs (default: `localhost:9000`) |
| `MINIO_USE_SSL` | Use SSL for MinIO (default: False) |
| `GRANITE_BACKEND` | LLM backend: `ollama` (default) or `hf` |
| `GRANITE_MODEL` | Ollama model name (default: `granite3.2:8b-instruct-fp16`) |
| `GRANITE_TIMEOUT` | LLM request timeout in seconds (default: 120) |
| `OLLAMA_URL` | Ollama API base URL (default: `http://localhost:11434`) |
| `HF_INFERENCE_URL` | HuggingFace Inference API URL (only needed when `GRANITE_BACKEND=hf`) |
| `HF_TOKEN` | HuggingFace API token |
| `POSTGRES_DB` | Used in Docker Compose for DB container |
| `POSTGRES_USER` | Used in Docker Compose for DB container |
| `POSTGRES_PASSWORD` | Used in Docker Compose for DB container |
| `GF_PG_READER_USER` | Grafana read-only Postgres user (default: `grafana`) |
| `GF_PG_READER_PASS` | Grafana read-only Postgres password (default: `grafana`) |
| `OLLAMA_HOST` | Ollama host for the metrics exporter (default: `host.docker.internal:11434`) |

## Infrastructure and deployment

- **Local development**: `docker compose up --build` — starts all services. App auto-migrates on container start.
- **Build**: Custom Dockerfile at `infra/web/Dockerfile`. App volume-mounted from `.:/app` in dev.
- **No CI/CD pipeline** was found in the repository at time of init.
- **Observability**: Grafana Alloy configured at `infra/telemetry/config/config.alloy`, receives OTEL traces/logs from Django. Tempo stores traces in MinIO (`tempo` bucket). Loki stores logs on local volume.
- **Database migrations**: Managed by Django's migration system. Run with `python manage.py migrate` (auto-runs on container start).

## Notable constraints or context

- All geospatial data uses SRID 4326 (WGS84). PostGIS is required — standard PostgreSQL will not work.
- Documents are stored in MinIO, not on disk. The `Document.file` field is an S3-style key; deletion from MinIO is handled in `Document.delete()`.
- The app is a university capstone project (IFB398/IFB399, QUT) being developed to a production-like standard.
- JORC (Joint Ore Reserves Committee) and VALMIN compliance are first-class requirements — approval workflows, audit logging, and clearance levels all exist specifically to satisfy these standards.
- Redis cache TTL for LLM-generated reports is 24 hours; cache key includes process ID, user clearance level, and latest document timestamp (auto-invalidates when a new document is uploaded to the project).
