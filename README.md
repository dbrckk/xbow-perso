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

**Android-only operation:** see [`MOBILE_ONLY.md`](MOBILE_ONLY.md) for the smartphone-only VPS workflow and GitHub Actions deployment path. For the recommended AWS EC2 path, see [`AWS_MOBILE_ONLY.md`](AWS_MOBILE_ONLY.md).

### Interface graphique

The graphical interface is the responsive PWA served by the frontend container on port **8080**:

- same machine: `http://localhost:8080`
- phone on the same LAN: `http://<LAN_IP_OF_SERVER>:8080`
- remote VPS/server: expose it behind an HTTPS reverse proxy and open the configured HTTPS origin.

The HackerOne launcher, connection state, live-readiness preflight, scope/policy review, run monitor, findings review, reports, remote status and attention center all live in this single interface. The **Pré-vol bug bounty réel** panel also displays the exact browser origin currently in use.

The default configuration uses `DRY_RUN=true`; external testing engines are not launched until you explicitly configure them.

### Preparing a real HackerOne run

For the step-by-step operator checklist, see `FIRST_REAL_HACKERONE_RUN.md`. The same manual steps are also rendered inside the **Pré-vol bug bounty réel** panel in the PWA.

Keep the safe defaults until you have selected a specific program and manually reviewed its current policy. The read-only endpoint `GET /api/hackerone/live-readiness` and the matching UI panel expose the non-secret gates.

For the current pinned scanner image, a live Nuclei run requires all of the following server-side conditions:

```bash
XBOW_ENABLE_ACTIVE_SCANS=true
DRY_RUN=false
XBOW_ENABLE_NUCLEI=true
XBOW_NUCLEI_ALLOWED_VERSION=3.11.1
XBOW_SCANNER_ALLOWED_ENGINES=nuclei
XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1
```

The dedicated scanner worker must also be running:

```bash
docker compose --profile scanner up -d --build
```

Do **not** enable those switches merely because the platform is technically ready. In the HackerOne launcher, first load the exact program, review its current scope/policy, explicitly confirm Safe Harbor/authorization, confirm that automated scanning is permitted, enter the exact request-rate ceiling, review account constraints/exclusions, preview the executable rules, and only then launch.

Direct HackerOne submission remains independently gated by `XBOW_ENABLE_HACKERONE_SUBMISSION=true` and is **not required** for a first real scan. The historical report-sync worker is also optional and can be enabled later.

## HackerOne Control Center

The PWA loads HackerOne programs and complete StructuredScope data through the server-side Hacker API client. Discovery is read-only by default. Optional direct report creation is separately gated and remains disabled unless `XBOW_ENABLE_HACKERONE_SUBMISSION=true` is explicitly configured.

Configure HackerOne credentials only on the server:

```bash
XBOW_HACKERONE_API_USERNAME=YOUR_HACKERONE_API_IDENTIFIER
XBOW_HACKERONE_API_TOKEN=YOUR_HACKERONE_API_TOKEN
```

When `XBOW_VAULT_ENABLED=true`, store the same values as vault entries `hackerone_api_username` and `hackerone_api_token` and leave the legacy environment variables unset. Vault mode refuses environment fallback if either vault entry is unavailable.

Safe launch workflow:

1. authenticate to the xbow-perso control plane with `XBOW_API_TOKEN` (and TOTP when enabled);
2. select and load a HackerOne program in the Control Center, or keep using the manual StructuredScope importer;
3. review the loaded policy and scope; the UI never infers permission to automate scanning from free-form policy text;
4. explicitly confirm Safe Harbor/authorization, automated scanning permission, the exact program request-rate ceiling and any account/restriction requirements;
5. preview the executable rules;
6. confirm the preview and launch only if the conservative admission gates remain green.

Remote-bound previews carry a deterministic SHA-256 snapshot of the program metadata, complete scope and exclusions. Launch re-fetches HackerOne before campaign creation. If the remote snapshot changed after review, xbow-perso returns `409 stale_hackerone_snapshot` and requires a fresh review. Unsupported or conflicting scope data remains fail-closed.

The HackerOne API timeout defaults to 10 seconds and its bounded response size to 2 MiB; see `.env.example` for `XBOW_HACKERONE_TIMEOUT_SECONDS` and `XBOW_HACKERONE_MAX_RESPONSE_BYTES`.

Direct HackerOne submission is fail-closed: it requires a current human approval of the exact integrity-verified report artifact, a verified remote program binding, exactly one confirmed finding, an explicit UI confirmation, and the server-side `XBOW_ENABLE_HACKERONE_SUBMISSION=true` gate. The approved report bytes are sent as the report body. Ambiguous transport failures are recorded and automatic retry is blocked to avoid duplicate HackerOne reports.


After a successful direct submission, the Control Center can read the remote report with HackerOne's `GET /v1/hackers/reports/{id}` endpoint. The local API exposes only bounded operational fields (remote report ID, program handle, state, and activity/triage/closure timestamps); report content, relationships, attachments, and user data are intentionally omitted. This status lookup is read-only and does not mutate the campaign audit log.


Optional historical synchronization is provided by the separate `hackerone-report-sync-worker` Compose service. It is disabled by default. Enable it with `XBOW_ENABLE_HACKERONE_REPORT_SYNC=true` and start the `hackerone-sync` profile. Each cycle examines only the configured number of recent campaigns, fetches only reports that already have an audited remote HackerOne report ID, and appends a sealed `hackerone_report_status_synced` event only when tracked state/timestamps changed. The default interval is 60 seconds and the default campaign bound is 100.


When HackerOne returns a public `activity-bug-needs-more-info` activity on a submitted report, the sync worker records a bounded `hackerone_needs_more_info_observed` audit event once per activity ID. The Control Center exposes the public request and generates a local deterministic response draft from already-confirmed findings and stored validation context. The draft endpoint is read-only and explicitly reports `send_supported=false`; no HackerOne reply/comment mutation is implemented by this feature.


The same report response is also reduced to an allowlisted public activity feed for `activity-comment`, `activity-bounty-awarded`, `activity-bug-duplicate`, `activity-bug-informative`, and `activity-bug-resolved`. Internal activities, actors, attachments, and unknown activity types are discarded. The worker records each accepted activity ID once as `hackerone_public_activity_observed`; the Control Center renders these together with synchronized report-state changes and NMI requests in a local timeline and compact activity summary.


The HackerOne attention center is a local-only index over recent stored campaigns. It does not query HackerOne when opened. Reports are grouped by current synchronized state into action-required (`needs-more-info` or `retesting`), active (`new`, `pending-program-review`, `triaged`), awaiting-sync, resolved, duplicate, informative, and other closed states. Bounty observations remain badges/metadata rather than replacing the report's current state. The UI refreshes the local index every 15 seconds and can open the corresponding local campaign monitor.


Each attention item also exposes a stable SHA-256 notification cursor derived only from bounded local event identity/timestamp fields. The browser stores only the report key and last-seen cursor under `xbow:hackerone:attention-seen:v1`; it does not persist report bodies, comments, NMI text, bounty details, credentials, or HackerOne user data. The first load establishes a baseline, later cursor changes become unread, and the operator can mark one item or all items as seen. Opening a report also marks its current cursor as seen. If browser storage is unavailable, the UI falls back to in-memory seen state for the current page session.


The attention table can be filtered entirely in the browser without extra API calls: free-text search, seen/unseen state, priority bucket, program handle, exact synchronized report state, bounty presence, and recency windows (24 hours, 7 days, 30 days). It can be sorted by backend priority, newest/oldest observation, program, or state. Global counters remain unfiltered while a separate result count shows how many reports match the current view. On narrow screens the existing responsive filter grid collapses to a single column.


The browser also persists the last attention-filter configuration under `xbow:hackerone:attention-filters:v1` and restores it after dynamic program/state options are rebuilt. This preference state contains only search/filter/sort values. Built-in saved-view shortcuts apply transparent filter combinations for **À traiter**, **Nouveaux aujourd’hui**, **Avec bounty**, **NMI**, and **Non lus**; selecting or editing any field immediately returns to a custom view when it no longer matches a preset. The `today` view uses the browser's local calendar date rather than a rolling 24-hour window.


Bulk actions operate only on the currently filtered/sorted local view. The operator can mark every visible unread item as seen, open the next visible `action-required` report in sequence (wrapping at the end), and export the visible view to JSON or CSV. Export rows intentionally contain only operational summary fields: campaign id/name, program handle, remote report id, current state/bucket, action-required flag, bounty amount/bonus, last observation timestamp, unread flag, and notification kind. NMI/comment text, report bodies, credentials, user data, and internal notification cursors are excluded.


Named custom attention views are stored locally under `xbow:hackerone:attention-custom-views:v1`. The operator can save the current filter/search/sort configuration under a name, re-apply it later, replace an existing view with the same name, or delete it. Custom view names are normalized and capped at 60 characters; at most 20 custom views are retained. Stored custom views contain only validated filter preference fields and never contain report bodies, NMI/comment text, credentials, user data, or notification cursors. Built-in presets remain immutable and separate from user-defined views.

## Target memory and recon graph

xbow-perso now exposes a bounded, read-only cross-campaign memory for the same authorized target through `GET /api/campaigns/{campaign_id}/target-memory`.

The memory aggregates only passive surface observations (`asset`, `endpoint`, `form`, `technology`, `waf`), tracks first/last observation, campaign frequency and source, and computes a deterministic delta against the previous campaign. It is isolated by the primary target host **and** authorization reference so unrelated programs that happen to share infrastructure do not silently share memory.

This layer is advisory only: historical observations never authorize a scan, never bypass scope review and never modify campaign admission. The dashboard renders the current surface and the added/removed delta after a campaign is loaded.

Bound the memory explicitly with:

```bash
XBOW_TARGET_MEMORY_MAX_CAMPAIGNS=50
XBOW_TARGET_MEMORY_MAX_NODES=5000
```

## Recon surface diff intelligence

The target-memory layer also exposes `GET /api/campaigns/{campaign_id}/surface-diff`, a bounded read-only comparison against the previous campaign for the same target + authorization identity.

It classifies added and removed assets, endpoints, forms, technologies and WAF observations, produces a deterministic change score, and highlights newly observed assets/endpoints/forms for operator review. This is advisory only: the diff never expands scope, never authorizes scanning and never influences execution admission.

The dashboard renders the change score and focus set inside **Mémoire de cible** after loading a campaign.

## Diff-prioritized recon

The recon planner can now use the read-only surface diff as a bounded ordering signal. The prioritizer receives only tasks that have already passed normal scope-aware planning and may change **priority/reason only**.

It is explicitly forbidden from creating tasks, rewriting targets, increasing request budgets, changing HTTP methods, or expanding scope. Newly observed endpoints/forms/assets can therefore make an already-authorized recon task run earlier, but they cannot create authority that did not already exist.

The advisory recon-plan endpoint exposes the audit metadata as `diff_priority`; orchestrated campaigns use the same bounded ordering before shared swarm budgets are allocated.

## Historical recon scoring

Diff-prioritized recon also uses bounded historical frequency from Target Memory. Newly observed surface receives a small novelty bonus, while an item that has appeared in many prior campaigns contributes progressively less historical weight.

Historical scoring is intentionally weak relative to the current surface diff: the diff component is capped at +15 priority points, historical novelty at +5, and the combined ordering boost at +20. This still changes **ordering only**. It cannot create tasks, increase request budgets, rewrite targets, change allowed methods, or expand scope.

## Temporal surface profile

The campaign dashboard and API now expose a bounded temporal profile through `GET /api/campaigns/{campaign_id}/surface-temporal`.

For campaigns sharing the same target + authorization identity, xbow classifies observed surface as `stable`, `new`, `returning`, `intermittent`, `disappeared`, or `historical`. It also tracks presence ratio and appearance/disappearance transitions so recurring deployment noise can be distinguished from genuinely new surface.

Only campaigns at or before the selected campaign timestamp are considered, preventing later observations from leaking into historical views. The profile is read-only and has no execution influence: it cannot expand scope, create recon tasks, alter request budgets, or authorize scanning.

## Temporal novelty scoring

The recon prioritizer can now use the temporal surface profile as a weak ordering signal. A surface that has never been observed before receives more attention than a returning or intermittent element that regularly appears and disappears across campaigns.

The temporal component is deliberately bounded: it contributes at most +5 priority points and the combined diff + historical + temporal boost remains capped at +20. Stable, disappeared and historical-only surface contributes no temporal novelty boost.

As with the other recon intelligence layers, this changes ordering only. It cannot create tasks, rewrite targets, increase request budgets, change allowed methods, expand scope, or authorize execution.

## Surface confidence scoring

The API exposes `GET /api/campaigns/{campaign_id}/surface-confidence`, a read-only reliability score for observed surface nodes.

Confidence combines three bounded signals: source diversity, repetition across campaigns, and temporal persistence. Nodes observed by several independent sources and repeatedly across campaigns score higher than one-off observations from a single source. The dashboard shows high/medium/low confidence counts and highlights low-confidence observations that still need corroboration.

This is descriptive only: confidence never changes scope, authorization, task creation, request budgets, or execution admission.

## Confidence-aware recon ordering

The recon prioritizer can now use surface confidence as a **damping signal**. High-confidence observations preserve the full bounded diff/history/temporal ordering boost, while low-confidence observations reduce that boost instead of amplifying uncertain data.

The confidence factor is bounded between 0.5 and 1.0. It never creates additional priority above the existing +20 global cap and cannot create tasks, rewrite targets, change methods, increase request budgets, expand scope, or authorize execution. Missing confidence data is neutral rather than permissive.

## HackerOne quick start

The HackerOne launcher includes an express-start profile for repeated bounty work. After a program policy/scope has been reviewed and accepted once, the non-secret review settings can be remembered locally **only for that exact HackerOne snapshot fingerprint**. If HackerOne changes the policy, scope or exclusions, the fingerprint changes and the launcher requires a fresh review instead of silently reusing the old authorization assumptions.

The express flow can restore the reviewer, verified rate limit, policy reference/date, automation/Safe Harbor confirmations, account constraints, notes and preferred primary URL. Compatible exact-domain/URL targets are also offered as browser suggestions. Secret credentials remain server-side in the encrypted vault.

For repeat work, the browser can also remember the last selected HackerOne program, reload it automatically after API authentication, and automatically rerun the read-only rules preview when the exact saved fingerprint is unchanged. Advanced first-review controls collapse automatically for a reused profile. Human confirmation and the final launch remain explicit actions.

## Vault migration

Legacy server-side credentials can be moved into the encrypted vault with the redacted migration workflow documented in [VAULT_MIGRATION.md](VAULT_MIGRATION.md). The CLI also supports a private source env file for containerized/mobile cutovers, so legacy values do not need to be copied into the shell. The migration never prints secret values, verifies every encrypted write before legacy cleanup, and keeps vault enablement as a separate fail-closed cutover step.

## Production migration

Existing single-node SQLite installations can be migrated to PostgreSQL + Redis with the controlled migration CLI documented in [PRODUCTION_MIGRATION.md](PRODUCTION_MIGRATION.md).

The migration performs a redacted plan first, refuses running source jobs or non-empty targets, verifies artifact hashes, creates a private SQLite backup, preserves queue history/dedupe state, and leaves the source database unchanged.

## Production hardening preflight

`GET /api/deployment/preflight` now treats `XBOW_DEPLOYMENT_ENV=production` as a strict fail-closed contract. In addition to digest-pinned backend/frontend images, production mode requires PostgreSQL metadata storage, a Redis queue, Redis-backed API rate limiting, and the encrypted vault with a master-key **file** source.

The preflight reports only redacted configuration state; it never returns database URLs, Redis URLs, vault paths, key material, or credentials.

Required production posture:

```bash
XBOW_DEPLOYMENT_ENV=production
XBOW_STORAGE_BACKEND=postgresql
XBOW_QUEUE_BACKEND=redis
XBOW_API_RATE_LIMIT_ENABLED=true
XBOW_API_RATE_LIMIT_BACKEND=redis
XBOW_VAULT_ENABLED=true
XBOW_VAULT_MASTER_KEY_FILE=/run/secrets/xbow_vault_master_key
```

Inline `XBOW_VAULT_MASTER_KEY` is rejected by production preflight. The distributed Compose overlay now enables Redis-backed API rate limiting automatically; vault migration remains an explicit operator step so existing credentials are never silently moved or lost.

Keep `DRY_RUN=true` and active scanner switches disabled while migrating storage/secrets. Production hardening does not imply permission to test any target.

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

The manifest stores only filenames, sizes, and SHA-256 hashes; it never embeds backup contents or decrypted secrets. When `XBOW_AUDIT_HMAC_KEY` (or the `audit_hmac_key` vault entry) is available, the manifest is also authenticated with HMAC-SHA256 so manifest rewriting is detectable.

## Safety model

A campaign must include written authorization metadata, allowed targets and prohibited actions. Requests outside the declared scope are rejected by the API before reaching a worker. This is an engineering control, not a substitute for the rules of the bug bounty program.

## Roadmap

Implemented foundations include PostgreSQL storage, Redis-backed queues, encrypted secret vault, recon graph/target memory, evidence artifacts, audit receipts, TLS deployment hardening, HackerOne program import, and TOTP-backed control-plane authentication.

Remaining major work:

- production migration/runbook automation and tested restore drills
- real Strix job lifecycle + result parser
- enforceable PentAGI remote execution contract
- Playwright browser worker hardening and authenticated-flow UX
- stronger CVSS/CWE normalization and report metadata assistance
- WebAuthn/passkeys and multi-user roles
- Prometheus/Grafana observability and alert routing
- signed/pinned production image release workflow


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
