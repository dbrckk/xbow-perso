# Observer self-SLO

The incident-observation control plane is now evaluated as a reliability source in its own right.

## Classification

The observer is degraded when it has a recent failure, delayed success, a recorded deadline overrun, or leadership loss.

It becomes critical when:

- its circuit breaker is open;
- three or more consecutive observations fail;
- no successful observation has been recorded for more than five minutes.

The two-minute stale-success threshold produces a degraded signal.

## Incident integration

Observer self-health is fused into the same deterministic incident snapshot as watchdog, workload SLO, and error-budget state.

This makes loss of monitoring visibility explicit instead of allowing a broken observer to make the service appear healthy.

## Safety

Observer incidents are operational metadata. They do not authorize retries, scanner activity, scope changes, or campaign execution.
