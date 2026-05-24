# Handoff — current session state

## Session date
2026-05-10

## What was worked on this session
Completed Requirement 6 admin registrations, fixed a SurveyAdmin field error, and fixed the audit log 404.

## What was implemented

- **`core/admin.py`** — completed the Requirement 6 admin work:
  - `ProspectAdmin` Geometry fieldset updated to include `area_geom`
  - `SampleAdmin` (GISModelAdmin) registered with fieldsets covering identity, sample details, collection, and location
  - `SurveyAdmin` (GISModelAdmin) registered with fieldsets covering identity, survey details, and coverage area
  - Fixed startup crash: `SurveyAdmin.readonly_fields` referenced `updated_at` which does not exist on the `Survey` model (Survey only has `created_at`); removed it from both `readonly_fields` and the Timestamps fieldset

- **`config/urls.py`** — fixed audit log 404:
  - Moved `path("", include("core.urls"))` before `path("admin/", admin.site.urls)`
  - Root cause: Django's admin site registers a catch-all for `admin/*` that intercepted `admin/audit-log/` before core.urls was ever consulted

## Key decisions made this session

- URL ordering fix documented in decisions.md: core.urls must precede admin.site.urls so that custom routes under the `admin/` prefix are not swallowed by Django admin's catch-all. See decisions.md entry dated 2026-05-10.

## Files created or meaningfully changed

- `core/admin.py`
- `config/urls.py`
- `memory/decisions.md`
- `memory/handoff-current.md`

## State of in-progress work

Migration 0023 (Req 6 — area_geom, Sample, Survey) needs to be applied. Django is reporting unapplied model changes even though 0023 appears to be in the migration history. The recommended fix is:
```
docker compose exec web python manage.py makemigrations core --name req6_fixup
docker compose exec web python manage.py migrate
```
This will let Django auto-generate any gap between 0023 and the current model state and apply it cleanly.

## Known issues

- Migration 0023 state discrepancy: Django detects model changes not yet in a migration despite 0023 existing and being applied. Exact cause not identified — likely a minor field kwarg mismatch between the hand-written migration and what Django derives from models.py. Running `makemigrations` will resolve it.
- `Document.confidentiality` (lowercase) vs `UserProfile.clearance_level` (uppercase) mismatch — documented tech debt in decisions.md, three mapping dictionaries must stay in sync.
- Debug `print()` statements in `views.upload_doc` (~lines 262–273) — must be removed before production.
- `ALLOWED_HOSTS = ["*"]` in settings — dev-only, must be tightened for production.
- Grafana anonymous admin access in docker-compose.yml — dev-only config.

## Immediate next steps

1. Run `makemigrations` + `migrate` to resolve the Req 6 migration gap (see above)
2. **Requirement 7** — Mode-aware dual-mode interface: mining entity models (`Pit`, `Stope`, `Panel`, `ProductionRecord`, `Reconciliation`, `Incident`), context processor, conditional nav in `base.html`
3. **Requirement 8** — Structured report sections (`ReportSection` model + editor UI) — most complex, implement last

## Memory files updated this session

- `memory/decisions.md` — added URL ordering decision (core.urls before admin.site.urls)
