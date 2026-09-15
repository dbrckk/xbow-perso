# Operational incident domains

Operational failures are separated into independent domains.

## Domains

- `workload`: workload SLO and error-budget burn;
- `control_plane`: worker-watchdog health;
- `observability`: incident-observer self-health.

Each domain receives its own fingerprint and deduplication key.

## Why domains are independent

A monitoring failure should not replace an existing workload incident. Likewise, worker control-plane recovery should not resolve an unrelated error-budget incident.

Domain identity is included in the fingerprint, so equivalent severity in two domains remains two distinct incidents.

## Compatibility

The domain classifier produces a top-level overall state for dashboards while preserving separate domain incidents underneath.

Lifecycle persistence can migrate to one active incident per domain in a follow-up change without changing the source classification rules.

## Safety

All domain signals are aggregate operational metadata. Domain separation does not change execution, retry, scanner, scope, or authorization behavior.
