# MINDS Geospatial

An exploration and mining knowledge system that connects geological records, technical documents, spatial investigation and traceable reporting.

MINDS brings the evidence behind an exploration decision into one workflow: manage project data, investigate a prospect, inspect supporting records, prepare a report and review a fixed revision. Reports can combine authored narrative, optional evidence-scoped AI drafting, geological tables and a collar-location figure.

**Status:** active development. The current application has been verified with 592 automated tests and targeted browser/file-format checks. Fresh-install automation, continuous integration, broader interface work and production deployment remain in progress. There is no public demo release yet.

[Architecture](docs/ARCHITECTURE.md) · [Development setup](docs/DEVELOPMENT.md) · [Verification](docs/VERIFICATION.md) · [Roadmap](docs/ROADMAP.md)

## The workflow

1. **Organise evidence.** Maintain projects, prospects, documents and drillhole records within an organisation.
2. **Import and inspect.** Validate collar, survey, lithology and assay workbooks before writing; inspect locations and linked records on the map.
3. **Develop a prospect.** Connect an interpretation and investigation objective to its documents and drillholes.
4. **Prepare a report.** Start with a manual outline or request an AI-assisted draft from a bounded set of accessible evidence.
5. **Assemble geological evidence.** Capture collar, Au/Cu assay and lithology tables, with an optional collar-location figure.
6. **Review and export.** Save revisions, submit a fixed version for review and export its narrative and geological appendix to PDF or DOCX.

## Capabilities

| Area | Current implementation |
|---|---|
| Documents | PDF/DOCX text extraction, organisation-scoped access, checksums, version chains and private downloads |
| Geological data | Collar, survey, lithology and assay records; validated workbook imports with dry runs and atomic replacement |
| Geography | PostGIS geometry and MapLibre views for projects, tenements, prospects and drillholes |
| Search and drafting | PostgreSQL full-text retrieval, ranked document passages, explicit evidence selection and inspectable drafting inputs |
| Background work | Durable PostgreSQL report queue, progress stages, explicit retry, cancellation, interrupted-worker recovery and submission receipts |
| Report assembly | Manual outlines, editable narrative and versioned geological tables/figures captured from the selected project or prospect |
| Governance | Organisation/role/clearance checks, report revisions, review transitions and audit records |
| Export | Native DOCX tables and embedded figure; PDF tables and vector figure using the saved geological snapshot |
| Evaluation | Versioned synthetic retrieval/citation cases and an offline regression command |

JORC/VALMIN-labelled review routes support human review. They do not establish certification or regulatory compliance. Citation feedback checks labels and literal excerpt matches; it does not prove factual or semantic support.

## Architecture

```mermaid
flowchart LR
    Browser[Browser: Django templates, HTMX, MapLibre] --> Web[Django / GeoDjango]
    Web --> DB[(PostgreSQL / PostGIS)]
    Web --> Storage[(S3-compatible document storage)]
    Web --> Cache[(Redis cache)]
    Worker[Report worker] --> DB
    Worker --> Model[Optional Ollama / Granite]
```

PostgreSQL owns report-job claims and publication state. Model calls run outside database transactions. The worker checks source snapshots and current access before publishing a draft. Cancellation invalidates the attempt token so late responses cannot save a cancelled draft.

Manual drafting uses the same worker without a model call. Saved geological appendices retain their own values, record IDs, scope, capture time and digest. Later edits to live geological data do not silently alter a saved report.

## Technology

| Layer | Stack |
|---|---|
| Application | Python 3.11, Django 5.2, GeoDjango |
| Database | PostgreSQL 16, PostGIS 3.4 |
| Interface | Django templates, HTMX, Tailwind CSS, MapLibre GL JS, EasyMDE |
| Storage and cache | MinIO-compatible S3 storage, Redis |
| Drafting | IBM Granite through Ollama; optional Hugging Face adapter |
| Reports | ReportLab, python-docx, Pillow |
| Development | Docker Compose, Django test runner, Ruff |
| Optional telemetry | OpenTelemetry, Grafana, Prometheus, Loki, Tempo, Alloy |

The container's application dependency list is [infra/web/requirements.txt](infra/web/requirements.txt). The root `pyproject.toml` currently lists only a subset; dependency consolidation is planned.

## Local development

Prerequisites: Docker Engine/Desktop with Compose v2. Ollama and an installed model are optional for manual reports.

```bash
git clone https://github.com/IvanVanRooyen/IFB398-T07-MINDS-.git
cd IFB398-T07-MINDS-
cp .env.example .env
```

Replace the secret/password placeholders in `.env`. Keep the `POSTGRES_*` and corresponding `DB_*` settings aligned. Then start the application services and their dependencies:

```bash
docker compose up --build web report-worker
```

The current development definition exposes the web app at `http://localhost:8000`. Migrations run in the web startup command; the worker waits for database/schema availability.

```bash
docker compose exec web python manage.py createsuperuser
```

Use the platform admin to configure an organisation and user profile. Application role and clearance determine access; platform superuser access should be reserved for administration.

The supplied Compose configuration is a development stack. Its full storage/telemetry startup has not yet been verified as a clean-install release. It publishes infrastructure ports, and its optional Grafana configuration enables anonymous administration. Review [setup details and current limits](docs/DEVELOPMENT.md) before running it on a shared or publicly reachable host.

For AI-assisted drafting, configure an available provider/model in `.env`. Model availability and hardware requirements are separate from the application. The application does not download a model automatically. The default client configuration is `granite3.2:8b-instruct-fp16`; choose a model deliberately for the evaluation environment.

## Verification

In a configured development environment:

```bash
docker compose exec web python manage.py test core --noinput
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py evaluate_ai --check --output /tmp/minds-evaluation.json
```

The last verified suite, on 19 November 2026, passed **592 tests**, including real PostGIS transaction/concurrency checks. Targeted browser checks covered report editing, queue recovery, cancellation, manual drafting and review. Actual PDF/DOCX output was parsed, and PDF pages were inspected.

The authored passage benchmark selects the annotated answer span in **8/10** answerable cases, compared with **2/10** for leading excerpts. Fourteen citation regression cases pass. These are synthetic development results, not independent benchmarks or measurements of real-model factual accuracy. [Evaluation scope and known misses](docs/ai/QUALITY.md).

CI is not yet configured. [Verification details](docs/VERIFICATION.md) distinguish automated coverage, browser checks and unverified deployment/model behavior.

## Repository structure

```text
config/                 Django configuration and platform administration
core/
  access.py             Shared organisation, role and clearance policy
  ai/                   Composition, jobs, retrieval, citations and evaluation
  reporting/            Geological snapshots, figures and export renderers
  importers.py          Workbook validation and import transactions
  management/commands/  Worker, evaluation, import and fixture commands
  migrations/           Database schema history
  tests/                Unit, integration, concurrency and file-format tests
templates/              Application interface
infra/                  Application container and optional telemetry
fixtures/               Original seed data and example documents
docs/                   Architecture, behavior, verification and roadmap
```

## Current limits and next work

The next milestone is a reproducible development/test environment and CI, including dependency consolidation and security updates. The following UX pass will connect project → map → prospect → evidence → report, with responsive navigation, static assets and accessible error/empty states.

Further work includes metre-correct spatial queries and stronger relationship validation, real-model/domain evaluation, richer report sections and filters, a meaningful mining-mode example, immutable export packages and a controlled demonstration environment. Geological appendices currently use fixed schemas and bounded record counts; the collar figure is a local schematic, not a survey plan.

See the [roadmap](docs/ROADMAP.md) for the sequence and acceptance conditions.

## Project background

This repository began as the Team T07 university capstone application developed for OreFox. The current rework builds on that shared codebase and retains its document, geospatial, reporting and governance purpose. The independent revisions strengthen data integrity, access policy, evidence handling and report reliability. Original team work and subsequent revisions remain distinguishable through repository history; no claim is made that the original application was a solo project.

## License

The repository does not currently declare an open-source license. No redistribution or relicensing rights are implied by this README.
