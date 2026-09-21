# Release 0.5.0 — stable prelaunch baseline

This release freezes the current HackerOne workflow for the first real authorized campaigns.

## Acceptance gates

A build is considered release-ready only when all of the following are true:

- GitHub `ci`, `security`, and `supply-chain` workflows pass.
- `/api/ready` reports healthy core dependencies.
- `/api/hackerone/live-readiness` reports `live_scan_ready=true` only after:
  - HackerOne server credentials are configured;
  - bounded recon is enabled and dispatch-ready;
  - the general worker heartbeat is fresh;
  - active scans are explicitly enabled;
  - `DRY_RUN=false`;
  - the dedicated scanner worker is enabled and its heartbeat is fresh;
  - Nuclei is enabled, allowlisted, version-pinned, and uses `restricted-v1`;
  - the API token is configured.
- Browser automation remains optional and explicitly gated.
- Direct HackerOne submission remains optional and disabled by default.
- PentAGI remains disabled for the first real run.
- Auto Queue selects only server-ranked `READY` bounty programs.
- Batch preflight creates no campaign.
- Final launch revalidates the current HackerOne snapshot, saved review profile, and current program-open state.
- Server-side batches remain durable if the dashboard closes.
- No historical bounty signal authorizes a target, expands scope, or enables a capability.

## First-run policy

For the first real authorized campaign:

- start with one reviewed program before increasing the batch size;
- keep request rates at or below the exact program policy limit;
- keep Nuclei as the only scanner engine;
- keep destructive testing, denial of service, social engineering, and credential attacks disabled;
- keep automatic external report submission disabled;
- stop immediately if scope or authorization becomes uncertain.

## Freeze rule

After this release, changes that add new execution capabilities should not be merged into the stable branch without a separate review cycle. Bug fixes, observability, fail-closed checks, and documentation corrections may continue.
