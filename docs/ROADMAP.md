# Roadmap

## 1. Reproducible engineering baseline — implemented locally

The supported local Compose profile, checked-in test settings, synthetic seed/reset, complete dependency lock/runtime export and CI workflow are implemented. Verification covers fresh migrations, whole-repository lint, 600 PostGIS tests, offline evaluation, runtime dependency audit and a separate-process HTTP/worker smoke check. The workflow is ready to execute on GitHub when pushed; local verification is not a hosted CI result.

Python/application/service images are pinned, local infrastructure ports are private and model access is optional. The legacy full storage/telemetry stack and production configuration remain outside this verified profile.

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
