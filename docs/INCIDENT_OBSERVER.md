# Incident observer

The incident observer connects aggregate reliability signals to the incident lifecycle and persistence layers.

Each observation pass:

1. receives already-aggregated operational metrics and rolling telemetry;
2. evaluates operational SLO state;
3. evaluates multi-window error-budget burn;
4. fuses those results with worker-watchdog state;
5. derives a deterministic incident snapshot;
6. applies lifecycle transitions;
7. persists only changed incident metadata.

## Concurrency

Persistence uses the incident store's optimistic versioning. The observer retries a bounded three times when another observer or operator changes incident state concurrently.

## Scheduler boundary

`run_incident_observation` performs exactly one observation pass. A scheduler can invoke it periodically without embedding an infinite loop in the API process.

Scheduling, leader election, and cross-instance coordination remain separate concerns.

## Safety boundary

The observer consumes aggregate health data only and writes operational incident metadata only.

It cannot create/retry jobs, reclaim leases, restart scanners, modify campaign state, alter scope, or change authorization. A critical incident remains an observation and escalation signal rather than an execution instruction.
