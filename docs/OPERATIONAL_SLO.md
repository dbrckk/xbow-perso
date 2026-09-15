# Operational SLO classification

xbow-perso classifies aggregate runtime health as `healthy`, `degraded`, or `critical`.

The classifier is read-only and uses operational counters/ages only. It never inspects targets, payloads, secrets, or scanner results.

## Signals

The initial SLI set is deliberately small:

- age of the oldest queued job;
- aggregate failed-job count;
- age of the oldest unresolved outbox intent;
- worker-watchdog status.

Each numeric signal has a warning and critical threshold. Invalid or inverted thresholds fail closed.

## Default thresholds

| Signal | Degraded | Critical |
| --- | ---: | ---: |
| oldest queued job | 120 s | 600 s |
| failed jobs | 2 | 10 |
| oldest pending outbox | 60 s | 300 s |

A watchdog warning makes the service degraded. A watchdog error makes it critical.

## Interpretation

`healthy` means none of the configured operational budgets is currently breached.

`degraded` means service is still expected to operate but an operator should investigate capacity, worker health, or downstream delivery.

`critical` means at least one hard operational budget has been crossed. It is a signal for incident handling, not permission to duplicate, retry, or broaden security-testing work.

Future SLOs should use bounded rolling windows once durable time-series storage is introduced.
