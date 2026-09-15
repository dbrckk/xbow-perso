# Incident persistence

Operational incident lifecycle history can be stored transactionally in SQLite without mixing it with campaign execution state.

## Concurrency

The incident document uses optimistic versioning. Every write supplies the version observed by the reader. A stale writer receives an explicit conflict instead of overwriting newer incident state.

This makes acknowledgement/lifecycle updates safe to retry at the API layer after re-reading current state.

## Isolation

Incident history lives in a dedicated `operational_incidents` table and does not modify campaign documents, queue leases, scanner state, scope, findings, or authorization.

The persistence API stores redacted lifecycle metadata only.

## Bounds

The lifecycle layer already caps history at 1,000 records. The persistence layer additionally rejects serialized history above 2 MiB.

## API integration

A future API adapter should:

- expose history through an authenticated read-only endpoint;
- require the existing mutation authentication controls for acknowledgement;
- translate stale-version writes to HTTP 409;
- never allow incident acknowledgement to trigger retries or execution.
