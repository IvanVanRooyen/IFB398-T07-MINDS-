# Durable report generation

Project/prospect report requests return promptly to the reporting workspace after enqueueing. A separate `run_report_worker` process reads the PostgreSQL queue; Redis remains a cache, not the broker.

## Claims and publication

Workers claim the oldest available queued row with `SELECT FOR UPDATE SKIP LOCKED`, assign an attempt token and release the transaction before evidence preparation or inference. Stages report the activity, not an estimated percentage.

The request freezes source IDs, fingerprints and project/prospect context, including empty automatic evidence. The worker reloads the account and checks current role, tenant, clearance and source/context access before generation and publication. Changed inputs fail safely and require review.

The report, source relations, audit and completed job result commit together. Cancellation locks the job and invalidates its token. If it commits first, late output is discarded; if completion wins, the job stays completed. Cancellation does not terminate an external inference already running.

## Duplicate requests and recovery

Each rendered form has a submission UUID. Replaying it with the same options returns the same job, including after completion or source changes; reusing it for different options is rejected. Identical active snapshots for the same user coalesce, with durable receipts for every submission key. A deliberately new form after completion can create another draft.

The worker refreshes leases at stage boundaries. The default lease is 600 seconds, with an effective minimum of provider timeout plus 60. Expired attempts become recoverable failures on worker/history checks. Retry is explicit, revalidates original inputs/access and increments attempts on the next claim. A stale token cannot publish.

External calls can repeat after an interruption; exactly-once provider execution is not guaranteed. Additional workers can claim different rows; each process handles one job at a time.

## Interface and operation

Owner-scoped history/status enforces current tenant/clearance even for job links. Status contains no internal payload or token; completed links check current report/source access. Responses are private/no-store. Cancel/retry use authenticated, CSRF-protected author POSTs. History is paginated, and native refresh/forms remain usable without JavaScript.

```bash
python manage.py run_report_worker
python manage.py run_report_worker --once
```

Compose includes a separate worker with no published ports and a restart policy. It tolerates database/schema startup errors. It does not run migrations itself. Admission limits, retention, alerting and load measurements remain release work.

[Development](../DEVELOPMENT.md) · [Verification](../VERIFICATION.md)
