# Release 0.5.1 — final stability patch

This patch contains stability and fail-closed changes only. It does not add a new execution capability.

## Batch safety

- Reviewed batch launch now uses one authoritative server-side go/no-go verdict combining live runtime readiness and current reviewed-program preflight.
- Sequential members are revalidated against the current HackerOne snapshot immediately before delayed start.
- Parallel members use the same revalidation path.
- A changed snapshot or a program that is no longer open moves the member to review instead of starting it.
- Temporary HackerOne revalidation failures do not start a campaign; retries use bounded exponential backoff.
- Parallel batches with ready members can resume after a worker/process restart.
- Reconciliation lists active batches directly so older active work is not hidden by large numbers of completed batches.

## Deployment safety

- The live production update performs a final backend HackerOne live-readiness attestation after recon, scanner sandbox, and Nuclei version checks.
- Failure remains redacted to status and failed check identifiers.
- Automatic HackerOne report submission remains disabled by default.
- PentAGI remains outside the first-run stable profile.

## Stable first run

Start with one explicitly reviewed HackerOne program. Increase batch size only after that run completes normally. Every program remains bound to its exact reviewed snapshot and policy.
