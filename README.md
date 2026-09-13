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
      +-- PentAGI (guarded execution + status tracking)
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

PentAGI execution is split into two dedicated services so remote flow creation never blocks generic scanning workers:

- `pentagi-worker`: creates one admitted remote flow after policy/permit revalidation.
- `pentagi-status-worker`: tracks only already-created flows through bounded read-only polling.

All PentAGI switches default to disabled, and the dedicated containers are behind Compose profiles so a normal `docker compose up` does not start them. To enable execution deliberately, configure the PentAGI endpoint/provider and credentials, enable `XBOW_ENABLE_PENTAGI`, `XBOW_ENABLE_PENTAGI_WORKER`, and `XBOW_ENABLE_PENTAGI_TRANSPORT`, then start the `pentagi` profile. Enable `XBOW_ENABLE_PENTAGI_STATUS_WORKER` and the `pentagi-status` profile separately for lifecycle tracking.

Example:

```bash
docker compose --profile pentagi --profile pentagi-status up -d --build
```
