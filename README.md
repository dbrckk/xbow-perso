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
