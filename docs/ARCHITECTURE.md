# Architecture

MINDS is a Django/GeoDjango application backed by PostgreSQL/PostGIS, S3-compatible document storage and Redis. Its browser interface uses Django templates, HTMX and MapLibre. An independent management-command worker processes report jobs from PostgreSQL.

## Domain

An organisation owns projects/operations. Projects contain prospects, tenements, documents and drillholes; drillholes carry survey, lithology and assay records. Documents can link to a prospect. Reports identify a project and optionally a prospect, keep source-document relations and belong to a stable revision series.

Application roles and clearance apply within an organisation. Platform superusers administer the system separately. Geological rows currently have organisation/project scope but no independent per-row classification field.

## Boundaries

| Component | Responsibility |
|---|---|
| `core/access.py` | Shared organisation, clearance and author policy |
| `core/importers.py` | Workbook parsing, validation and atomic import behavior |
| `core/ai/composition.py` | Validated source/options selection and exact drafting input manifests |
| `core/ai/jobs.py` | Durable claims, attempt tokens, leases, retries, cancellation and atomic publication |
| `core/ai/passages.py` | Bounded passage selection within chosen documents |
| `core/ai/retrieval.py` | PostgreSQL full-text ranking for legacy chunk retrieval |
| `core/ai/citations.py` | Advisory saved-text citation mechanics and literal excerpt matching |
| `core/reporting/` | Frozen geological appendices, collar layout and PDF/DOCX rendering |
| `SavedReport.create_version` | Series locking, stale-parent checks and revision inheritance |

## Data flow

Uploads are extracted and versioned with unique file paths. Workbook imports validate before database writes and replace matching child records transactionally when requested. These services preserve historical document bytes and avoid partial import results within their stated transaction boundaries.

The report composer fixes the selected source IDs, source fingerprints and project/prospect context. A worker checks current authority and the frozen inputs before generation and again before publication. The report, its sources, creation audit and completed job state commit together. There is no database transaction held across a model call.

An author can capture a geological appendix during save or review submission. It records bounded rows, record identities, scope, time and digest separately from the original drafting manifest. Narrative edits inherit the saved appendix; an explicit capture replaces it in a new revision.

Review refers to a particular report revision. Editor exports for reports with appendices use the saved narrative and appendix together. Historical process exports and document-analysis/cache helpers remain separate legacy paths.

## Design constraints

- Access checks apply to the parent and relevant related records, not only an incoming ID.
- Derived report classification must not lower the requesting context's restrictions.
- Retries can repeat an external call after an interruption; exactly-once external inference is not guaranteed.
- Database and object storage do not form a distributed transaction. Cleanup/reconciliation needs remain.
- A capture is a bounded read set during a save transaction, not a serializable whole-database backup.
- Citation mechanics and a valid source label do not establish scientific support.

## Detailed behavior

[Access](security/FOUNDATION.md) · [Ingestion](ingestion/INTEGRITY.md) · [Revisions/review](reporting/INTEGRITY.md) · [Composition](reporting/COMPOSITION.md) · [Jobs](reporting/JOBS.md) · [Geological assembly](reporting/ASSEMBLY.md) · [Evaluation](ai/QUALITY.md)
