# Domain incident lifecycle

The lifecycle layer can now maintain one active incident independently for each operational domain:

- workload;
- control plane;
- observability.

A healthy transition in one domain resolves only that domain's active incident.

A changed fingerprint rotates only the affected domain. Incidents in other domains remain active and continue updating independently.

Repeated identical fingerprints update `last_seen_at` rather than creating duplicates.

The history remains globally bounded to 1,000 records.

This removes the previous single-active-incident coupling while retaining the same read-only operational boundary: lifecycle changes never authorize campaign execution, retries, scanner activity, or scope changes.
