# Roadmap

## 1. Reproducible engineering baseline

Provide a minimal application Compose profile, an owned test configuration, explicit environment validation, consistent dependency installation and a maintained synthetic seed. Add CI for migrations, meaningful lint, the full PostGIS test suite and offline evaluation. Address known dependency/security and development-configuration issues before deployment.

Acceptance: a clean checkout can boot the supported development profile and run the test suite from documented commands, with no personal directories, cached image assumptions or existing services required. CI reports the same checks on a pull request.

## 2. Complete the investigation workflow

Review project → map → prospect → linked evidence → report as one interaction. Address navigation, missing static assets, accessible geometry editing, mobile tables/filters, loading/empty/error states and consistent terminology.

Acceptance: a new user can complete the scenario with supplied data; keyboard, mobile, failure-recovery and access checks cover the whole path. Produce new screenshots from that verified interface for the repository overview.

## 3. Strengthen spatial and domain integrity

Verify metre-based spatial operations and CRS transformations against known fixtures. Extend relationship and geometry validation beyond the import service. Define geological validation policies where overlaps and check assays may be legitimate.

Acceptance: documented expected results for spatial queries and invalid relationship/geometry cases, backed by integration tests.

## 4. Evaluate real evidence-assisted drafting

Use a domain-reviewed corpus with known evidence, contradictions and missing answers. Measure retrieval quality, supported citations, unsupported assertions, abstention and latency on an explicitly identified provider/model. Compare improvements to the existing lexical baseline.

Acceptance: inspectable dataset/configuration/results, retained misses and clear separation between mechanical checks and expert factual review.

## 5. Expand reporting and demonstrate mining work

Add richer sections/record filters, reporting periods, complete source catalogues and archival exports. Define a bounded operational example before expanding mining-specific entities or terminology. Framework templates require domain review and explicit requirements.

Acceptance: a meaningful exploration and mining scenario share the same access, evidence, version and review services; published snapshots remain understandable after live data changes.

## 6. Package a controlled release

Finish production configuration, dependency maintenance, storage/backups, job limits/retention, telemetry and a safe demo/reset policy. Confirm licensing and distribution rights. Keep original university team work distinct from subsequent revisions in the case study.

Acceptance: repeatable deployment/rollback and demo reset, measured operating limits, approved public data and an accurate project overview with representative screenshots.
