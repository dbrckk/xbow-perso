# xbow-perso

Self-hosted, mobile-first orchestration platform for **authorized** bug bounty and security testing.

## Goal

Enter a target, scope, credentials and program rules from a smartphone. xbow-perso converts them into enforceable policy, launches isolated security workers, correlates evidence, requests independent validation, deduplicates findings and produces a professional submission-ready report.

## Core principles

- **Scope first:** no task is executed before policy authorization.
- **Fail closed:** unknown hosts/actions are blocked.
- **Non-destructive by default:** DoS, destructive actions, social engineering and credential attacks are disabled.
- **Independent validation:** discovery and validation are separate stages.
- **Evidence over claims:** findings require reproducible evidence before `confirmed` status.
- **Mobile-first:** responsive PWA/API, with the heavy work executed server-side.
- **Replaceable engines:** Strix, PentAGI and future engines are adapters, not the core.

## Architecture

```text
Smartphone / PWA
      |
      v
FastAPI Control Plane
      |
      +-- Scope & Rules Engine (fail closed)
      +-- Campaign Orchestrator
      +-- Findings / Evidence Store
      +-- Report Generator
      |
      v
Isolated Worker Adapter Layer
      |
      +-- Strix (first integration)
      +-- PentAGI (guarded preview + dedicated lifecycle workers)
      +-- additional scanners/tools (planned)
```

## Current MVP

The first milestone provides:

1. target/campaign creation;
2. allow/deny scope validation;
3. explicit test policy;
4. campaign state machine;
5. Strix command adapter with dry-run by default;
6. independent validation queue;
7. normalized findings;
8. Markdown bug-bounty report generation;
9. responsive smartphone UI;
10. Docker Compose deployment.

## Run

```bash
cp .env.example .env
docker compose up --build
```

Open `http://SERVER_IP:8080` from your phone.

The default configuration uses `DRY_RUN=true`; external testing engines are not launched until you explicitly configure them.

Governed queue jobs also require deterministic policy provenance by default. A worker rejects a governed job when provenance is missing or when the campaign scope/rules no longer match the queued policy fingerprint. During migration only, legacy jobs created before provenance enforcement may be drained by explicitly setting `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS=true`; deployment preflight reports this as a warning and the default remains `false`.

## Disaster recovery integrity

Backups remain operator-managed. xbow-perso does not automatically restore PostgreSQL, Redis, or vault data.

After producing trusted copies of the PostgreSQL dump, Redis snapshot, and encrypted vault, create an integrity manifest:

```bash
PYTHONPATH=backend python -m app.dr_cli manifest \
  --postgres-dump /backups/postgres.dump \
  --redis-snapshot /backups/dump.rdb \
  --vault-copy /backups/secrets.vault.json \
  --output /backups/xbow-manifest.json
```

Before any restore operation, verify the copies non-destructively:

```bash
PYTHONPATH=backend python -m app.dr_cli verify \
  --manifest /backups/xbow-manifest.json \
  --postgres-dump /backups/postgres.dump \
  --redis-snapshot /backups/dump.rdb \
  --vault-copy /backups/secrets.vault.json
```

After restoring storage, validate the logical queue state before resuming workers:

```bash
PYTHONPATH=backend python -m app.dr_cli queue-check
```

`queue-check` is read-only. It does not requeue jobs, recreate work, clear leases, or mutate queue state. It reports expired or inconsistent leases, invalid retry counters, and queue-transition audit failures, then returns a non-zero exit code when operator reconciliation is required. The same assessment is available through `GET /api/recovery/queue`.

When backup verification, queue recovery, campaign audit, worker audit, and queue-transition audit are all valid, create a signed recovery attestation:

```bash
PYTHONPATH=backend python -m app.dr_cli attest \
  --manifest /backups/xbow-manifest.json \
  --postgres-dump /backups/postgres.dump \
  --redis-snapshot /backups/dump.rdb \
  --vault-copy /backups/secrets.vault.json \
  --output /backups/recovery-attestation.json
```

Verify the artifact independently with:

```bash
PYTHONPATH=backend python -m app.dr_cli verify-attestation \
  --attestation /backups/recovery-attestation.json
```

Recovery attestations require the configured audit HMAC key and contain only integrity/check results and aggregate counts; they do not include backup contents, target data, payloads, or secrets.

The manifest stores only filenames, sizes, and SHA-256 hashes; it never embeds backup contents or decrypted secrets. When `XBOW_AUDIT_HMAC_KEY` (or the `audit_hmac_key` vault entry) is available, the manifest is also authenticated with HMAC-SHA256 so manifest rewriting is detectable.

## Safety model

A campaign must include written authorization metadata, allowed targets and prohibited actions. Requests outside the declared scope are rejected by the API before reaching a worker. This is an engineering control, not a substitute for the rules of the bug bounty program.

## Roadmap

- persistent PostgreSQL storage
- queued workers (Redis/Celery or equivalent)
- real Strix job lifecycle + result parser
- PentAGI remote lifecycle/status UX
- Playwright browser worker
- recon graph / target memory
- program importers
- evidence artifacts and screenshots
- CVSS/CWE normalization
- HackerOne/Bugcrowd-style report templates
- authentication + TOTP/WebAuthn
- encrypted secrets vault
- audit logs and per-action policy receipts
- deployment hardening and reverse proxy/TLS


## PentAGI workers

PentAGI has two dedicated worker services so its lifecycle never blocks generic scanning workers:

- `pentagi-worker`: reserved for a future execution-capable, fully admitted remote-flow path.
- `pentagi-status-worker`: tracks already-created flows through bounded read-only polling.

The current release intentionally keeps **new PentAGI flow dispatch in `preview_only` mode**. The HTTPS transport, permit validation, dedicated queue and worker gates exist, but xbow-perso cannot yet prove that downstream PentAGI activity enforces the campaign's exact scope and request-rate ceiling after `createFlow`. For that reason, turning on `XBOW_ENABLE_PENTAGI`, `XBOW_ENABLE_PENTAGI_WORKER`, `XBOW_ENABLE_PENTAGI_TRANSPORT`, active scans, and `DRY_RUN=false` is still **not sufficient** to make dispatch admissible.

`GET /api/capabilities` reports the effective PentAGI state and the exact non-secret block reasons. The control plane remains fail-closed until an enforceable downstream execution contract is implemented and reviewed.

The dedicated containers remain behind Compose profiles. The status profile may be enabled separately when tracking previously created/known flows is required:

```bash
docker compose --profile pentagi --profile pentagi-status up -d --build
```


## Dedicated scanner sandbox

Active external scanner execution is isolated from the general worker. The general worker handles recon, browser, validation and report jobs; Strix/Nuclei jobs require the dedicated scanner worker profile.

Start it explicitly:

```bash
docker compose --profile scanner up -d --build
```

Active execution remains fail-closed unless all scanner admission gates are satisfied, including:

- `DRY_RUN=false`;
- `XBOW_ENABLE_ACTIVE_SCANS=true`;
- `XBOW_ENABLE_SCANNER_WORKER=true`;
- `XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1`;
- engine present in `XBOW_SCANNER_ALLOWED_ENGINES`;
- worker runtime attests read-only root filesystem, no-new-privileges and all Linux capabilities dropped;
- engine-specific runtime checks such as the pinned Nuclei version.

The default allowlist contains only Nuclei. Strix must be explicitly added after its runtime contract has been reviewed. `GET /api/capabilities` reports the non-secret scanner admission state.


### Recovery readiness gate

After restore verification, configure the signed attestation path:

```bash
XBOW_RECOVERY_ATTESTATION_PATH=/backups/recovery-attestation.json
```

The read-only endpoint `GET /api/recovery/readiness` returns one of:

- `BLOCK`: a hard integrity or configuration problem exists; workers must not resume.
- `REVIEW`: no blocker exists, but operator review is still required (for example legacy provenance mode or no signed attestation configured).
- `READY`: preflight, queue recovery, campaign/worker/queue audits, and the signed recovery attestation are all valid.

The gate never starts workers or mutates queue state. `workers_may_resume=true` is only an advisory authorization signal for an operator-controlled restart.


### Control plane health model

The operations dashboard exposes a read-only 0-100 control-plane health score composed from six domains:

- governance: 20%
- queue integrity: 20%
- validation pipeline: 15%
- recovery readiness: 20%
- storage/durability: 15%
- reporting pipeline: 10%

Score states are:

- `HEALTHY`: 90-100
- `DEGRADED`: 70-89
- `BLOCKED`: 0-69

Hard fail-closed caps override the weighted average when queue transition audit is invalid, recovery readiness is `BLOCK`, or critical operational alerts exist. The score is advisory and never starts workers or mutates platform state.


### Control plane health history

Health snapshots are persisted only when the canonical health state changes. The operations dashboard records the current score and exposes trend data through:

```text
GET /api/dashboard/operations/health-history
```

The history includes the current and previous score, score delta, trend (`improving`, `stable`, `degrading`), state transitions, and persistent-degradation detection. Operational alerts include a warning when health is actively degrading and a critical alert when degradation persists across the latest retained snapshots. History is aggregate-only and contains no target, payload, or secret data.


### Operational health response

Control-plane health is an advisory, aggregate signal only. `HEALTHY`, `DEGRADED`, and `BLOCKED` never expand authorization, target scope, execution permissions, or worker capabilities. Operators should inspect the operations dashboard, health history, recovery readiness, queue-transition integrity, and aggregate alerts before declaring recovery. Ordinary failed jobs degrade service health; fail-closed blocking remains reserved for integrity/recovery conditions and persistent control-plane degradation.


### Platform SLO and error budgets

The control plane exposes read-only SLO/error-budget status through `GET /api/slo` and the operations dashboard. Current SLOs cover platform availability, queue integrity, terminal job reliability, recovery readiness, and reporting/outbox health.

Each SLO reports its target, observed ratio, error budget, budget consumed, remaining budget, burn rate, and state (`HEALTHY`, `AT_RISK`, or `EXHAUSTED`). The platform also computes historical 1h/24h/7d burn-rate windows from retained control-plane health snapshots. Multi-window alerting raises a critical fast-burn alert when both 1h and 24h consumption are elevated, and a warning for sustained 24h/7d slow burn. SLO state never changes scope, authorization, worker permissions, or execution behavior.


### Historical SLO burn-rate windows

The SLO layer computes read-only historical availability windows for `1h`, `24h`, and `7d` from retained control-plane health snapshots. Because health snapshots are deduplicated on state change, window observations are time-weighted rather than averaged by snapshot count.

Each historical window reports:

- `observed`
- `burn_rate`
- `budget_remaining`
- `samples`
- `covered_seconds`
- `window_seconds`
- `coverage_ratio`
- `boundary_state_known`
- `data_quality` (`complete`, `partial`, or `insufficient`)

A partial window is never presented as complete evidence. Historical windows remain advisory and do not alter worker execution, scope, authorization, or queue state.


### Multi-window SLO policy

Historical SLO windows feed one centralized, read-only multi-window policy. Fast burn requires complete `1h` and `24h` windows and burn rates of at least `2.0` and `1.0` respectively. Slow burn requires complete `24h` and `7d` windows with burn rates of at least `1.0` in both. Partial or insufficient windows are not evaluable and cannot trigger multi-window alerts.

The policy exposes `FAST_BURN`, `SLOW_BURN`, `HEALTHY`, or `UNKNOWN`, together with the evaluated windows and thresholds. Alerting consumes this centralized policy rather than duplicating threshold logic. It remains advisory-only and cannot mutate scope, authorization, queue state, or worker behavior.


### Report quality gate

Report readiness now feeds a separate advisory quality gate. Grades have stable semantics: `A` means submission-complete with consensus quorum, `B` means submission-complete with evidence-backed consensus, `C` means ready for human review but submission metadata remains incomplete, and `D` means human review is still blocked.

The quality gate combines evidence-backed validation, evidence quality, consensus, metadata completeness, duplicate review, and existing report-readiness state. Grade `B` is the minimum quality level for submission completeness, but no grade authorizes submission: explicit human approval remains mandatory and automatic submission remains disabled.


### Verified submission gate

The local submission governance gate now requires both current human approval and verified report quality coverage for every confirmed finding. Each covered finding must have grade `A` or `B`, be marked submission-ready, have complete report provenance, and pass independent provenance fingerprint verification.

A present-but-tampered provenance manifest is treated as invalid and blocks submission exactly like incomplete provenance. Missing quality coverage for any confirmed finding also blocks submission. This gate remains local and advisory to the submission workflow; external platform submission remains disabled by default.


### Approval provenance binding

Human report approval is bound to the aggregate fingerprint of the current report provenance set. The approval basis digest therefore covers the report artifact, submission-relevant campaign state, and the exact provenance fingerprints for confirmed findings.

If report provenance changes after approval, the approval becomes stale and submission state returns to `review_required` until a reviewer explicitly approves the new provenance-bound state. This behavior remains local to governance; it does not submit externally or mutate worker execution.


### Centralized reporting governance snapshot

Report readiness, provenance manifests, report quality gates, and the aggregate provenance fingerprint are now built through one shared read-only governance snapshot. The report-readiness API, campaign overview, approval flow, and submission flow consume this same canonical computation, reducing the risk of policy drift between reporting surfaces.

The snapshot remains advisory and deterministic. It does not approve reports, submit externally, mutate campaign state, or change worker execution.


### Submission event audit

The reporting workflow exposes a read-only submission-event audit for each report artifact:

```text
GET /api/campaigns/{campaign_id}/reports/{artifact_id}/submission-audit
```

The audit checks approval, revocation, and submission ordering and reports invalid sequences such as submission without an active approval or revocation without an active approval. It also exposes the latest approval provenance fingerprint for incident review. The audit never repairs, reorders, or mutates campaign events automatically.


### Submission integrity observability

Submission-event integrity is aggregated into `/api/metrics`, operational alerts, campaign overview, and the operations dashboard. Invalid report workflow sequences produce a warning and reduce only the reporting health component; they do not automatically hard-block the entire control plane.

This preserves the distinction between a reporting governance incident and a platform-wide recovery or queue-integrity failure.


### Submission audit fingerprints

Per-report submission audits use the canonical `submission-audit-v1` schema and include a deterministic SHA-256 fingerprint. The API also returns an independent verification result with expected/computed fingerprints and schema validity.

This allows operators to detect post-generation modification of audit results without changing campaign state or automatically repairing events.


### Aggregate submission audit fingerprints

Campaign-level and storage-wide submission-integrity summaries are now canonicalized and SHA-256 fingerprinted. Their fingerprints include the fingerprints of child report audits, allowing aggregate summaries to be independently verified and making post-generation modification detectable.

The operations dashboard exposes verification status for the storage-wide aggregate. Unsupported backends remain explicitly marked unsupported rather than being treated as integrity failures.


### Reporting governance fingerprint

The reporting governance snapshot now has a deterministic `reporting-governance-v1` fingerprint covering report readiness, provenance manifests, provenance-set fingerprint, and report quality gates. The campaign overview exposes both the fingerprint and an independent verification result.

This makes post-generation modification of the reporting-governance state detectable while keeping the entire layer read-only and advisory.
