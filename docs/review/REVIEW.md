# Baseline assessment and revision scope

The baseline assessment used university handover commit `05c668c`. It found a substantial Django/PostGIS application with useful domain models, but incomplete authorisation, disconnected report options, fragile data-changing operations and a development-only deployment configuration.

## Baseline findings

Runtime checks identified cross-organisation reads/writes, inconsistent clearance checks, unsafe serialized geospatial properties and derived report classification below high-clearance context. Other findings included repeat-import child duplication, failure-unsafe document versions, ignored report title edits, stale editing/review behavior, missing mobile navigation/assets and interface contrast/overflow issues.

An isolated baseline test run had 431 tests, with 424 passing, five failures and two errors. PostgreSQL/PostGIS migrations and exporter checks also ran. These numbers describe that historical baseline, not the current application.

## Current revision

Subsequent changes centralise access checks, preserve private downloads and classification, make imports/document versions safer, add stable report series/review snapshots, connect evidence-scoped composition, add ranked passages/citation regressions, move drafting into durable jobs and support manual outlines plus geological appendices/exports.

The current suite has 600 passing tests. [Verification](../VERIFICATION.md) records its scope and limitations. The implementation does not require a framework rewrite to complete its current product workflows.

## Still open

Hosted CI execution, ongoing dependency/security maintenance, broad spatial/model validation, a coherent interface pass, real-model/domain evaluation, fuller report assembly, mining-mode demonstration and controlled deployment remain. Passing the current tests is not a claim that all original findings or production risks are resolved.

The original application was a team capstone for OreFox; the subsequent rework builds on it. Historical intent and current executable behavior are separate evidence. Original contributions and repository history remain intact.
