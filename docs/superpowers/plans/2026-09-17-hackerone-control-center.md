# HackerOne Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-oriented, read-only HackerOne API control center that loads programs/scopes automatically and binds launch to an anti-drift remote snapshot without weakening the existing fail-closed launcher.

**Architecture:** Add a small HackerOne auth/transport layer beside the existing `hackerone_api.py`, normalize official Hacker API v1 responses into a deterministic snapshot, expose read-only local endpoints, then extend the current preview/launch contract with an optional remote snapshot binding. The frontend stays vanilla HTML/CSS/JS and reuses the current launcher flow.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, stdlib `urllib`, existing encrypted secret vault, vanilla JavaScript, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-hackerone-control-center-design.md`

## Global Constraints

- HackerOne credentials are server-side only and never returned by local APIs.
- HackerOne integration remains read-only in this tranche.
- No policy text is interpreted automatically as scanning permission.
- Unsupported/conflicting scope data fails closed.
- Existing manual StructuredScope mode remains supported.
- Destructive testing, DoS, social engineering, and credential attacks remain disabled.
- Remote-bound launch must fail on snapshot drift.
- HTTPS fixed origin only, redirects refused, timeout and response size bounded.

---

### Task 1: HackerOne credentials and hardened read transport

**Files:**
- Create: `backend/app/hackerone_client.py`
- Create: `backend/tests/test_hackerone_client.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `HackerOneClientError`, `HackerOneCredentials`, `load_hackerone_credentials()`, `HackerOneClient.get_json(path, query=None)`, `HackerOneClient.get_all_pages(path)`.
- Credentials resolve from vault names `hackerone_api_username`, `hackerone_api_token` and env names `XBOW_HACKERONE_API_USERNAME`, `XBOW_HACKERONE_API_TOKEN`.

- [ ] **Step 1: Write failing tests** for missing credentials, Basic auth header generation, fixed HTTPS origin, redirect refusal, bounded JSON response, and multi-page fetching.
- [ ] **Step 2: Push tests and verify GitHub Actions fails for missing production module.**
- [ ] **Step 3: Implement minimal hardened client** with stdlib `urllib.request`, no redirects, `Accept: application/json`, fixed `https://api.hackerone.com/v1`, timeout `XBOW_HACKERONE_TIMEOUT_SECONDS` default 10 (1..60), response cap `XBOW_HACKERONE_MAX_RESPONSE_BYTES` default 2 MiB (1 KiB..8 MiB), and at most 100 pagination pages.
- [ ] **Step 4: Verify targeted and full CI green.**
- [ ] **Step 5: Commit.**

### Task 2: Deterministic remote HackerOne snapshot

**Files:**
- Modify: `backend/app/hackerone_client.py`
- Create: `backend/tests/test_hackerone_remote_snapshot.py`

**Interfaces:**
- Produces: `HackerOneRemoteSnapshot` and `fetch_hackerone_program_snapshot(handle)`.
- Snapshot contains normalized program metadata, raw complete StructuredScope document, scope exclusions, local import preview data, and deterministic `snapshot_sha256`.

- [ ] **Step 1: Write failing tests** proving all scope pages are included, program handle validation is strict, normalized document is accepted by existing `import_hackerone_structured_scope`, and hash changes when program metadata/scope/exclusions change.
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement minimal snapshot builder** using official endpoints `/hackers/programs/{handle}`, `/structured_scopes`, `/scope_exclusions`; canonical JSON SHA-256; no credential leakage.
- [ ] **Step 4: Verify tests green.**
- [ ] **Step 5: Commit.**

### Task 3: Read-only local Control Center API

**Files:**
- Modify: `backend/app/hackerone_api.py`
- Create: `backend/tests/test_hackerone_control_center_api.py`

**Interfaces:**
- Produces GET routes:
  - `/api/imports/hackerone/connection`
  - `/api/imports/hackerone/programs`
  - `/api/imports/hackerone/programs/{handle}/snapshot`

- [ ] **Step 1: Write failing API tests** for configured status without secret exposure, normalized program list, snapshot response, upstream 401/403/429/transport failures mapped to safe 502/503 responses.
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement routes** using the client/snapshot layer and existing global `/api/*` authentication middleware.
- [ ] **Step 4: Verify API tests and OpenAPI integrity green.**
- [ ] **Step 5: Commit.**

### Task 4: Anti-drift binding on preview and launch

**Files:**
- Modify: `backend/app/hackerone_api.py`
- Modify: `backend/tests/test_hackerone_scope_preview_api.py`
- Modify: `backend/tests/test_hackerone_launch_api.py`

**Interfaces:**
- Extend `HackerOneRulesPreviewInput` with optional `remote_handle: str | None` and `remote_snapshot_sha256: str | None`.
- Preview returns `remote_binding` when supplied.
- Launch re-fetches the bound snapshot and raises HTTP 409 detail `{message, reason: "stale_hackerone_snapshot"}` when hashes differ.

- [ ] **Step 1: Write failing tests** for valid bound preview, incomplete binding rejection, mismatch between supplied document and remote snapshot rejection, launch drift rejection, and unchanged legacy manual mode.
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement binding validation and launch re-fetch.**
- [ ] **Step 4: Verify targeted HackerOne tests and full CI green.**
- [ ] **Step 5: Commit.**

### Task 5: Mobile-first HackerOne Control Center UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/hackerone.js`
- Modify: `frontend/app.css`
- Modify: `frontend/sw.js`
- Modify: `backend/tests/test_frontend_policy_launcher.py`

**Interfaces:**
- Add DOM IDs `h1ConnectionState`, `h1ProgramSearch`, `h1ProgramSelect`, `h1LoadProgram`, `h1ProgramMeta`, `h1RemoteFingerprint`, `h1ScopeTable`, `h1ScopeExclusions`.
- Existing `buildPayload()` includes `remote_handle` and `remote_snapshot_sha256` only when a remote program has been loaded.

- [ ] **Step 1: Write failing frontend contract tests** for the new controls and remote-bound payload behavior.
- [ ] **Step 2: Verify RED in CI.**
- [ ] **Step 3: Implement program discovery/load, searchable selector, normalized metadata/scope rendering, and snapshot invalidation on program/local policy changes.**
- [ ] **Step 4: Update responsive CSS and service-worker cache; run JS syntax checks via CI.**
- [ ] **Step 5: Verify full CI green.**
- [ ] **Step 6: Commit.**

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:**
- Document exact server-side HackerOne credential variables/vault names and the safe launch workflow.

- [ ] **Step 1: Document HackerOne API setup** without embedding credentials or suggesting client-side storage.
- [ ] **Step 2: Verify `ruff`, compile, JS syntax checks, pytest suite, Docker Compose config/build, security and supply-chain workflows through GitHub Actions.**
- [ ] **Step 3: Review branch diff for secret leakage and out-of-scope changes.**
- [ ] **Step 4: Open PR against `main` only after verification is green.**
