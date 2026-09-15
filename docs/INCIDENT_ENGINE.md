# Operational incident engine

The incident engine fuses three existing redacted health sources:

- worker watchdog;
- operational SLO classification;
- multi-window error-budget burn status.

It produces one deterministic service state: `healthy`, `degraded`, or `critical`.

## Deduplication

An incident fingerprint is derived only from the sorted source/state pairs. Repeated evaluation of the same degraded conditions therefore yields the same deduplication key.

No target, payload, credential, scanner output, endpoint, campaign identifier, or job identifier participates in the fingerprint.

## Severity

Critical/error source states dominate degraded/warning states. Healthy sources do not create incident signals.

## Recovery boundary

The incident engine is observational only.

It never:

- retries a job;
- reclaims a lease;
- restarts a scanner;
- broadens target scope;
- changes campaign state;
- bypasses admission or authorization controls.

Recovery remains an explicit operator or separately reviewed orchestration action. This prevents an observability component from becoming an execution path.
