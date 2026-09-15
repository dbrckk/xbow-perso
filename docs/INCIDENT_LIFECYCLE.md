# Incident lifecycle

Operational incident snapshots can be converted into a bounded lifecycle history.

## States

An incident starts as `opened`. An operator can mark it `acknowledged`. A healthy snapshot resolves the active incident.

If the active fingerprint changes, the previous incident is resolved and a new incident is opened. Repeated snapshots with the same fingerprint update `last_seen_at` instead of creating duplicates.

## Retention

The lifecycle helper keeps at most 1,000 incident records per supplied history. Persistence remains the responsibility of the storage layer.

## Reliability statistics

Resolved history can produce:

- mean time to resolution (MTTR);
- mean interval between incident openings (MTBF-style operational interval).

Statistics ignore malformed records rather than exposing or inferring workload content.

## Execution boundary

Lifecycle transitions are operational metadata only. Acknowledging or resolving an incident does not retry work, reclaim leases, restart scanners, modify target scope, or change campaign authorization.
