# Verification

Last recorded application verification: **19 November 2026**. The supported Docker profile passes **600 tests** with real PostgreSQL/PostGIS, Redis and repository-owned test settings. This includes eight synthetic seed/reset regressions added to the earlier 592-test application baseline.

## Reproducibility and CI

The application builds from the repository root with `pyproject.toml`, `uv.lock` and a pinned Python image, with no personal directories, source mount or previously built application image. Runtime pip requirements are hash-pinned exports checked for drift. PostGIS/Redis images are pinned; package updates include the patched Pillow 13 release. GDAL is supplied by the current pinned distribution base.

The same `scripts/check.sh` runs locally and in `.github/workflows/ci.yml`: lock consistency, export drift, whole-repository Ruff, warning-free Django checks, migrations, model/migration drift, the PostGIS suite and offline AI evaluation. The runtime dependency advisory check is separate in `scripts/audit.sh`. It reported no known Python runtime dependency vulnerabilities at verification time; this is not an operating-system/container penetration assessment or a permanent security guarantee.

A clean source-copy/fresh-volume verification covers the supported profile. The HTTP smoke check seeds twice, opens authenticated routes, downloads the exact private source bytes, verifies an anonymous download is refused and waits for a separate worker to complete a manual report job. No model or object store is needed. Hosted GitHub execution begins after push; local command/action syntax verification is not presented as a hosted run.

## Application coverage

| Area | Representative checks |
|---|---|
| Access/security | Cross-organisation reads/writes, related-record clearance, platform administration, private downloads and safe geospatial serialization |
| Imports/documents | Real workbook validation, repeat imports, empty-child replacement, dry runs, database/audit failures, concurrent imports/uploads and preserved file versions |
| Revisions/review | Stable series, title changes, stale saves, exact editor-to-review text, review locks and inherited provenance |
| Composition | Explicit selections, linked prospect scope, all drafting options, prompt limits, source changes and manifest persistence |
| Jobs | Concurrent enqueue/claims, durable replay receipts, retry, lease interruption, stale tokens, cancellation/completion races and publication rollback |
| Geological assembly | Scope, bounds, BDL/missing values, empty/coincident locations, version/refresh/removal, review snapshots and parsed PDF/DOCX tables/figures |
| Synthetic seed | Repeat-safe IDs/files/passwords, real source content and snapshot, bounded reset, retained outside records/profiles, rollback/file cleanup, collisions and environment/password guards |
| Evaluation | Authored passage selection and citation mechanics regressions |

## Interface evidence

Earlier targeted headless Chromium checks exercised report editing, native review submission, queue navigation/retry/cancellation, manual drafting with an unreachable provider, native appendix saving and desktop/390px views. Rendered PDF pages were inspected; DOCX was parsed as ZIP/XML/media rather than opened in desktop Word/LibreOffice. No horizontal page overflow or application JavaScript errors occurred in those recorded flows. These checks are not a complete accessibility or browser-compatibility audit. The next milestone is the end-to-end UX pass.

## Evaluation boundaries

The versioned dataset in `core/ai/evaluation_data/quality-v1.json` has ten answerable passage cases, two no-answer cases and fourteen citation regression cases. Ranked passages hit 8/10 annotated spans; leading excerpts hit 2/10. Synonym and planned-versus-observed misses remain. The partitions were authored alongside the implementation, not independently blinded.

Provider-boundary tests use deterministic responses. Test settings prevent use of configured real model endpoints. No real-model factual accuracy, semantic citation support or domain compliance has been established.

## Re-run

```bash
docker compose -f compose.dev.yml --profile test run --rm checks
docker compose -f compose.dev.yml --profile test run --rm checks sh scripts/audit.sh
docker compose -f compose.dev.yml exec -T web python -m scripts.smoke
```

See [development setup](DEVELOPMENT.md) for environment, seed/reset and cleanup. Smoke checks create synthetic drafts; run them against the disposable local profile.

## Remaining release areas

The separate legacy MinIO/telemetry stack, production deployment, load limits, storage reconciliation, complete spatial/domain invariants, real-model quality and broad accessibility remain open. Raw environment-specific verification outputs are kept outside the distributable source tree; executable regressions, test settings, commands and synthetic evaluation data are checked in.
