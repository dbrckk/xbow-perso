# Worker watchdog

The watchdog converts existing aggregate operational metrics into bounded health signals.

It is intentionally read-only. It does not inspect target URLs, job payloads, secrets, or scanner output, and it does not automatically re-run work.

## Signals

- `queue_stalled`: the oldest queued job exceeded the configured queue-age budget.
- `running_lease_stale`: the oldest running lease exceeded its hard age budget.
- `failed_job_budget_exceeded`: aggregate failed jobs exceeded the configured error budget.

A stale running lease is an error. Queue delay and failed-job budget violations are warnings so operators can investigate without automatically duplicating potentially expensive work.

## Configuration

- `XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS` defaults to 600.
- `XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS` defaults to 21600.
- `XBOW_WATCHDOG_MAX_FAILED_JOBS` defaults to 5.

Invalid thresholds fail closed.

## Recovery policy

Recovery remains explicit and conservative:

1. identify the aggregate watchdog signal;
2. inspect worker/process health and queue backend health;
3. allow the existing lease mechanism to establish that ownership has expired;
4. recover only through the queue's existing ownership/lease semantics;
5. never create a duplicate job solely because the watchdog reports a stale condition.

This separates detection from mutation and reduces duplicate execution risk.
