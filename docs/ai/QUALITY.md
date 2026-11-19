# Retrieval and citation evaluation

The offline evaluation measures bounded passage selection and mechanical citation checks. It does not establish real-model factual accuracy, independent benchmark performance or company adoption.

## Authored passage benchmark

The versioned dataset contains twelve cases: ten annotated answer spans and two without an answer. Under a 600-byte ceiling, it compares leading excerpts with ranked passages selected within a document.

| Partition | Answerable | Leading hits | Ranked hits |
|---|---:|---:|---:|
| Development | 6 | 1/6 | 6/6 |
| Challenge | 4 | 1/4 | 2/4 |
| Total | 10 | 2/10 | 8/10 |

The partitions were authored alongside the implementation, not independently blinded. Repeated filler makes later evidence easy to test; these proportions do not represent a production corpus. The retained misses are a synonym gap and a planned-versus-observed statement. One no-answer case has a lexical match, so positive scores do not prove answerability.

## Retrieval methods

Composition ranks overlapping, byte-bounded windows of canonical document text using BM25, within the selected file scope and prompt cap. A no-match fallback remains explicitly labelled. Manifests retain canonical character offsets, score/method, query, source URL and exact excerpts. Scores are ordering values, not probabilities.

Legacy chunk retrieval uses PostgreSQL English full-text `SearchRank`, current parent metadata, stable ties and access/latest/scope constraints. It is a different retrieval path from the within-document passage benchmark.

## Citation checks

Fourteen authored regression cases verify label/link mechanics, paragraph/list-item coverage and literal quoted/measurement matches against supplied excerpts. Source footers/reference definitions/code do not earn prose coverage. The editor refreshes feedback after saves and marks later unsaved text unchecked.

These checks are advisory and add no automatic approval gate. A syntactically valid citation or matching number can still be semantically misleading. Unit conversions, calculations, negation, scientific notation, complex attribution and expert scientific support need stronger evaluation. A deliberate regression demonstrates the limitation.

## Run

```bash
python manage.py evaluate_ai --check --output /tmp/minds-evaluation.json
```

Default execution is offline: no model call/download and no evaluation data written to the application database. The artifact records dataset SHA-256, versions, limits, selected passages, per-case outcomes and regression failures. `--check` enforces the recorded floors and citation expectations; these preserve behavior rather than define real-world acceptance quality.

An explicit `--live` run can use an already configured provider on synthetic contexts. It records requests/responses and mechanical checks with semantic review marked not performed. No live-model factual evaluation has been completed.

Dataset: [quality-v1.json](../../core/ai/evaluation_data/quality-v1.json). See [verification](../VERIFICATION.md) and the [roadmap](../ROADMAP.md) for the domain-reviewed next step.
