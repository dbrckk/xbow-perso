# Incident API contract

The incident API adapter separates operational incident management from campaign execution.

## Read contract

The read operation returns:

- optimistic concurrency version;
- current active incident, if any;
- bounded lifecycle history;
- MTTR/MTBF-style reliability statistics.

It is intended for an authenticated `GET /api/incidents` route.

## Acknowledge contract

Acknowledgement requires both the incident fingerprint and the version previously read by the client.

A stale version becomes a conflict. This prevents an operator from acknowledging an incident state that has already changed.

Unknown, resolved, or already acknowledged fingerprints are a no-op rather than an execution action.

The HTTP adapter should expose this as an authenticated mutation route. Existing API middleware already applies API-token authentication and mutation TOTP requirements to `/api/*` requests.

## Boundary

Acknowledgement changes incident metadata only. It cannot retry jobs, restart workers/scanners, reclaim leases, alter scope, or modify campaign authorization.
