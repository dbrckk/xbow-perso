# Observer resilience

The incident observer scheduler tracks its own redacted operational health.

## Signals

The health snapshot contains:

- consecutive observation failures;
- last successful observation timestamp;
- last failed observation timestamp;
- observed leadership-generation changes;
- current generation;
- circuit-breaker cooldown deadline.

No campaign, target, payload, scanner output, or secret data is included.

## Circuit breaker

Three consecutive observation exceptions open the circuit for 60 seconds by default. While open, a scheduled pass returns without acquiring leadership or running the observer.

A successful observation resets the failure streak and closes the circuit.

This prevents a repeatedly failing observer from continuously acquiring the incident-observation lease.

## Scope

The circuit breaker affects incident observation only. It does not stop, retry, resume, or alter campaign execution.
