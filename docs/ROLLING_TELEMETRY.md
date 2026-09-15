# Rolling operational telemetry

The rolling telemetry layer derives short-window service indicators from redacted worker outcome events.

## Windows

Two bounded windows are currently supported:

- 5 minutes;
- 1 hour.

At most the latest 10,000 source events are considered for one aggregation pass.

## Indicators

For each window the aggregator reports:

- completed outcome-event count;
- failed outcome-event count;
- failure rate;
- throughput per minute;
- execution duration p50, p95, and p99 when duration data is present.

Malformed timestamps, future timestamps, and invalid duration values are ignored.

## Privacy and safety

Only redacted `worker_outcome` events are accepted. Aggregated output contains no targets, job payloads, credentials, scanner output, or endpoint identities.

This module performs no retries and does not influence task admission or execution.

## Storage model

This layer deliberately separates aggregation from persistence. Existing campaign event storage can supply the bounded source event set today. A future dedicated telemetry backend can implement retention, compaction, and cross-instance aggregation without changing the SLI calculation contract.
