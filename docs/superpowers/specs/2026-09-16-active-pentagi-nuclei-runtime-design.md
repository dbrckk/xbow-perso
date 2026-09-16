# Active PentAGI + pinned Nuclei runtime design

Date: 2026-09-16
Status: design approved in chat; implementation pending written-spec review
Branch: `feat/active-pentagi-nuclei-runtime`
Base: `main` at `5dbcde974270c6cd576d8fc04f2b6a12d3b36ef4`

## 1. Goal

Make `xbow-perso` ready to run authorized bug-bounty campaigns with two execution paths:

1. a dedicated, reproducible Nuclei scanner runtime that can perform active scans only after all existing scope, sandbox, version, and rate-limit gates pass; and
2. an active PentAGI integration where PentAGI may plan and coordinate a campaign, but every network-affecting action remains mediated and authorized by XBOW.

The integration must preserve the repository's current fail-closed model. Enabling PentAGI must never mean that a language-model prompt becomes the security boundary.

## 2. Non-goals

This design does not enable destructive testing, denial-of-service, credential attacks, social engineering, persistence, stealth/evasion, mass scanning, or scope expansion.

It does not grant PentAGI unrestricted terminal, browser, raw-network, or shell access for bug-bounty flows.

It does not automatically import arbitrary HackerOne programs or infer permissions that are absent from a program policy.

It does not make ambiguous remote mutations retry automatically.

It does not make PentAGI a replacement for XBOW's policy engine, queue, evidence store, validator, or campaign state machine.

## 3. Security model

XBOW remains the policy enforcement point and execution authority.

PentAGI is an orchestration and reasoning component. It may request actions, inspect bounded results, and decide what to request next, but it must not independently create network traffic against the target outside XBOW-controlled workers.

For every externally visible action, XBOW must re-evaluate the current campaign state and policy immediately before queueing or executing work. A stale PentAGI plan is not sufficient authorization.

The effective authorization chain is:

`program policy -> XBOW campaign rules -> policy fingerprint -> action request -> current-policy revalidation -> bounded job -> dedicated worker -> evidence -> validation`

The following invariants are mandatory:

- target host is in `allowed_targets` and not in `denied_targets`;
- `automated_scanning` is explicitly enabled;
- destructive, DoS, social-engineering, and credential-attack flags are false;
- campaign is not cancelled or terminally failed;
- requested rate is positive and no higher than both the campaign policy and XBOW's local admission ceiling;
- the requested operation maps to a known XBOW capability;
- all action payloads are server-constructed or server-normalized; PentAGI cannot pass arbitrary command lines;
- no arbitrary URL may be used as an XBOW callback or PentAGI endpoint;
- secrets remain server-side and are never returned to PentAGI;
- ambiguous mutating remote operations are reconciled, not blindly retried.

## 4. Nuclei runtime architecture

### 4.1 Dedicated image

The general backend image remains focused on the API and non-scanner workers.

Add a scanner-specific Docker image, for example `backend/Dockerfile.scanner`, and point the `scanner-worker` Compose service at it. This image is the only image required to contain Nuclei.

This preserves the current scanner isolation model and avoids increasing the attack surface of the API and general worker images.

### 4.2 Version pinning

Pin Nuclei to `v3.11.1`.

The image build must:

- download the architecture-appropriate official release asset;
- verify the asset against a hard-coded SHA-256 copied from the official release metadata/checksum file;
- fail the build on checksum mismatch;
- install the binary to a fixed path on `PATH`;
- run `nuclei -version` as a build-time smoke check.

No `latest` download, Go install from a moving branch, or runtime self-update is allowed.

### 4.3 Template pinning

Pin `nuclei-templates` to `v10.4.8`.

The scanner image should contain a read-only preloaded template tree or an equivalent immutable artifact. The worker must pass the explicit template directory to Nuclei and keep update checks disabled.

The runtime must not silently download new templates during a scan. Template changes require an explicit repository change and normal CI review.

### 4.4 Runtime attestation

Reuse and strengthen the existing `XBOW_NUCLEI_ALLOWED_VERSION` gate.

Active execution requires all of:

- `DRY_RUN=false`;
- `XBOW_ENABLE_ACTIVE_SCANS=true`;
- `XBOW_ENABLE_SCANNER_WORKER=true`;
- `XBOW_ENABLE_NUCLEI=true`;
- `XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1`;
- `nuclei` in `XBOW_SCANNER_ALLOWED_ENGINES`;
- sandbox runtime attestations for read-only root filesystem, `no-new-privileges`, and all capabilities dropped;
- exact expected Nuclei version;
- expected pinned template version or manifest fingerprint.

If any value is missing, malformed, or mismatched, active execution remains blocked.

### 4.5 Nuclei command contract

The worker must continue constructing the command itself. Campaign or PentAGI input cannot inject raw Nuclei flags.

The existing conservative properties remain required:

- HTTP-oriented scan mode only for the first active release;
- low concurrency and bulk size;
- explicit request-rate limiting;
- no unsigned templates;
- no Interactsh in the initial active path;
- local-network access restricted;
- redirects disabled unless a future reviewed policy explicitly supports them;
- retries bounded;
- update checks disabled;
- output written only under the configured run root;
- unsafe/fuzz/DoS categories excluded.

If the pinned template set introduces tags or behavior incompatible with the allowed policy, the scanner admission layer must block rather than broaden execution.

## 5. PentAGI integration architecture

### 5.1 Role separation

PentAGI becomes a planner/orchestrator for authorized campaigns, not a direct executor of arbitrary target actions.

For XBOW-managed bug-bounty flows, PentAGI's built-in direct execution tools that can bypass XBOW policy must be disabled. In particular, terminal/shell and unrestricted browser/network execution must not be available to the flow.

PentAGI receives only a constrained set of XBOW-backed external functions.

### 5.2 Transport contract

Replace the current minimal GraphQL `createFlow` execution plan with the currently supported PentAGI flow-creation contract that can carry an explicit `functions` configuration.

Keep HTTPS-only endpoint validation, no redirects, bounded response size, bounded total deadline, no credentials in URL, exact expected API path, and server-side token loading.

Do not support arbitrary PentAGI base URLs per campaign. The endpoint remains server configuration.

### 5.3 XBOW functions exposed to PentAGI

Initial external function surface:

- `request_recon`
- `request_nuclei_scan`
- `request_validation`
- `get_job_status`
- `get_campaign_summary`
- `get_findings`

Every mutating function returns a durable XBOW job identifier or a deterministic deduplication result. Read functions return bounded, redacted JSON.

No generic `run_command`, `fetch_url`, `browser_action`, `raw_http`, `shell`, or arbitrary scanner-flag function is exposed.

### 5.4 Flow binding

Create a durable server-side PentAGI flow binding containing at minimum:

- XBOW campaign ID;
- PentAGI flow ID;
- immutable integration/binding ID;
- policy fingerprint at creation;
- PentAGI endpoint identity;
- model provider;
- creation timestamp;
- status;
- deterministic idempotency key;
- latest reconciled remote status.

The value PentAGI uses when calling an XBOW function must be an opaque binding token or server-authenticated identity, not a user-guessable campaign ID that can be substituted to cross campaign boundaries.

XBOW resolves the binding to the campaign server-side and verifies that the binding is still active before processing every function request.

### 5.5 Action authorization

Each PentAGI-requested action is normalized into an internal XBOW action request.

For a mutating action, XBOW must:

1. authenticate the PentAGI integration channel;
2. resolve the flow binding;
3. load the latest campaign record;
4. reject cancelled/completed/failed campaigns where appropriate;
5. recompute the current policy fingerprint;
6. validate target/scope and action type;
7. clamp or reject rate values against campaign and local caps;
8. build the worker payload internally;
9. enqueue with a deterministic dedupe key;
10. return a bounded status object.

A PentAGI request must not contain an arbitrary executable command.

### 5.6 Rate enforcement

A rate limit written into a prompt is advisory only and is not accepted as enforcement.

XBOW remains responsible for hard rate enforcement at worker-plan construction and admission.

For Nuclei, the effective request rate is `min(requested_rate, campaign_policy_rate, local_autonomy_cap)` and must still satisfy the existing worker rules. Prefer rejection when PentAGI requests a rate higher than policy rather than silently hiding a policy error.

Recon and validation use their existing XBOW-specific ceilings in addition to the campaign policy.

PentAGI itself must not receive a generic direct-network tool that can evade those limits.

### 5.7 Cancellation and stop propagation

When an XBOW campaign is cancelled:

- new PentAGI action requests fail closed;
- queued XBOW jobs follow the existing cancellation semantics;
- XBOW sends an explicit stop request to the bound PentAGI flow when the remote API supports it;
- the stop operation is idempotent/reconcilable;
- failure to confirm remote stop is surfaced as an operational alert and does not re-enable local execution.

The status poller keeps reconciling the remote state until a terminal remote state or a configured reconciliation deadline is reached.

### 5.8 Remote create idempotency and ambiguous failure

Preserve the current rule that the mutating remote flow creation is not automatically retried after an ambiguous transport failure unless PentAGI documents a server-side idempotency mechanism that XBOW can verify.

XBOW keeps a deterministic local idempotency key and stores enough information to reconcile whether a flow was created.

If the HTTP result is ambiguous, the job enters a distinct reconciliation/manual-review state rather than simply running `createFlow` again.

### 5.9 PentAGI status and results

The existing dedicated status worker remains separate from the creator worker.

Remote status is treated as untrusted external state and normalized before use.

PentAGI outputs do not become confirmed findings directly. Any candidate finding must pass through XBOW normalization, evidence storage, deduplication, and the existing validation/review lifecycle.

## 6. Authentication and secrets

PentAGI API credentials remain available only to server-side PentAGI workers and preferably come from the encrypted XBOW vault.

The new XBOW external-function endpoint used by PentAGI needs a separate integration credential from the human-facing `XBOW_API_TOKEN`.

The credential must be:

- generated with high entropy;
- stored server-side in XBOW/PentAGI configuration, never in campaign data;
- compared in constant time;
- redacted from logs and error messages;
- rotatable without changing campaign IDs;
- optionally stored in the existing XBOW vault.

Function requests additionally require the flow binding, so possession of the integration token alone does not select an arbitrary campaign.

If future PentAGI releases support request signing, XBOW may add HMAC request signatures and replay protection. This is not required for the first active implementation if the integration is HTTPS-only, token-authenticated, and bound per flow, but the interface must not prevent adding signatures later.

## 7. Data model and persistence

Add a persistence abstraction for PentAGI bindings rather than storing them only in process memory.

The binding record must support both SQLite and distributed/PostgreSQL storage paths used by XBOW.

Required operations:

- create binding idempotently;
- resolve binding by opaque integration identifier;
- find by campaign ID;
- update normalized remote status with optimistic/version-aware persistence where the storage backend supports it;
- mark stop requested/confirmed;
- store reconciliation error metadata without secrets.

Do not persist PentAGI API tokens or LLM provider secrets in the binding record.

## 8. Capability reporting

`GET /api/capabilities` must stop reporting PentAGI as `preview_only` only when every required active contract is satisfied.

Active PentAGI capability requires at minimum:

- PentAGI enabled;
- active scans enabled;
- global dry-run disabled;
- worker enabled;
- reviewed transport enabled;
- external XBOW function channel configured;
- direct bypass-capable PentAGI tools disabled for XBOW flows;
- persistent binding storage available;
- the current PentAGI API contract matches the implementation;
- rate and scope enforcement remain XBOW-side.

Capability output must expose non-secret block reasons for every missing gate.

Nuclei capability reporting must similarly expose version/template/runtime block reasons without leaking host secrets.

## 9. Failure handling

### 9.1 Nuclei

- missing binary: fail closed;
- wrong version: fail closed;
- wrong/missing template manifest: fail closed;
- sandbox attestation mismatch: fail closed;
- result parser failure: preserve artifacts and mark job failed; do not invent findings;
- worker crash: existing lease/recovery rules apply only where retry is safe.

### 9.2 PentAGI

- create-flow definite rejection: mark failed with redacted reason;
- create-flow ambiguous timeout/I/O result: mark reconciliation-required, no blind retry;
- flow binding mismatch: reject and audit;
- stale policy fingerprint: reject and require a new decision/action request;
- campaign cancellation: reject new actions and request remote stop;
- malformed external function request: reject before queue mutation;
- remote status malformed: fail closed and retain previous known-good normalized state;
- PentAGI-generated finding without XBOW evidence: never mark confirmed.

## 10. Audit and observability

Record structured audit events for:

- PentAGI flow admission;
- flow creation requested;
- flow creation confirmed;
- ambiguous create requiring reconciliation;
- binding created;
- PentAGI action requested;
- action admitted/denied with non-secret policy reason;
- campaign policy changed while a flow is active;
- PentAGI stop requested/confirmed/failed;
- Nuclei runtime attested;
- scanner execution admitted/denied;
- pinned-template manifest verified/mismatched.

Metrics should include counts and age for unresolved PentAGI reconciliation items and scanner runtime failures.

Logs must not contain PentAGI tokens, LLM keys, browser secrets, TOTP secrets, raw authorization headers, or unrestricted response bodies.

## 11. Deployment changes

### 11.1 Compose

`scanner-worker` uses the dedicated scanner Dockerfile/image.

PentAGI creator and status worker remain behind explicit Compose profiles.

The active configuration requires explicit environment gates. Safe defaults stay disabled in `.env.example`.

Add only the minimum new environment values required, expected to include equivalents of:

- pinned Nuclei version;
- pinned Nuclei template version/manifest;
- PentAGI function integration token or vault key name;
- XBOW callback/base URL reachable from PentAGI if external functions are configured by URL;
- PentAGI active-contract flag/version marker if needed for compatibility checks.

All defaults remain fail closed.

### 11.2 Network topology

Prefer a private/container network path for PentAGI -> XBOW external-function calls when PentAGI is deployed alongside XBOW.

Do not expose the external-function endpoint publicly unless deployment topology requires it. If public reachability is required, TLS and the dedicated integration authentication are mandatory.

The target-facing workers remain isolated from the control-plane path according to the existing network model.

## 12. Testing strategy

Implementation follows TDD.

### 12.1 Nuclei tests

Add tests proving:

- scanner Dockerfile pins the exact Nuclei release and expected checksum;
- template release is pinned and update-at-runtime is disabled;
- scanner Compose service uses the dedicated image/build target;
- runtime attestation accepts exactly the configured release and rejects mismatches;
- active Nuclei refuses execution without all gates;
- active command contains the required conservative flags and explicit template path;
- rate enforcement cannot exceed campaign/local policy;
- dry-run path remains safe and unchanged;
- a container smoke check can run `nuclei -version` without target network activity.

### 12.2 PentAGI unit tests

Add tests proving:

- flow creation payload disables bypass-capable direct tools and contains only reviewed XBOW functions;
- arbitrary functions cannot be injected through campaign/user data;
- every action revalidates the current policy fingerprint;
- opaque binding cannot be used for another campaign;
- cancelled campaigns reject new actions;
- target/rate/action type are enforced server-side;
- arbitrary commands/URLs are rejected;
- secrets are absent from persisted binding and responses;
- duplicate action requests dedupe safely;
- ambiguous flow creation is not auto-retried;
- stop propagation is idempotent;
- unvalidated PentAGI output cannot produce a confirmed finding.

### 12.3 Integration tests

Use a local fake PentAGI HTTP service or deterministic mocked transport in CI; CI must not contact real external targets.

Exercise:

1. create authorized XBOW campaign;
2. create PentAGI flow;
3. persist binding;
4. PentAGI requests a bounded Nuclei action;
5. XBOW creates the exact internal scan job;
6. simulated scanner result is ingested;
7. PentAGI reads bounded findings/status;
8. campaign cancellation causes subsequent action denial and remote-stop request.

No CI test may perform an active scan of a third-party host.

### 12.4 Regression gate

Before PR readiness:

- full backend pytest suite passes;
- Ruff passes;
- frontend JS syntax checks pass if frontend files change;
- Docker Compose config validates;
- scanner image builds;
- Nuclei version smoke test passes;
- security workflow passes;
- supply-chain workflow passes;
- release/deployment preflight tests stay green.

## 13. Implementation boundaries and likely files

Expected existing files to modify:

- `backend/Dockerfile` only if common build stages are intentionally shared;
- new `backend/Dockerfile.scanner`;
- `docker-compose.yml`;
- `.env.example`;
- `backend/app/worker.py`;
- `backend/app/scanner_sandbox.py` and/or `backend/app/runtime_capabilities.py`;
- `backend/app/pentagi_adapter.py`;
- `backend/app/pentagi_admission.py`;
- `backend/app/pentagi_execution_guard.py`;
- `backend/app/pentagi_dispatch.py`;
- `backend/app/pentagi_transport.py`;
- `backend/app/pentagi_worker_service.py`;
- `backend/app/pentagi_status_worker_service.py` / status modules as required;
- storage abstraction/implementations for flow bindings;
- `backend/app/main.py` or a focused PentAGI integration API router;
- capability reporting and readiness code;
- tests for each changed contract;
- README/deployment docs after behavior is verified.

Prefer adding focused modules for binding and external-function policy rather than expanding already-large files such as `main.py` or `worker_service.py`.

## 14. Rollout sequence

Implementation should be split into reviewable, independently safe increments on one feature branch or a small PR series:

1. pinned Nuclei scanner image + build/runtime attestation;
2. PentAGI REST/function-capable transport contract while still fail-closed;
3. persistent flow binding + dedicated integration authentication;
4. XBOW external-function endpoint with read-only functions first;
5. bounded mutating functions backed by existing XBOW queues;
6. active PentAGI admission gate switched from preview-only only after the preceding contracts are verified;
7. cancellation/stop/reconciliation handling;
8. end-to-end fake-PentAGI integration test and docs.

At no intermediate commit should setting a single flag accidentally enable unrestricted PentAGI execution.

## 15. Acceptance criteria

The feature is complete only when all of the following are true:

- the scanner worker image contains the exact pinned Nuclei binary and templates with verified integrity;
- `GET /api/capabilities` reports Nuclei executable only when runtime/version/template/sandbox gates all pass;
- PentAGI can create a real flow using the reviewed API contract;
- the XBOW-managed flow has no bypass-capable direct execution tools;
- PentAGI can request recon, Nuclei scanning, validation, and read status/findings only through XBOW functions;
- every mutating request is re-authorized against current policy and campaign state;
- rate limits are enforced by XBOW workers, not only described in prompts;
- flow-to-campaign binding prevents cross-campaign substitution;
- campaign cancellation blocks new PentAGI actions and propagates a remote stop request;
- ambiguous remote creation never causes an automatic duplicate-flow retry;
- findings remain evidence-backed and pass XBOW's validation lifecycle;
- safe defaults remain disabled in a fresh deployment;
- full CI/security/supply-chain checks pass.

## 16. Safety rationale

The previous preview-only PentAGI state was correct because the local code could not prove downstream enforcement after handing control to PentAGI.

This design resolves that limitation by changing the trust boundary rather than merely changing the flag: PentAGI is allowed to decide which approved XBOW capability to request, while XBOW retains authority over whether, where, and how that capability executes.

That preserves the fail-closed model even if PentAGI produces incorrect, stale, or adversarial instructions.