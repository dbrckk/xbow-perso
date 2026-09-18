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
