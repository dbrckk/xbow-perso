# Nuclei + PentAGI Controlled Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pinned Nuclei scanning executable in its sandbox and make PentAGI an active, XBOW-policy-mediated orchestrator.

**Architecture:** A dedicated scanner image owns the Nuclei binary/templates. PentAGI can create and track flows, but all target-facing actions are mediated by XBOW jobs that revalidate campaign policy at execution time.

**Tech Stack:** Python 3.12, FastAPI, Docker Compose, Nuclei v3.11.1, nuclei-templates v10.4.8, PentAGI HTTPS API.

**Spec:** docs/superpowers/specs/2026-09-16-nuclei-pentagi-controlled-runtime-design.md

## Global Constraints
- Default active execution flags remain off and DRY_RUN remains true.
- Nuclei version is exactly v3.11.1; nuclei-templates version is exactly v10.4.8.
- XBOW is authoritative for scope, rate, prohibited actions and cancellation.
- PentAGI direct target-facing tools are disabled for XBOW-managed flows.
- Remote create operations are never automatically retried after ambiguous failures.
- Secrets remain server-side/vault-backed.

---

### Task 1: Pinned Nuclei scanner image

**Files:**
- Create: `backend/Dockerfile.scanner`
- Modify: `docker-compose.yml`
- Test: `tests/test_scanner_runtime_contract.py`

**Interfaces:**
- Consumes: existing scanner-worker environment and `restricted-v1` admission.
- Produces: scanner image containing `nuclei` v3.11.1 and templates v10.4.8.

- [ ] **Step 1: Write the failing runtime-contract test**
Assert scanner-worker builds from `backend/Dockerfile.scanner`, declares the pinned versions, and the Dockerfile verifies upstream checksums before installation.

- [ ] **Step 2: Run the focused test**
Run: `pytest tests/test_scanner_runtime_contract.py -v`
Expected: FAIL because the dedicated scanner Dockerfile does not exist.

- [ ] **Step 3: Implement the scanner image**
Use a multi-stage build to download the correct Linux architecture release, verify SHA-256, install only the verified binary, fetch the exact templates release, and copy both into the final Python worker image.

- [ ] **Step 4: Wire Compose**
Set scanner-worker `build.dockerfile: Dockerfile.scanner` and default `XBOW_NUCLEI_ALLOWED_VERSION` to `3.11.1` only inside the scanner profile.

- [ ] **Step 5: Verify**
Run: `pytest tests/test_scanner_runtime_contract.py -v` and `docker compose config`.
Expected: PASS.

- [ ] **Step 6: Commit**
Commit message: `feat(scanner): pin nuclei runtime and templates`.

### Task 2: Controlled PentAGI flow contract

**Files:**
- Modify: `backend/app/pentagi_adapter.py`
- Modify: `backend/app/pentagi_admission.py`
- Test: `tests/test_pentagi_adapter.py`
- Test: `tests/test_pentagi_admission.py`

**Interfaces:**
- Consumes: `Campaign`, current scope rules and PentAGI provider/base URL.
- Produces: an execution-capable flow plan only when controlled functions are configured and direct target-facing functions are disabled.

- [ ] **Step 1: Add failing tests**
Cover execution-capable controlled plans and denial when direct terminal/browser-style functions are enabled.

- [ ] **Step 2: Run focused tests**
Run: `pytest tests/test_pentagi_adapter.py tests/test_pentagi_admission.py -v`
Expected: FAIL on the new controlled execution cases.

- [ ] **Step 3: Implement minimal controlled plan**
Encode the allowed function set explicitly, disable direct target-facing tools, and mark the plan execution-capable only for that contract.

- [ ] **Step 4: Re-run focused tests**
Expected: PASS.

- [ ] **Step 5: Commit**
Commit message: `feat(pentagi): enforce controlled flow contract`.

### Task 3: Server-held campaign binding and action gateway

**Files:**
- Create: `backend/app/pentagi_action_gateway.py`
- Modify: `backend/app/storage_backend.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_pentagi_action_gateway.py`

**Interfaces:**
- Consumes: remote flow id plus server-held flow/campaign binding.
- Produces: bounded XBOW job IDs for recon, Nuclei scan, status, findings and validation requests.

- [ ] **Step 1: Add failing gateway tests**
Prove unknown flow, caller-supplied campaign substitution, cancelled campaign, changed policy fingerprint, out-of-scope target and excessive rate all fail closed.

- [ ] **Step 2: Run focused test**
Run: `pytest tests/test_pentagi_action_gateway.py -v`
Expected: FAIL because the gateway is absent.

- [ ] **Step 3: Implement binding storage and gateway**
Persist `flow_id -> campaign_id + policy_fingerprint`; derive campaign identity exclusively from this binding; re-run existing scope/admission checks before queue mutation.

- [ ] **Step 4: Add authenticated internal endpoints**
Expose only the bounded operations needed by PentAGI and return job IDs rather than raw unrestricted execution.

- [ ] **Step 5: Re-run focused tests**
Expected: PASS.

- [ ] **Step 6: Commit**
Commit message: `feat(pentagi): add policy mediated action gateway`.

### Task 4: PentAGI lifecycle and cancellation

**Files:**
- Modify: `backend/app/pentagi_transport.py`
- Modify: `backend/app/pentagi_worker_service.py`
- Modify: `backend/app/pentagi_status_worker_service.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_pentagi_transport.py`
- Test: `tests/test_pentagi_worker_service.py`

**Interfaces:**
- Consumes: admitted permit and campaign lifecycle.
- Produces: one remote flow creation, persisted binding/receipt, bounded polling and remote stop on campaign cancellation.

- [ ] **Step 1: Add failing lifecycle tests**
Cover one-shot create, binding persistence, malformed flow IDs, cancellation stop, no redirect and no retry after ambiguous failure.

- [ ] **Step 2: Run focused tests**
Expected: FAIL on binding/cancellation behavior.

- [ ] **Step 3: Implement lifecycle**
Persist binding immediately after a confirmed create; status worker tracks only bound flows; cancellation blocks new gateway work and sends one bounded stop request.

- [ ] **Step 4: Re-run focused tests**
Expected: PASS.

- [ ] **Step 5: Commit**
Commit message: `feat(pentagi): complete controlled lifecycle`.

### Task 5: Capabilities, deployment docs and regression verification

**Files:**
- Modify: `backend/app/readiness.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Test: existing capabilities/readiness tests plus new runtime tests.

**Interfaces:**
- Consumes: runtime configuration from Tasks 1-4.
- Produces: explicit non-secret readiness reasons and operator instructions.

- [ ] **Step 1: Add failing readiness tests**
Assert active PentAGI reports blocked unless controlled contract, worker, transport, credentials and campaign-safe runtime gates are satisfied.

- [ ] **Step 2: Implement readiness/capabilities**
Expose only non-secret configuration state and exact fail-closed reasons.

- [ ] **Step 3: Document opt-in**
Document dry-run validation first, then the exact scanner/PentAGI profiles and environment variables required for active authorized testing.

- [ ] **Step 4: Run full verification**
Run: `ruff check backend tests`; `pytest -q`; JS syntax checks; `docker compose config`; build backend/scanner images; existing security/supply-chain CI.
Expected: all checks PASS.

- [ ] **Step 5: Commit**
Commit message: `docs: document controlled pentagi and nuclei runtime`.
