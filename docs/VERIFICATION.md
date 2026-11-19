# Verification

Last recorded verification: **19 November 2026**. The application suite passed **592 tests** against real PostgreSQL/PostGIS. Integration coverage includes concurrency, rollback, tenant isolation and actual export file contents. This is a recorded local result; CI is not yet configured.

## Coverage

| Area | Representative checks |
|---|---|
| Access/security | Cross-organisation reads/writes, related-record clearance, platform administration, private downloads and safe geospatial serialization |
| Imports/documents | Real workbook validation, repeat imports, empty-child replacement, dry runs, database/audit failures, concurrent imports/uploads and preserved file versions |
| Revisions/review | Stable series, title changes, stale saves, exact editor-to-review text, review locks and inherited provenance |
| Composition | Explicit selections, linked prospect scope, all drafting options, prompt limits, source changes and manifest persistence |
| Jobs | Concurrent enqueue/claims, durable replay receipts, retry, lease interruption, stale tokens, cancellation/completion races and publication rollback |
| Geological assembly | Scope, bounds, BDL/missing values, empty/coincident locations, version/refresh/removal, review snapshots and parsed PDF/DOCX tables/figures |
| Evaluation | Authored passage selection and citation mechanics regressions |

Fresh test-database migrations, model/migration drift, scoped Ruff checks and whitespace checks passed. The existing missing static-directory warning remains. Lint coverage is scoped to changed Python files, not a claim that every legacy file is clean.

Targeted headless Chromium checks exercised report editing, native review submission, queue navigation/retry/cancellation, manual drafting with an unreachable provider, native appendix saving and desktop/390px views. Rendered PDF pages were inspected; DOCX was parsed as ZIP/XML/media rather than opened in desktop Word/LibreOffice. No horizontal page overflow or application JavaScript errors occurred in the final recorded flows. These checks are not a complete accessibility or browser-compatibility audit.

## Evaluation boundaries

The versioned dataset in `core/ai/evaluation_data/quality-v1.json` has ten answerable passage cases, two no-answer cases and fourteen citation regression cases. Ranked passages hit 8/10 annotated spans; leading excerpts hit 2/10. Synonym and planned-versus-observed misses remain. The partitions were authored alongside the implementation, not independently blinded.

Provider-boundary tests and browser flows use deterministic responses; the manual drafting flow also runs with no reachable provider. No real-model factual accuracy, semantic citation support or domain compliance has been established.

## Re-run

In a configured development/test environment:

```bash
python manage.py test core --noinput
python manage.py makemigrations --check --dry-run
python manage.py evaluate_ai --check --output /tmp/minds-evaluation.json
```

See [development setup](DEVELOPMENT.md) for PostGIS, storage and migration privileges. Building a checked-in disposable test configuration and CI is the next verification milestone.

## Unverified release areas

Complete clean-install MinIO/telemetry startup, production deployment, load/performance limits, storage fault reconciliation, complete spatial/domain invariants, live-model quality and broad accessibility remain open. Previous raw review outputs and environment-specific scripts are retained outside the distributable source tree; the executable application regressions and synthetic evaluation dataset remain in the repository.
