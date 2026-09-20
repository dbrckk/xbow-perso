# Production migration: SQLite → PostgreSQL + Redis

This runbook migrates an existing single-node xbow-perso installation to the distributed production backends without enabling scanning.

## What is migrated

The migration tool copies the durable campaign metadata that is currently stored in SQLite:

- campaigns and optimistic versions
- observations
- artifact metadata
- hypothesis snapshots
- advisory-focus snapshots
- PentAGI flow bindings, when present
- queue history, including completed/failed/cancelled jobs, dedupe keys and queued jobs

Artifact files are **not copied**. They remain in the configured `XBOW_ARTIFACT_ROOT` and are verified by size and SHA-256 before cutover.

The source SQLite database is never modified. Before writing to PostgreSQL/Redis, `apply` creates a SQLite backup.

## Safety contract

Do not migrate while workers are executing jobs.

`plan` refuses a source queue containing a running job. `apply` additionally requires:

```bash
XBOW_MIGRATION_QUIESCED=true
```

Set that flag only after stopping backend/workers for the cutover window.

The target PostgreSQL tables and Redis queue prefix must be empty. This prevents accidental merging with another installation.

The migration does not:

- enable active scans
- change `DRY_RUN`
- change HackerOne submission settings
- migrate secrets out of environment variables
- delete or rewrite the source SQLite database
- send data to HackerOne or any target

## Configuration

The migration reads:

```bash
XBOW_MIGRATION_SQLITE_PATH=/data/xbow.sqlite3
XBOW_ARTIFACT_ROOT=/data/artifacts
XBOW_DATABASE_URL=postgresql://...
XBOW_REDIS_URL=redis://...
XBOW_REDIS_PREFIX=xbow:queue
```

Optional backup destination:

```bash
XBOW_MIGRATION_BACKUP_PATH=/data/xbow.sqlite3.pre-postgres.bak
```

## 1. Plan

Run from the backend image/container with access to the existing `/data` volume and the new PostgreSQL/Redis services:

```bash
PYTHONPATH=backend python -m app.production_migration plan
```

The output is redacted. It reports counts and blockers but never emits job payloads, credentials, database URLs, Redis URLs, or secret values.

A successful plan has:

```json
{"ok": true, "blockers": []}
```

## 2. Quiesce

Stop the backend and every worker before applying. Keep PostgreSQL and Redis running.

There must be no running source job. Queued jobs are allowed: they are copied with their original IDs, payloads, attempts, timestamps and dedupe keys, then become available after the distributed workers start.

## 3. Apply

With the application quiesced:

```bash
XBOW_MIGRATION_QUIESCED=true PYTHONPATH=backend python -m app.production_migration apply
```

The tool:

1. repeats preflight;
2. verifies every stored artifact;
3. creates a private SQLite backup;
4. copies metadata into PostgreSQL;
5. copies queue history into Redis;
6. verifies row/job counts;
7. leaves the source unchanged.

If target writing fails, the tool attempts to clear only the previously-empty target PostgreSQL tables and Redis queue prefix so the migration can be retried.

## 4. Cut over

After a successful apply, start xbow-perso with the distributed overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.distributed.yml -f docker-compose.tls.yml up -d --build
```

Keep the scanner profile disabled during the migration validation.

Confirm:

- `/ready` is healthy;
- `/api/deployment/preflight` reports the intended backend posture;
- campaign counts match the migration result;
- the dashboard can load existing campaigns;
- artifact reads still pass integrity checks;
- Redis queue counts match the migrated history.

Only after the storage migration and vault migration are separately verified should the installation be considered ready for the production-hardening profile.
