This file is a merged representation of a subset of the codebase, containing specifically included files and files not matching ignore patterns, combined into a single document by Repomix.
The content has been processed where content has been compressed (code blocks are separated by ⋮---- delimiter).

# File Summary

## Purpose
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: **/*.{py,js,mjs,cjs,ts,tsx,jsx,java,kt,kts,gd,groovy,gradle,toml,json,yaml,yml,sql,sh}, README.md, AGENTS.md, PROJECT_*.md
- Files matching these patterns are excluded: .ai/**, **/node_modules/**, **/.gradle/**, **/build/**, **/dist/**, **/.venv/**, **/__pycache__/**, **/.pytest_cache/**, **/.git/**, **/coverage/**, **/*.lock, **/*.min.js, **/*.map, assets/**, art/**, art_sources/**, marketing/**, colab/**, kaggle/**, discovery-cache.json, health-snapshot.json, history.json
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Content has been compressed - code blocks are separated by ⋮---- delimiter
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
````
.circleci/
  config.yml
.github/
  workflows/
    ai-repo-map.yml
    ci.yml
    release-images.yml
    release-quality-gate.yml
    security.yml
    supply-chain.yml
  dependabot.yml
.serena/
  project.yml
backend/
  app/
    adaptive_cycle.py
    agent_registry.py
    alert_delivery.py
    api_outbox.py
    api_rate_limit.py
    attack_surface.py
    auth.py
    autonomy_gate.py
    browser.py
    campaign_audit.py
    campaign_control.py
    campaign_overview.py
    campaign_review_state.py
    campaign_risk.py
    campaign_runtime.py
    chain_detector.py
    circuit_breaker.py
    coverage.py
    decision_audit.py
    decision_consensus.py
    decision_timeline.py
    deployment_preflight.py
    differential_intelligence.py
    domain_incident_lifecycle.py
    dr_cli.py
    dr_manifest.py
    error_budget.py
    evidence_chain.py
    evidence_quality.py
    finding_cluster_consensus.py
    finding_cluster_saturation.py
    finding_consensus.py
    finding_correlation.py
    finding_intelligence.py
    finding_lifecycle.py
    finding_readiness.py
    finding_triage.py
    hackerone_api.py
    hackerone_binding.py
    hackerone_scope_import.py
    hypothesis_engine.py
    hypothesis_memory.py
    incident_api.py
    incident_domains.py
    incident_engine.py
    incident_lifecycle.py
    incident_observer.py
    incident_store.py
    job_provenance.py
    jobqueue.py
    knowledge_memory.py
    learning_memory.py
    main.py
    metrics.py
    nuclei_parser.py
    observation_graph.py
    observation_writer.py
    observer_heartbeat.py
    observer_lease.py
    observer_metrics.py
    observer_resilience.py
    observer_runtime.py
    observer_scheduler.py
    observer_slo.py
    operational_alerts.py
    operational_slo.py
    orchestrator.py
    outbox_recovery.py
    pentagi_adapter.py
    pentagi_admission.py
    pentagi_auth.py
    pentagi_control.py
    pentagi_dispatch.py
    pentagi_execution_guard.py
    pentagi_flow_status.py
    pentagi_status_poller.py
    pentagi_status_tracker.py
    pentagi_status_worker_service.py
    pentagi_transport.py
    pentagi_worker_service.py
    pipeline_swarm.py
    planner_advisory.py
    planner_budget.py
    planner_limits.py
    planner_lock.py
    policy_integrity.py
    postgres_storage.py
    queue_backend.py
    readiness.py
    recon_swarm.py
    recon_worker.py
    red_team_coverage.py
    red_team_decision.py
    redis_jobqueue.py
    report_approval.py
    report_readiness.py
    report.py
    review_queue.py
    rolling_telemetry.py
    runtime_capabilities.py
    scanner_adaptation.py
    scanner_ingestion.py
    scanner_normalization.py
    scanner_registry.py
    scanner_sandbox.py
    scanner_worker.py
    secret_vault.py
    storage_backend.py
    storage.py
    strix_parser.py
    submission_api.py
    submission_state.py
    swarm_coordinator.py
    totp_auth.py
    validation_state.py
    validator.py
    vault_cli.py
    worker_audit.py
    worker_service.py
    worker_watchdog.py
    worker.py
  tests/
    test_adaptive_cycle.py
    test_agent_registry.py
    test_alert_delivery.py
    test_api_idempotency.py
    test_api_outbox.py
    test_api_rate_limit.py
    test_attack_surface_scope.py
    test_attack_surface.py
    test_auth.py
    test_autonomy_gate.py
    test_browser.py
    test_campaign_audit.py
    test_campaign_cancel.py
    test_campaign_circuit_breaker.py
    test_campaign_overview.py
    test_campaign_review_state.py
    test_campaign_risk.py
    test_campaign_runtime.py
    test_chain_detector.py
    test_control_views.py
    test_coverage.py
    test_decision_audit.py
    test_decision_consensus.py
    test_decision_timeline.py
    test_deployment_config.py
    test_deployment_preflight.py
    test_differential_evidence_integration.py
    test_differential_intelligence.py
    test_distributed_concurrency.py
    test_domain_incident_lifecycle.py
    test_domain_lifecycle_integration.py
    test_dr_cli.py
    test_dr_manifest.py
    test_error_budget.py
    test_evidence_backed_planner.py
    test_evidence_chain.py
    test_evidence_quality.py
    test_finding_cluster_consensus.py
    test_finding_cluster_saturation.py
    test_finding_consensus.py
    test_finding_correlation.py
    test_finding_intelligence.py
    test_finding_lifecycle.py
    test_finding_readiness.py
    test_finding_triage.py
    test_form_waf_reasoning.py
    test_frontend_policy_launcher.py
    test_hackerone_binding.py
    test_hackerone_launch_api.py
    test_hackerone_scope_import.py
    test_hackerone_scope_preview_api.py
    test_health.py
    test_hypothesis_engine.py
    test_hypothesis_memory.py
    test_incident_api.py
    test_incident_domains.py
    test_incident_engine.py
    test_incident_http_api.py
    test_incident_lifecycle.py
    test_incident_observer.py
    test_incident_store_fencing.py
    test_incident_store.py
    test_job_provenance_api_integration.py
    test_job_provenance_integration.py
    test_job_provenance.py
    test_jobqueue.py
    test_knowledge_memory.py
    test_learning_memory.py
    test_metrics.py
    test_nuclei_preflight.py
    test_nuclei_queue_lifecycle.py
    test_nuclei_worker_plan.py
    test_observation_graph.py
    test_observation_writer_provenance.py
    test_observer_deadline_heartbeat.py
    test_observer_fencing_integration.py
    test_observer_fencing.py
    test_observer_health_http.py
    test_observer_health_metrics.py
    test_observer_resilience.py
    test_observer_runtime.py
    test_observer_scheduler.py
    test_observer_slo.py
    test_openapi_integrity.py
    test_operational_alerts.py
    test_operational_slo.py
    test_orchestrator_validation_alignment.py
    test_orchestrator.py
    test_outbox_chaos.py
    test_overview_reasoning.py
    test_pentagi_adapter.py
    test_pentagi_admission.py
    test_pentagi_auth.py
    test_pentagi_control_api.py
    test_pentagi_control.py
    test_pentagi_dispatch.py
    test_pentagi_execution_guard.py
    test_pentagi_flow_status.py
    test_pentagi_status_poller.py
    test_pentagi_status_tracker.py
    test_pentagi_status_worker_service.py
    test_pentagi_transport.py
    test_pentagi_worker_service.py
    test_pipeline_swarm.py
    test_plan_evidence_quality.py
    test_planner_advisory.py
    test_planner_budget.py
    test_planner_limits.py
    test_policy_integrity.py
    test_policy_invariants.py
    test_postgres_integration.py
    test_postgres_storage.py
    test_queue_age_metrics.py
    test_queue_backend.py
    test_queue_health.py
    test_readiness.py
    test_recon_swarm.py
    test_recon_worker.py
    test_red_team_coverage.py
    test_red_team_decision.py
    test_redis_chaos.py
    test_redis_integration.py
    test_redis_jobqueue_integration.py
    test_redis_jobqueue.py
    test_report_approval.py
    test_report_readiness.py
    test_report.py
    test_review_queue.py
    test_rolling_telemetry.py
    test_runtime_budget_config.py
    test_runtime_capabilities.py
    test_scan_payload_idempotency.py
    test_scanner_adaptation.py
    test_scanner_ingestion.py
    test_scanner_normalization.py
    test_scanner_observation_chain.py
    test_scanner_sandbox.py
    test_scanner_worker.py
    test_scope.py
    test_secret_vault.py
    test_storage_backend.py
    test_storage.py
    test_submission_api.py
    test_submission_state.py
    test_swarm_coordinator.py
    test_totp_auth.py
    test_validation_state.py
    test_validator.py
    test_watchdog_observability.py
    test_worker_concurrency.py
    test_worker_job_provenance.py
    test_worker_observations.py
    test_worker_outcome_memory.py
    test_worker_parser.py
    test_worker_roles.py
    test_worker_secrets.py
    test_worker_state.py
    test_worker_watchdog.py
frontend/
  app.js
  hackerone.js
  sw.js
.repo-standards.yml
AGENTS.md
docker-compose.distributed.yml
docker-compose.tls.yml
docker-compose.yml
pyproject.toml
README.md
````

# Files

## File: .circleci/config.yml
````yaml
version: 2.1

jobs:
  test:
    docker:
      - image: cimg/python:3.12
    resource_class: small
    steps:
      - checkout
      - restore_cache:
          keys:
            - pip-v1-{{ checksum "backend/requirements.txt" }}-{{ checksum "backend/requirements-dev.txt" }}
      - run:
          name: Install dependencies
          command: pip install -r backend/requirements-dev.txt
      - save_cache:
          key: pip-v1-{{ checksum "backend/requirements.txt" }}-{{ checksum "backend/requirements-dev.txt" }}
          paths:
            - ~/.cache/pip
      - run:
          name: Dependency consistency
          command: python -m pip check
      - run:
          name: Compile
          command: python -m compileall -q backend/app backend/tests
      - run:
          name: Lint
          command: ruff check backend/app backend/tests
      - run:
          name: Test
          command: PYTHONPATH=backend pytest -q --strict-config --strict-markers backend/tests
      - run:
          name: Dependency audit
          command: pip-audit -r backend/requirements.txt

  compose-config:
    machine:
      image: ubuntu-2204:current
    resource_class: medium
    steps:
      - checkout
      - run:
          name: Validate Compose configuration
          command: docker compose config --quiet
      - run:
          name: Build containers
          command: docker compose build --pull

workflows:
  validate:
    jobs:
      - test
      - compose-config
````

## File: .github/workflows/ai-repo-map.yml
````yaml
name: Repository standards

on:
  push:
    branches: [main]
    paths-ignore:
      - ".ai/**"
  workflow_dispatch:

permissions:
  contents: write
  actions: read

concurrency:
  group: repo-standards-${{ github.repository }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  repository-standards:
    uses: dbrckk/repo-standards/.github/workflows/reusable-unified.yml@v7
````

## File: .github/workflows/release-images.yml
````yaml
name: release-images

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  packages: write
  id-token: write
  attestations: write

concurrency:
  group: release-images-${{ github.ref }}
  cancel-in-progress: false

jobs:
  publish:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: true
      matrix:
        include:
          - component: backend
            context: ./backend
          - component: frontend
            context: ./frontend
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Normalize repository owner
        id: owner
        shell: bash
        run: echo "value=${GITHUB_REPOSITORY_OWNER,,}" >> "$GITHUB_OUTPUT"

      - name: Build and publish immutable release image
        id: build
        uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          provenance: mode=max
          sbom: true
          tags: |
            ghcr.io/${{ steps.owner.outputs.value }}/xbow-perso-${{ matrix.component }}:${{ github.ref_name }}
            ghcr.io/${{ steps.owner.outputs.value }}/xbow-perso-${{ matrix.component }}:sha-${{ github.sha }}

      - name: Attest published image
        uses: actions/attest-build-provenance@v2
        with:
          subject-name: ghcr.io/${{ steps.owner.outputs.value }}/xbow-perso-${{ matrix.component }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true

      - name: Record immutable deployment reference
        shell: bash
        run: |
          mkdir -p release-manifest
          printf '%s@%s\n' \
            "ghcr.io/${{ steps.owner.outputs.value }}/xbow-perso-${{ matrix.component }}" \
            "${{ steps.build.outputs.digest }}" \
            > "release-manifest/${{ matrix.component }}.image"

      - uses: actions/upload-artifact@v4
        with:
          name: release-${{ matrix.component }}-${{ github.ref_name }}
          path: release-manifest/${{ matrix.component }}.image
          if-no-files-found: error
          retention-days: 90
````

## File: .github/workflows/release-quality-gate.yml
````yaml
name: release-quality-gate

on:
  workflow_dispatch:
    inputs:
      release_ref:
        description: "Immutable release tag or commit to validate"
        required: true
        type: string
      backend_image:
        description: "Backend image pinned as ghcr.io/...@sha256:..."
        required: true
        type: string
      frontend_image:
        description: "Frontend image pinned as ghcr.io/...@sha256:..."
        required: true
        type: string

permissions:
  contents: read
  packages: read
  attestations: read
  id-token: write

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    environment: production-candidate
    steps:
      - name: Reject mutable image references
        shell: bash
        env:
          BACKEND_IMAGE: ${{ inputs.backend_image }}
          FRONTEND_IMAGE: ${{ inputs.frontend_image }}
        run: |
          pattern='^ghcr\.io/.+@sha256:[0-9a-f]{64}$'
          [[ "$BACKEND_IMAGE" =~ $pattern ]] || { echo "backend image is not digest-pinned"; exit 1; }
          [[ "$FRONTEND_IMAGE" =~ $pattern ]] || { echo "frontend image is not digest-pinned"; exit 1; }

      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.release_ref }}

      - name: Verify backend provenance
        env:
          GH_TOKEN: ${{ github.token }}
          IMAGE: ${{ inputs.backend_image }}
        run: gh attestation verify "oci://$IMAGE" --repo "${{ github.repository }}"

      - name: Verify frontend provenance
        env:
          GH_TOKEN: ${{ github.token }}
          IMAGE: ${{ inputs.frontend_image }}
        run: gh attestation verify "oci://$IMAGE" --repo "${{ github.repository }}"

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            backend/requirements.txt
            backend/requirements-dev.txt

      - name: Install backend test dependencies
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Dependency consistency
        run: python -m pip check

      - name: Backend tests
        working-directory: backend
        env:
          DRY_RUN: "true"
          XBOW_ENABLE_ACTIVE_SCANS: "false"
        run: pytest -q

      - name: Static checks
        working-directory: backend
        run: ruff check app tests

      - name: Audit runtime dependencies
        working-directory: backend
        run: pip-audit -r requirements.txt

      - name: Build production preflight evidence
        env:
          BACKEND_IMAGE: ${{ inputs.backend_image }}
          FRONTEND_IMAGE: ${{ inputs.frontend_image }}
        shell: bash
        run: |
          mkdir -p release-gate
          printf '%s\n' "release_ref=${{ inputs.release_ref }}" > release-gate/manifest.txt
          printf '%s\n' "backend=$BACKEND_IMAGE" >> release-gate/manifest.txt
          printf '%s\n' "frontend=$FRONTEND_IMAGE" >> release-gate/manifest.txt
          printf '%s\n' "validated_commit=${{ github.sha }}" >> release-gate/manifest.txt

      - uses: actions/upload-artifact@v4
        with:
          name: production-candidate-${{ github.run_id }}
          path: release-gate/manifest.txt
          if-no-files-found: error
          retention-days: 90
````

## File: .github/workflows/security.yml
````yaml
name: security

on:
  push:
  pull_request:
  schedule:
    - cron: "17 4 * * 1"

permissions:
  contents: read

concurrency:
  group: security-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  dependency-audit:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            backend/requirements.txt
            backend/requirements-dev.txt
      - run: python -m pip install --upgrade pip
      - run: pip install -r backend/requirements-dev.txt
      - run: python -m pip check
      - run: pip-audit -r backend/requirements.txt

  secret-scan:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
````

## File: .github/workflows/supply-chain.yml
````yaml
name: supply-chain

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  backend-sbom:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: python -m pip install --upgrade pip
      - run: pip install -r backend/requirements.txt
      - run: pip install cyclonedx-bom==7.1.0
      - name: Generate CycloneDX SBOM
        run: cyclonedx-py environment --output-format JSON --output-file backend-sbom.cdx.json
      - uses: actions/upload-artifact@v4
        with:
          name: backend-sbom
          path: backend-sbom.cdx.json
          if-no-files-found: error
          retention-days: 14

  container-build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build backend without publishing
        uses: docker/build-push-action@v6
        with:
          context: ./backend
          push: false
          load: false
          provenance: mode=max
          sbom: true
          tags: xbow-perso-backend:ci
      - name: Build frontend without publishing
        uses: docker/build-push-action@v6
        with:
          context: ./frontend
          push: false
          load: false
          provenance: mode=max
          sbom: true
          tags: xbow-perso-frontend:ci
````

## File: .github/dependabot.yml
````yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /backend
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - security

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - security

  - package-ecosystem: docker
    directory: /backend
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - security

  - package-ecosystem: docker
    directory: /frontend
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - security
````

## File: .serena/project.yml
````yaml
project_name: "xbow-perso"
language_servers:
  - python
  - typescript
ls_workspace_folders:
  - "."
ignore_all_files_in_gitignore: true
ignored_paths:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/__pycache__/**"
  - "**/dist/**"
  - "**/build/**"
  - "deploy/**"
read_only: false
encoding: utf-8
symbol_info_budget: 8
initial_prompt: |
  Use Serena's symbol and reference tools before reading whole files. Start with symbol overviews, find_symbol and find_referencing_symbols; fetch full file bodies only when required for the task. Prefer targeted edits and preserve the existing architecture.
````

## File: backend/app/adaptive_cycle.py
````python
CycleState = Literal["halt", "recon", "review", "validate", "human_review", "complete"]
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class AdaptiveCycle
⋮----
state: CycleState
next_action: str
reason: str
retry_suppressed_techniques: tuple[str, ...]
retry_suppressed_job_kinds: tuple[str, ...]
safe_to_progress: bool
requires_human: bool
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _suppressed_techniques(memories: list[TechniqueMemory]) -> tuple[str, ...]
⋮----
def _unstable_job_kinds(worker_outcomes: dict[str, Any] | None) -> tuple[str, ...]
⋮----
by_kind = worker_outcomes.get("by_job_kind")
⋮----
unstable = []
⋮----
requeued = int(values.get("requeued") or 0)
completed = int(values.get("completed") or 0)
⋮----
"""Resolve one bounded campaign cycle without executing target actions."""
suppressed = _suppressed_techniques(memories)
unstable_jobs = _unstable_job_kinds(worker_outcomes)
⋮----
action = planned_actions[0] if planned_actions else PlannedAction("stop", None, "no planner action", 100)
⋮----
terminal = "already exists" in action.reason or "all findings rejected" in action.reason
⋮----
state_by_action: dict[str, CycleState] = {
state = state_by_action.get(action.kind, "halt")
requires_human = action.kind == "report"
⋮----
@router.get("/api/campaigns/{campaign_id}/adaptive-cycle")
def campaign_adaptive_cycle(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
graph = load_observation_graph(store, campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
decisions = build_red_team_decisions(campaign.findings, graph, scope_checker=scope_checker, limit=10)
consensus = build_decision_consensus(decisions)
risk = build_campaign_risk(campaign.findings, graph, scope_checker=scope_checker)
limits = PlannerBudget()
budget = budget_usage(graph, queue(), campaign.id, limits)
runtime = runtime_status(campaign.created_at, CampaignRuntimeLimit())
job_statuses = queue().campaign_job_status_counts(campaign.id)
gate = build_autonomy_gate(
planned = AdaptivePlanner().plan(campaign, graph)
memories = build_learning_memory(graph)
worker_outcomes = summarize_worker_outcomes(campaign.events)
cycle = build_adaptive_cycle(gate, planned, memories, worker_outcomes)
````

## File: backend/app/agent_registry.py
````python
AgentRole = Literal["recon", "analysis", "validation", "reporting", "control"]
⋮----
@dataclass(frozen=True)
class AgentProfile
⋮----
name: str
role: AgentRole
actions: tuple[str, ...]
description: str
network_access: bool = False
⋮----
def to_dict(self) -> dict
⋮----
AGENTS: tuple[AgentProfile, ...] = (
⋮----
def agent_for_action(action: str) -> AgentProfile
⋮----
matches = [agent for agent in AGENTS if action in agent.actions]
⋮----
def public_agent_catalog() -> list[dict]
⋮----
def agent_by_name(name: str) -> AgentProfile
⋮----
matches = [agent for agent in AGENTS if agent.name == name]
````

## File: backend/app/alert_delivery.py
````python
class AlertDeliveryError(RuntimeError)
⋮----
class _NoRedirect(HTTPRedirectHandler)
⋮----
def redirect_request(self, req, fp, code, msg, headers, newurl)
⋮----
def _webhook_url() -> str
⋮----
raw = os.getenv("XBOW_ALERT_WEBHOOK_URL", "").strip()
⋮----
parsed = urlparse(raw)
⋮----
def _timeout_seconds() -> float
⋮----
raw = os.getenv("XBOW_ALERT_WEBHOOK_TIMEOUT_SECONDS", "5").strip()
⋮----
value = float(raw)
⋮----
def _redacted_payload(alerts: dict) -> dict
⋮----
safe_alerts = []
⋮----
def _signature(body: bytes) -> str | None
⋮----
inline = os.getenv("XBOW_ALERT_WEBHOOK_HMAC_KEY")
⋮----
use_vault = vault_enabled()
⋮----
secret = get_secret("alert_webhook_hmac_key")
⋮----
secret = inline
⋮----
def deliver_alerts(alerts: dict) -> dict
⋮----
payload = _redacted_payload(alerts)
⋮----
url = _webhook_url()
body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
headers = {
signature = _signature(body)
⋮----
request = Request(url, data=body, method="POST", headers=headers)
opener = build_opener(_NoRedirect())
⋮----
status = int(response.status)
````

## File: backend/app/api_outbox.py
````python
def _matches_identity(event: Mapping[str, Any], identity: Mapping[str, Any]) -> bool
⋮----
identity = identity or {}
materialized = list(events)
completed = {
⋮----
request_id = event.get("request_id")
⋮----
def _identity_digest(value: str) -> str
⋮----
def _request_key(event: Mapping[str, Any]) -> tuple[str, str] | None
⋮----
event_type = event.get("type")
⋮----
finding_id = event.get("finding_id")
⋮----
purpose = event.get("purpose")
⋮----
flow_fingerprint = event.get("flow_fingerprint")
⋮----
fingerprint = event.get("dispatch_fingerprint")
⋮----
def _completion_key(event: Mapping[str, Any]) -> tuple[str, str] | None
⋮----
pending: list[dict[str, Any]] = []
seen: set[tuple[str, str]] = set()
⋮----
identity_key = _request_key(event)
⋮----
requested_at = event.get("at")
⋮----
counts = Counter(item["kind"] for item in pending)
oldest = next((item["requested_at"] for item in pending if item["requested_at"]), None)
visible = pending[:max_items]
⋮----
"""Return internal pending intent descriptors.

    This function intentionally includes raw identities/dedupe keys for local
    reconciliation code. API responses must use redacted diagnostics instead.
    """
⋮----
intents: list[dict[str, Any]] = []
⋮----
descriptor: dict[str, Any] = {
⋮----
platform = event.get("platform")
````

## File: backend/app/api_rate_limit.py
````python
class RateLimitConfigError(ValueError)
⋮----
@dataclass(frozen=True)
class ApiRateLimitConfig
⋮----
enabled: bool
requests: int
window_seconds: int
max_keys: int
backend: str = "memory"
⋮----
def _strict_bool(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _bounded_int(name: str, default: int, low: int, high: int) -> int
⋮----
raw = os.getenv(name, str(default)).strip()
⋮----
value = int(raw)
⋮----
def load_api_rate_limit_config() -> ApiRateLimitConfig
⋮----
backend = os.getenv("XBOW_API_RATE_LIMIT_BACKEND", "memory").strip().lower()
⋮----
class FixedWindowLimiter
⋮----
def __init__(self) -> None
⋮----
def _prune(self, current_window: int, max_keys: int) -> None
⋮----
stale = [key for key, (window, _count) in self._entries.items() if window != current_window]
⋮----
# Fail closed at capacity instead of evicting an active key and resetting its quota.
⋮----
def check(self, key: str, config: ApiRateLimitConfig, *, now: float | None = None) -> tuple[bool, int]
⋮----
timestamp = time.time() if now is None else now
window = int(timestamp // config.window_seconds)
retry_after = max(1, config.window_seconds - int(timestamp % config.window_seconds))
⋮----
entry = self._entries.get(key)
⋮----
count = entry[1]
⋮----
class RedisFixedWindowLimiter
⋮----
_SCRIPT = """
⋮----
def __init__(self, url: str, prefix: str = "xbow:ratelimit") -> None
⋮----
def _key(self, client_key: str, window_seconds: int, now: float) -> str
⋮----
window = int(now // window_seconds)
digest = hashlib.sha256(client_key.encode("utf-8")).hexdigest()
⋮----
retry_after = max(
digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
redis_key = self._key(key, config.window_seconds, timestamp)
active_key = f"{self.prefix}:active"
⋮----
retry_after = max(1, int(ttl) if int(ttl) > 0 else config.window_seconds)
⋮----
_limiter = FixedWindowLimiter()
_distributed_limiter: RedisFixedWindowLimiter | None = None
⋮----
def _active_limiter(config: ApiRateLimitConfig)
⋮----
url = os.getenv("XBOW_API_RATE_LIMIT_REDIS_URL", "").strip()
⋮----
prefix = os.getenv("XBOW_API_RATE_LIMIT_REDIS_PREFIX", "xbow:ratelimit").strip()
⋮----
_distributed_limiter = RedisFixedWindowLimiter(url, prefix)
⋮----
def _trusted_proxy_networks()
⋮----
raw = os.getenv("XBOW_TRUSTED_PROXY_CIDRS", "").strip()
⋮----
networks = []
⋮----
candidate = value.strip()
⋮----
def _parse_client_ip(value: str)
⋮----
def _client_key(request: Request) -> str
⋮----
client = request.client
peer = _parse_client_ip(client.host) if client and client.host else None
networks = _trusted_proxy_networks()
⋮----
forwarded = request.headers.get("x-forwarded-for", "")
hops = [item.strip() for item in forwarded.split(",") if item.strip()]
⋮----
parsed = [_parse_client_ip(item) for item in hops]
⋮----
# Walk from the nearest hop backwards. Trusted proxy hops are discarded;
# the first untrusted address is the effective client.
⋮----
async def api_rate_limit_middleware(request: Request, call_next)
⋮----
config = load_api_rate_limit_config()
⋮----
limiter = _active_limiter(config)
⋮----
response = await call_next(request)
````

## File: backend/app/attack_surface.py
````python
router = APIRouter()
⋮----
def canonical_host(value: str) -> str
⋮----
parsed = urlsplit(value if "://" in value else f"//{value}")
⋮----
def canonical_endpoint(value: str) -> dict[str, Any]
⋮----
parsed = urlsplit(value)
scheme = parsed.scheme.lower()
host = (parsed.hostname or "").lower().rstrip(".")
⋮----
port = parsed.port
⋮----
port = None
valid = False
error = "invalid_port"
⋮----
valid = bool(scheme and host)
error = None if valid else "missing_scheme_or_host"
⋮----
netloc = f"{host}:{port}"
⋮----
netloc = host
path = parsed.path or "/"
canonical_url = urlunsplit((scheme, netloc, path, "", "")) if valid else ""
parameter_names = sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)})
⋮----
def _safe_form(item: Any, scope_checker: Callable[[str], bool] | None) -> dict[str, Any]
⋮----
action = canonical_endpoint(item.value)
method = str(item.metadata.get("method", "GET")).upper()
⋮----
method = "OTHER"
input_names = sorted({str(name) for name in item.metadata.get("input_names", ()) if str(name).strip()})
host = action["host"]
⋮----
asset_observations = graph.by_kind("asset")
asset_hosts = {item.id: canonical_host(item.value) for item in asset_observations}
⋮----
assets = []
⋮----
host = asset_hosts[item.id]
⋮----
endpoints = []
⋮----
normalized = canonical_endpoint(item.value)
asset_parent_ids = sorted(parent for parent in item.parent_ids if parent in asset_hosts)
parent_hosts = sorted({asset_hosts[parent] for parent in asset_parent_ids})
host = normalized["host"]
⋮----
forms = [_safe_form(item, scope_checker) for item in graph.by_kind("form")]
technologies = [
wafs = [
⋮----
valid_endpoints = [item for item in endpoints if item["valid"]]
valid_forms = [item for item in forms if item["valid"]]
hosts = Counter(item["host"] for item in valid_endpoints if item["host"])
schemes = Counter(item["scheme"] for item in valid_endpoints if item["scheme"])
parameter_names = sorted({name for item in valid_endpoints for name in item["parameter_names"]})
form_input_names = sorted({name for item in valid_forms for name in item["input_names"]})
unique_urls = {item["url"] for item in valid_endpoints}
endpoint_sources = Counter(item["source"] for item in valid_endpoints)
surface_sources = {
source_diversity = len(surface_sources)
enrichment_score = round(
orphan_endpoints = [item for item in endpoints if not item["asset_parent_ids"]]
host_asset_mismatches = [item for item in valid_endpoints if item["host_asset_mismatch"]]
⋮----
scoped_assets = [item for item in assets if item["in_scope"] is not None]
scoped_endpoints = [item for item in valid_endpoints if item["in_scope"] is not None]
scoped_forms = [item for item in valid_forms if item["in_scope"] is not None]
⋮----
@router.get("/api/campaigns/{campaign_id}/attack-surface")
def campaign_attack_surface(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
surface = build_attack_surface(
````

## File: backend/app/auth.py
````python
class AuthError(RuntimeError)
⋮----
def __init__(self, status_code: int, detail: str)
⋮----
def _validate_token(token: str) -> str
⋮----
token = token.strip()
⋮----
def configured_api_token() -> str
⋮----
"""Return the server API token or fail closed when it is unsafe/missing.

    When the encrypted vault is enabled, only the api_token vault entry is
    accepted. Legacy env/file sources remain available only with the vault disabled.
    """
inline = os.getenv("XBOW_API_TOKEN", "").strip()
token_file = os.getenv("XBOW_API_TOKEN_FILE", "").strip()
⋮----
use_vault = vault_enabled()
⋮----
path = Path(token_file)
⋮----
size = path.stat().st_size
⋮----
token = path.read_text(encoding="utf-8")
⋮----
def presented_api_token(request: Request) -> str | None
⋮----
authorization = request.headers.get("authorization", "").strip()
fallback = request.headers.get("x-api-key", "").strip()
⋮----
def require_api_token(request: Request) -> None
⋮----
expected = configured_api_token()
presented = presented_api_token(request)
````

## File: backend/app/autonomy_gate.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class AutonomyGate
⋮----
safe_autonomy_ready: bool
human_review_required: bool
next_focus: str
blockers: tuple[str, ...]
safeguards: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Fail closed before any autonomous safe-review progression.

    The gate is read-only: it never queues jobs, changes finding state, or performs
    network actions. It only decides whether the current campaign state is safe
    enough for already-authorized bounded automation to continue elsewhere.
    """
blockers: list[str] = []
⋮----
blockers = sorted(set(blockers))
human_review_required = consensus.next_focus == "review_for_report" or risk.level in {
⋮----
safeguards = (
⋮----
@router.get("/api/campaigns/{campaign_id}/autonomy-gate")
def campaign_autonomy_gate(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
decisions = build_red_team_decisions(
consensus = build_decision_consensus(decisions)
risk = build_campaign_risk(
limits = planner_budget_from_env()
budget = budget_usage(graph, queue(), campaign.id, limits)
runtime = runtime_status(campaign.created_at, campaign_runtime_limit_from_env())
job_statuses = queue().campaign_job_status_counts(campaign.id)
⋮----
gate = build_autonomy_gate(
````

## File: backend/app/browser.py
````python
router = APIRouter()
⋮----
class BrowserPolicyError(RuntimeError)
⋮----
class BrowserStep(BaseModel)
⋮----
operation: Literal["navigate", "click", "fill", "wait_for", "screenshot"]
url: str | None = None
selector: str | None = Field(default=None, max_length=500)
secret_env: str | None = Field(default=None, pattern=r"^XBOW_BROWSER_SECRET_[A-Z0-9_]+$")
timeout_ms: int = Field(default=10_000, ge=100, le=30_000)
⋮----
@model_validator(mode="after")
    def validate_shape(self)
⋮----
class BrowserFlowInput(BaseModel)
⋮----
steps: list[BrowserStep] = Field(min_length=1, max_length=25)
⋮----
@dataclass(frozen=True)
class BrowserExecutionResult
⋮----
status: str
observations: list[dict]
screenshots: list[tuple[str, bytes]]
⋮----
def _bool_env(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _browser_secret(secret_env: str) -> str
⋮----
use_vault = vault_enabled()
⋮----
vault_name = "browser." + secret_env.removeprefix("XBOW_BROWSER_SECRET_").lower()
⋮----
secret = os.getenv(secret_env)
⋮----
def _utcnow() -> str
⋮----
def _campaign(campaign_id: str, store: StorageBackend | None = None)
⋮----
backend = store or create_storage()
record = backend.get_campaign_record(campaign_id)
⋮----
def _flow_fingerprint(flow: BrowserFlowInput) -> str
⋮----
encoded = json.dumps(
⋮----
def _flow_dedupe_key(campaign_id: str, version: int, flow: BrowserFlowInput) -> str
⋮----
"""Backward-compatible deterministic key helper for historical callers/tests."""
digest = _flow_fingerprint(flow)[:24]
⋮----
def _save_campaign(store: StorageBackend, campaign, version: int) -> int
⋮----
def _allowed_url(campaign, candidate: str, base: str | None = None) -> str
⋮----
resolved = urljoin(base or str(campaign.target.primary_url), candidate)
parsed = urlparse(resolved)
⋮----
def _assert_read_only_browser_method(method: str) -> None
⋮----
normalized = method.strip().upper()
⋮----
def _assert_browser_policy(campaign) -> None
⋮----
rules = campaign.target.rules
⋮----
def validate_flow(campaign, flow: BrowserFlowInput) -> BrowserFlowInput
⋮----
base = str(campaign.target.primary_url)
⋮----
base = _allowed_url(campaign, step.url or "", base)
⋮----
@router.post("/api/campaigns/{campaign_id}/browser-flows")
def queue_browser_flow(campaign_id: str, flow: BrowserFlowInput)
⋮----
store = create_storage()
jobs: QueueBackend = create_queue()
⋮----
flow_fingerprint = _flow_fingerprint(flow)
request_id = pending_request_id(
⋮----
job = jobs.enqueue(
⋮----
def execute_browser_flow(campaign, payload: dict) -> BrowserExecutionResult
⋮----
flow = validate_flow(campaign, BrowserFlowInput.model_validate({"steps": payload.get("steps", [])}))
⋮----
observations: list[dict] = []
screenshots: list[tuple[str, bytes]] = []
⋮----
browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
context = browser.new_context(ignore_https_errors=False)
page = context.new_page()
⋮----
def route_guard(route)
⋮----
target = _allowed_url(campaign, step.url or "", page.url if page.url != "about:blank" else None)
response = page.goto(target, wait_until="domcontentloaded", timeout=step.timeout_ms)
final_url = _allowed_url(campaign, page.url, target)
⋮----
links = []
⋮----
safe = _allowed_url(campaign, str(href), final_url)
⋮----
forms = []
raw_forms = page.locator("form").evaluate_all(
⋮----
method = str(raw_form.get("method") or "GET").upper()
⋮----
action_url = _allowed_url(
⋮----
technologies = []
generator = page.locator('meta[name="generator"]').get_attribute("content")
⋮----
framework_markers = page.evaluate(
⋮----
secret = _browser_secret(step.secret_env or "")
⋮----
data = page.screenshot(full_page=True)
⋮----
artifacts = [
````

## File: backend/app/campaign_audit.py
````python
_VOLATILE_FIELDS = {"event_hash", "event_signature", "event_signature_alg"}
⋮----
def _canonical_event(event: dict[str, Any]) -> bytes
⋮----
payload = {key: value for key, value in event.items() if key not in _VOLATILE_FIELDS}
⋮----
def seal_campaign_event(event: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]
⋮----
sealed = dict(event)
previous = events[-1].get("event_hash") if events else None
⋮----
canonical = _canonical_event(sealed)
⋮----
secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
⋮----
def append_campaign_event(events: list[dict[str, Any]], event: dict[str, Any]) -> None
⋮----
def verify_campaign_event_chain(events: list[dict[str, Any]]) -> dict[str, Any]
⋮----
# Backward compatibility: historical events remain explicitly reported as legacy.
first_sealed = next((i for i, item in enumerate(events) if item.get("event_hash")), len(events))
legacy = first_sealed
previous = events[first_sealed - 1].get("event_hash") if first_sealed else None
checked = 0
expected_seq = first_sealed + 1
⋮----
canonical = _canonical_event(item)
digest = hashlib.sha256(canonical).hexdigest()
⋮----
signature = item.get("event_signature")
⋮----
secret = None
⋮----
expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
⋮----
previous = digest
````

## File: backend/app/campaign_control.py
````python
router = APIRouter()
⋮----
def _recon_telemetry(events: list[dict]) -> dict
⋮----
completed = [event for event in events if event.get("type") == "recon_task_completed"]
⋮----
def _autonomy_block_reasons(breaker: dict, runtime: object, usage: object) -> list[str]
⋮----
reasons: list[str] = []
⋮----
@router.get("/api/campaigns/{campaign_id}/control-status")
def campaign_control_status(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
jobs = queue()
graph = load_observation_graph(store, campaign.id)
budget_limits = planner_budget_from_env()
runtime_limit = campaign_runtime_limit_from_env()
usage = budget_usage(graph, jobs, campaign.id, budget_limits)
runtime = runtime_status(campaign.created_at, runtime_limit)
statuses = jobs.campaign_job_status_counts(campaign.id)
breaker = circuit_breaker_state(graph)
stability = planner_stability_from_graph(graph)
scanner = safe_scanner_runtime_capability()
recon = _recon_telemetry(campaign.events)
block_reasons = _autonomy_block_reasons(breaker, runtime, usage)
⋮----
@router.post("/api/campaigns/{campaign_id}/circuit-breaker/reset")
def reset_campaign_circuit_breaker(campaign_id: str)
⋮----
state = record_circuit_reset(storage(), campaign.id, at=utcnow())
````

## File: backend/app/campaign_overview.py
````python
router = APIRouter()
⋮----
@router.get("/api/campaigns/{campaign_id}/overview")
def campaign_overview(campaign_id: str)
⋮----
store = storage()
jobs = queue()
graph = load_observation_graph(store, campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
validation = analyze_validation_state(graph)
knowledge = build_knowledge_snapshot(graph)
learning = build_learning_memory(graph)
surface = build_attack_surface(graph, scope_checker=scope_checker)
hypotheses = build_hypotheses(graph, scope_checker=scope_checker)
chains = build_evidence_chains(graph)
correlations = correlate_findings(campaign.findings)
triage = build_finding_triage(campaign.findings, graph)
lifecycle = build_finding_lifecycle(campaign.findings, graph)
report_readiness = build_report_readiness(campaign.findings, graph)
review_state = build_campaign_review_state(campaign.findings, graph)
coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
review_tasks = build_review_queue(graph, scope_checker=scope_checker)
decisions = build_red_team_decisions(
consensus = build_decision_consensus(decisions)
risk = build_campaign_risk(
recon_tasks = build_recon_plan(
limits = PlannerBudget()
budget = budget_usage(graph, jobs, campaign.id, limits)
runtime_limit = CampaignRuntimeLimit()
runtime = runtime_status(campaign.created_at, runtime_limit)
⋮----
finding_counts = Counter(str(item.status) for item in campaign.findings)
resolved_findings = finding_counts.get("confirmed", 0) + finding_counts.get("rejected", 0)
hypothesis_counts = Counter(item.kind for item in hypotheses)
complete_chains = sum(item.complete for item in chains)
duplicate_groups = [item for item in correlations if item.duplicate_candidate]
report_states = Counter()
report_integrity_errors = 0
reports = []
⋮----
status = submission_status(campaign, verified).to_dict()
⋮----
job_kinds = jobs.campaign_job_counts(campaign.id)
job_statuses = jobs.campaign_job_status_counts(campaign.id)
blocked = dict(budget.blocked_actions)
terminal_campaign = campaign.state.value in {"completed", "failed", "cancelled"}
attention_reasons = []
⋮----
latest_event = campaign.events[-1] if campaign.events else None
total_findings = len(campaign.findings)
````

## File: backend/app/campaign_review_state.py
````python
router = APIRouter()
⋮----
def build_campaign_review_state(findings: list[Any], graph: ObservationGraph) -> dict[str, Any]
⋮----
"""Aggregate human-review state from existing finding evidence only.

    This summary is read-only and advisory. It cannot mutate findings, approve
    reports, submit reports, queue target actions, or execute against targets.
    """
lifecycle = build_finding_lifecycle(findings, graph)
readiness = build_report_readiness(findings, graph)
⋮----
blockers = Counter(
prerequisites = Counter(
⋮----
ready_ids = tuple(
human_decision_ids = tuple(
transition_ids = tuple(
⋮----
next_focus = "idle"
⋮----
next_focus = "independent_validation"
⋮----
next_focus = "evidence_integrity"
⋮----
next_focus = "duplicate_review"
⋮----
next_focus = "human_report_review"
⋮----
next_focus = "human_finding_decision"
⋮----
next_focus = "finding_state_review"
⋮----
@router.get("/api/campaigns/{campaign_id}/review-state")
def campaign_review_state(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
````

## File: backend/app/campaign_risk.py
````python
RiskLevel = Literal["low", "moderate", "high", "critical"]
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class CampaignRisk
⋮----
level: RiskLevel
score: float
confidence: float
blocked: bool
factors: tuple[str, ...]
next_focus: str
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Summarize campaign review risk from existing evidence only.

    This model is advisory and read-only. It never changes finding state, creates
    payloads, queues work, or performs target actions.
    """
surface = build_attack_surface(graph, scope_checker=scope_checker)
coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
triage = build_finding_triage(findings, graph)
decisions = build_red_team_decisions(
consensus = build_decision_consensus(decisions)
⋮----
factors: list[str] = []
integrity_count = (
⋮----
needs_validation = sum(item.recommended_state == "validate" for item in triage)
⋮----
high_value = [item for item in triage if item.severity in {"high", "critical"}]
⋮----
duplicate_review = sum(item.recommended_state == "review_duplicate" for item in triage)
⋮----
coverage_score = float(coverage["score"])
⋮----
highest_triage = max((item.score for item in triage), default=0.0)
coverage_gap = max(1.0 - coverage_score, 0.5 if integrity_count else 0.0)
integrity_pressure = min(1.0, integrity_count / 3)
consensus_pressure = 1.0 if consensus.blocked else 0.0
score = round(
⋮----
level: RiskLevel = "critical"
⋮----
level = "high"
⋮----
level = "moderate"
⋮----
level = "low"
⋮----
confidence = round(
⋮----
@router.get("/api/campaigns/{campaign_id}/risk")
def campaign_risk(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
risk = build_campaign_risk(
````

## File: backend/app/campaign_runtime.py
````python
@dataclass(frozen=True)
class CampaignRuntimeLimit
⋮----
max_runtime_seconds: int = 6 * 60 * 60
⋮----
def __post_init__(self) -> None
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def campaign_runtime_limit_from_env() -> CampaignRuntimeLimit
⋮----
raw = os.getenv("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS")
⋮----
value = int(raw)
⋮----
@dataclass(frozen=True)
class CampaignRuntimeStatus
⋮----
elapsed_seconds: int
remaining_seconds: int
exhausted: bool
reason: str | None
⋮----
def _parse_timestamp(value: str) -> datetime
⋮----
normalized = value.strip().replace("Z", "+00:00")
parsed = datetime.fromisoformat(normalized)
⋮----
limits = limit or CampaignRuntimeLimit()
started = _parse_timestamp(created_at)
current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
elapsed = max(0, int((current - started).total_seconds()))
remaining = max(0, limits.max_runtime_seconds - elapsed)
exhausted = elapsed >= limits.max_runtime_seconds
````

## File: backend/app/chain_detector.py
````python
@dataclass(frozen=True)
class ObservationChain
⋮----
node_ids: tuple[str, ...]
kinds: tuple[str, ...]
terminal_kind: str
complete_validation_chain: bool
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Return bounded provenance chains from the observation graph.

    The detector is read-only. It follows existing parent relationships and does
    not infer exploit steps, targets, payloads, or new network actions.
    """
⋮----
items = {item.id: item for item in graph.values()}
children: dict[str, list[str]] = {item_id: [] for item_id in items}
⋮----
roots = sorted(item.id for item in items.values() if not item.parent_ids)
chains: list[ObservationChain] = []
⋮----
def walk(path: tuple[str, ...]) -> None
⋮----
current = path[-1]
next_nodes = [node_id for node_id in children.get(current, ()) if node_id not in path]
⋮----
kinds = tuple(items[node_id].kind for node_id in path)
````

## File: backend/app/circuit_breaker.py
````python
_BREAKER_MEMORY_TYPE = "campaign_circuit_breaker"
⋮----
def _breaker_id(reason: str) -> str
⋮----
digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:24]
⋮----
def circuit_breaker_state(graph: ObservationGraph) -> dict[str, Any]
⋮----
events = [
ordered = sorted(events, key=lambda item: str(item.metadata.get("at") or ""))
⋮----
latest = ordered[-1]
state = str(latest.metadata.get("state") or "")
⋮----
def record_circuit_open(store: Any, campaign_id: str, reason: str, *, at: str) -> dict[str, Any]
⋮----
graph = ObservationGraph.from_records(store.list_observations(campaign_id))
current = circuit_breaker_state(graph)
⋮----
observation = Observation(
⋮----
def record_circuit_reset(store: Any, campaign_id: str, *, at: str) -> dict[str, Any]
````

## File: backend/app/coverage.py
````python
router = APIRouter()
⋮----
surface = build_attack_surface(graph, scope_checker=scope_checker)
summary = surface["summary"]
discovery = float(summary["enrichment_score"])
⋮----
scan_evidence = [
scanner_sources = sorted({item.source for item in scan_evidence})
scan_score = 1.0 if scan_evidence else 0.0
⋮----
validation = analyze_validation_state(graph)
finding_count = len(validation.finding_ids)
validated_count = len(validation.observed_independent_finding_ids)
validation_score = (
⋮----
overall = round(discovery * 0.625 + scan_score * 0.375, 4)
⋮----
overall = round(
⋮----
@router.get("/api/campaigns/{campaign_id}/coverage")
def campaign_coverage(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
coverage = build_evidence_coverage(
⋮----
def build_coverage_guidance(coverage: dict[str, Any]) -> dict[str, Any]
⋮----
dimensions = coverage.get("dimensions") or {}
discovery = float(dimensions.get("surface_discovery") or 0.0)
scanner = float(dimensions.get("scanner_execution") or 0.0)
validation = dimensions.get("independent_validation")
⋮----
focus = "surface_discovery"
reason = "surface evidence is still sparse"
⋮----
focus = "scanner_execution"
reason = "surface evidence exists but no completed scanner evidence is recorded"
⋮----
focus = "independent_validation"
reason = "not all observed findings have independent validation evidence"
⋮----
focus = "none"
reason = "no evidence-coverage gap requires advisory emphasis"
````

## File: backend/app/decision_audit.py
````python
_AUDIT_FIELDS = {
⋮----
payload = {
⋮----
sealed = dict(metadata)
canonical = _canonical_decision_payload(observation_id, sealed)
⋮----
secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
⋮----
def _planner_decisions(graph: ObservationGraph)
⋮----
def next_audit_link(graph: ObservationGraph) -> tuple[int, str | None]
⋮----
sealed = [
⋮----
latest = max(sealed, key=lambda item: int(item.metadata["audit_seq"]))
⋮----
def verify_decision_audit_chain(graph: ObservationGraph) -> dict[str, Any]
⋮----
decisions = _planner_decisions(graph)
legacy = [
⋮----
expected_seq = 1
previous_hash: str | None = None
checked = 0
⋮----
metadata = item.metadata
seq = int(metadata["audit_seq"])
⋮----
canonical = _canonical_decision_payload(item.id, metadata)
actual_hash = hashlib.sha256(canonical).hexdigest()
⋮----
signature = metadata.get("decision_signature")
⋮----
expected_signature = hmac.new(
⋮----
previous_hash = str(metadata["decision_hash"])
````

## File: backend/app/decision_consensus.py
````python
router = APIRouter()
⋮----
_BLOCKING_KINDS = {"scope_integrity", "review_contradiction"}
_ACTIONABLE_KINDS = {
⋮----
@dataclass(frozen=True)
class DecisionConsensus
⋮----
next_focus: str
confidence: float
blocked: bool
contradictory: bool
reasons: tuple[str, ...]
supporting_kinds: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def build_decision_consensus(decisions: list[RedTeamDecision]) -> DecisionConsensus
⋮----
"""Resolve advisory decisions conservatively without executing any action."""
⋮----
kinds = tuple(sorted({item.kind for item in decisions}))
blocking = [item for item in decisions if item.kind in _BLOCKING_KINDS]
actionable = [item for item in decisions if item.kind in _ACTIONABLE_KINDS]
⋮----
top_blocker = sorted(blocking, key=lambda item: (-item.priority, item.kind))[0]
reason = (
⋮----
ranked = sorted(decisions, key=lambda item: (-item.priority, item.kind))
top = ranked[0]
close_competitors = [
contradictory = bool(close_competitors)
confidence = round(
reasons = [top.reason]
⋮----
@router.get("/api/campaigns/{campaign_id}/decision-consensus")
def campaign_decision_consensus(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph: ObservationGraph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
decisions = build_red_team_decisions(
consensus = build_decision_consensus(decisions)
````

## File: backend/app/decision_timeline.py
````python
router = APIRouter()
⋮----
def _flatten_explanation(value: Any, prefix: str = "") -> dict[str, Any]
⋮----
flattened: dict[str, Any] = {}
⋮----
child = f"{prefix}.{key}" if prefix else str(key)
⋮----
def _signal_diff(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> list[dict[str, Any]]
⋮----
before = _flatten_explanation(previous)
after = _flatten_explanation(current)
changes: list[dict[str, Any]] = []
⋮----
old = before.get(key)
new = after.get(key)
⋮----
change: dict[str, Any] = {"signal": key, "before": old, "after": new}
⋮----
old_set = set(str(item) for item in old)
new_set = set(str(item) for item in new)
⋮----
by_signal = {item["signal"]: item for item in changes}
clauses: list[str] = []
⋮----
gate_allowed = by_signal.get("gate.allowed")
gate_blockers = by_signal.get("gate.blockers")
⋮----
added = list((gate_blockers or {}).get("added") or [])
suffix = f" après {len(added)} nouveau(x) blocker(s)" if added else ""
⋮----
risk_level = by_signal.get("risk.level")
⋮----
consensus_focus = by_signal.get("consensus.next_focus")
⋮----
contradictory = by_signal.get("consensus.contradictory")
⋮----
cycle_state = by_signal.get("cycle.state")
⋮----
surface_ready = by_signal.get("surface_enrichment.ready")
⋮----
coverage = by_signal.get("coverage.coverage_score")
⋮----
before = round(float(coverage["before"]) * 100)
after = round(float(coverage["after"]) * 100)
⋮----
transition_text = (
⋮----
def planner_stability(planner_entries: list[dict[str, Any]]) -> dict[str, Any]
⋮----
actions = [str(item.get("action") or "") for item in planner_entries if item.get("action")]
transitions = list(zip(actions, actions[1:]))
anomalies: list[dict[str, Any]] = []
⋮----
reversals = 0
⋮----
stop_reopens = 0
⋮----
repeated_switches = 0
⋮----
recent = transitions[-4:]
repeated_switches = sum(1 for before, after in recent if before != after)
⋮----
score = 1.0
⋮----
score = round(max(0.0, score), 2)
⋮----
state = "stable"
⋮----
state = "watch"
⋮----
state = "unstable"
⋮----
def planner_stability_from_graph(graph: Any) -> dict[str, Any]
⋮----
entries = []
⋮----
def planner_stability_breaker_reason(stability: dict[str, Any]) -> str | None
⋮----
planner_entries = []
⋮----
previous: dict[str, Any] | None = None
⋮----
previous = entry
⋮----
campaign_entries = []
⋮----
timestamped = [
⋮----
stability = planner_stability(planner_entries)
⋮----
@router.get("/api/campaigns/{campaign_id}/decision-timeline")
def campaign_decision_timeline(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
payload = build_decision_timeline(campaign, graph)
````

## File: backend/app/deployment_preflight.py
````python
def _configured(name: str) -> bool
⋮----
def _bool_env(name: str, default: bool = False) -> tuple[bool, bool]
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _production_mode() -> bool
⋮----
def _image_digest_configured(name: str) -> bool
⋮----
value = (os.getenv(name) or "").strip()
⋮----
"""Return redacted deployment diagnostics without changing runtime state."""
⋮----
pentagi = safe_pentagi_runtime_capability()
scanner = safe_scanner_runtime_capability()
issues: list[dict[str, Any]] = []
production = _production_mode()
⋮----
integration_enabled = bool(pentagi.get("integration_enabled"))
worker_enabled = bool(pentagi.get("worker_enabled"))
transport_enabled = bool(pentagi.get("transport_enabled"))
status_worker_enabled = bool(
⋮----
execution_intent = bool(
⋮----
scanner_execution_intent = bool(scanner.get("nuclei_execution_intent"))
⋮----
severities = {str(item["severity"]) for item in issues}
⋮----
status = "error"
⋮----
status = "warning"
⋮----
status = "ok"
````

## File: backend/app/differential_intelligence.py
````python
DifferentialSignalLevel = Literal["none", "weak", "strong"]
_SIGNAL_RANK: dict[DifferentialSignalLevel, int] = {
⋮----
@dataclass(frozen=True)
class DifferentialSignal
⋮----
finding_id: str
signal: DifferentialSignalLevel
parameter: str | None = None
marker_reflected: bool = False
status_changed: bool = False
body_changed: bool = False
baseline_status: int | None = None
marker_status: int | None = None
observation_ids: tuple[str, ...] = ()
⋮----
def to_dict(self) -> dict[str, object]
⋮----
payload = asdict(self)
⋮----
def classify_differential_signal(differential: dict[str, Any] | None) -> DifferentialSignalLevel
⋮----
"""Classify read-only differential evidence without asserting exploitability."""
⋮----
def differential_signal_metadata(differential: dict[str, Any] | None) -> dict[str, object]
⋮----
"""Return sanitized graph metadata for a differential observation."""
⋮----
signal = classify_differential_signal(differential)
metadata: dict[str, object] = {
parameter = differential.get("parameter")
⋮----
value = differential.get(source_key)
⋮----
reason = differential.get("reason")
⋮----
def _finding_id_from_validation(observation) -> str | None
⋮----
value = observation.metadata.get("finding_id")
⋮----
def _signal_from_metadata(finding_id: str, observation) -> DifferentialSignal | None
⋮----
raw_signal = observation.metadata.get("differential_signal")
⋮----
def build_differential_signals(graph: ObservationGraph) -> dict[str, DifferentialSignal]
⋮----
"""Build one conservative differential signal per graph finding.

    Multiple validation observations are deduplicated by their graph IDs. The
    strongest signal wins while all contributing differential observation IDs
    remain attached as provenance.
    """
finding_ids: set[str] = set()
⋮----
candidates: dict[str, list[DifferentialSignal]] = {finding_id: [] for finding_id in finding_ids}
provenance: dict[str, set[str]] = {finding_id: set() for finding_id in finding_ids}
⋮----
finding_id = _finding_id_from_validation(observation)
⋮----
signal = _signal_from_metadata(finding_id, observation)
⋮----
result: dict[str, DifferentialSignal] = {}
⋮----
items = candidates.get(finding_id, [])
⋮----
selected = max(
⋮----
def differential_signal_rank(signal: DifferentialSignalLevel | str) -> int
````

## File: backend/app/domain_incident_lifecycle.py
````python
DOMAINS = ("workload", "control_plane", "observability")
MAX_HISTORY = 1000
⋮----
def _now(value: datetime | None = None) -> str
⋮----
"""Apply independent lifecycle transitions for each operational domain."""
items = [dict(item) for item in history[-MAX_HISTORY:]]
incoming = snapshot.get("incidents") or {}
timestamp = _now(now)
⋮----
incident = incoming.get(domain)
active = next(
⋮----
fingerprint = str(incident["fingerprint"])
⋮----
def active_incidents_by_domain(history: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]
⋮----
result: dict[str, dict[str, Any] | None] = {}
````

## File: backend/app/dr_cli.py
````python
def _parser() -> argparse.ArgumentParser
⋮----
parser = argparse.ArgumentParser(
sub = parser.add_subparsers(dest="command", required=True)
⋮----
create = sub.add_parser("manifest")
⋮----
verify = sub.add_parser("verify")
⋮----
def main() -> int
⋮----
args = _parser().parse_args()
⋮----
output_path = Path(args.output).resolve(strict=False)
backup_paths = {
⋮----
manifest = build_backup_manifest(
⋮----
result = {
⋮----
verification = verify_backup_manifest(
result = {"ok": verification["valid"], **verification}
````

## File: backend/app/dr_manifest.py
````python
_LEGACY_SIGNATURE_FIELDS = {
_V2_SIGNATURE_FIELDS = {"manifest_signature", "manifest_signature_alg"}
_V2_INTEGRITY_MODE = "sha256-artifacts+hmac-sha256-manifest"
⋮----
class DisasterRecoveryError(RuntimeError)
⋮----
def _canonical_manifest(manifest: dict[str, Any]) -> bytes
⋮----
version = manifest.get("version")
excluded = (
payload = {
⋮----
def _seal_manifest(manifest: dict[str, Any]) -> dict[str, Any]
⋮----
sealed = dict(manifest)
⋮----
secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
⋮----
# Version 2 makes authenticated manifests unambiguously authenticated.
# A v2 manifest cannot be downgraded to an unsigned legacy manifest merely
# by deleting signature metadata.
⋮----
canonical = _canonical_manifest(sealed)
⋮----
def _verification_secret() -> str
⋮----
def _verify_manifest_signature(manifest: dict[str, Any]) -> bool | None
⋮----
signature = manifest.get("manifest_signature")
algorithm = manifest.get("manifest_signature_alg")
integrity_mode = manifest.get("integrity_mode")
⋮----
# Legacy unsigned v1 manifests remain readable. Legacy signed v1
# manifests also remain verifiable using their original canonical form.
⋮----
secret = _verification_secret()
expected = hmac.new(
⋮----
def _safe_backup_file(path_value: str, label: str) -> Path
⋮----
path = Path(path_value)
⋮----
stat = path.stat()
⋮----
def _sha256(path: Path) -> str
⋮----
digest = hashlib.sha256()
⋮----
entries = []
⋮----
path = _safe_backup_file(value, kind)
⋮----
def write_backup_manifest(manifest: dict[str, Any], destination: str) -> None
⋮----
path = Path(destination)
⋮----
tmp = path.with_name(path.name + ".tmp")
sealed = _seal_manifest(manifest)
encoded = json.dumps(sealed, sort_keys=True, indent=2)
⋮----
path = Path(manifest_path)
⋮----
manifest = json.loads(path.read_text(encoding="utf-8"))
⋮----
signature_valid = _verify_manifest_signature(manifest)
⋮----
current = build_backup_manifest(
expected = {
actual = {item["kind"]: item for item in current["artifacts"]}
⋮----
results = {}
valid = True
⋮----
left = expected.get(kind)
right = actual.get(kind)
⋮----
size_value = left.get("size_bytes")
⋮----
match = bool(
⋮----
valid = valid and match
````

## File: backend/app/error_budget.py
````python
def _target_success_rate() -> float
⋮----
raw = os.getenv("XBOW_SLO_TARGET_SUCCESS_RATE", "0.99")
⋮----
value = float(raw)
⋮----
def _burn(failure_rate: float, budget: float) -> float
⋮----
def build_error_budget_status(telemetry: dict[str, Any]) -> dict[str, Any]
⋮----
"""Evaluate multi-window error-budget consumption from rolling telemetry."""
target = _target_success_rate()
budget = 1.0 - target
windows = telemetry.get("windows") or {}
⋮----
short = windows.get("300") or {}
long = windows.get("3600") or {}
short_events = int(short.get("events") or 0)
long_events = int(long.get("events") or 0)
short_burn = _burn(float(short.get("failure_rate") or 0.0), budget)
long_burn = _burn(float(long.get("failure_rate") or 0.0), budget)
⋮----
alerts: list[dict[str, Any]] = []
⋮----
# Require minimum sample counts to avoid one isolated failure creating a
# high-severity incident signal on an otherwise idle installation.
⋮----
state = (
````

## File: backend/app/evidence_chain.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class EvidenceChain
⋮----
finding_id: str
ancestor_ids: tuple[str, ...]
validation_ids: tuple[str, ...]
evidence_ids: tuple[str, ...]
source_count: int
dangling_parent_ids: tuple[str, ...]
cycle_detected: bool
independent_validation_observed: bool
complete: bool
issues: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
by_id = {item.id: item for item in graph.values()}
ancestors: set[str] = set()
dangling: set[str] = set()
cycle_detected = False
⋮----
def visit(current_id: str, path: tuple[str, ...]) -> None
⋮----
current = by_id.get(current_id)
⋮----
cycle_detected = True
⋮----
def build_evidence_chains(graph: ObservationGraph) -> list[EvidenceChain]
⋮----
"""Summarize support-chain integrity for findings without target actions."""
validation_state = analyze_validation_state(graph)
validations = graph.by_kind("validation")
evidence = graph.by_kind("evidence")
⋮----
chains: list[EvidenceChain] = []
⋮----
validation_ids = tuple(
validation_id_set = set(validation_ids)
evidence_ids = tuple(
⋮----
independent = finding.id in validation_state.observed_independent_finding_ids
⋮----
related_ids = {finding.id, *ancestors, *validation_ids, *evidence_ids}
sources = {
⋮----
issues = []
⋮----
@router.get("/api/campaigns/{campaign_id}/evidence-chains")
def campaign_evidence_chains(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
chains = build_evidence_chains(graph)
complete = sum(item.complete for item in chains)
````

## File: backend/app/evidence_quality.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class EvidenceQuality
⋮----
finding_id: str
score: float
grade: str
independent_validation: bool
artifact_backed: bool
integrity_attested: bool
source_count: int
chain_integrity: bool
corroborated: bool
components: dict[str, float]
issues: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _grade(score: float, *, integrity_attested: bool) -> str
⋮----
def build_evidence_quality(graph: ObservationGraph) -> list[EvidenceQuality]
⋮----
"""Score recorded evidence quality without changing finding state or executing work."""
chains = {item.finding_id: item for item in build_evidence_chains(graph)}
consensus = {
by_id = {item.id: item for item in graph.values()}
results: list[EvidenceQuality] = []
⋮----
chain = chains.get(finding.id)
finding_consensus = consensus.get(finding.id)
⋮----
evidence_items = [
artifact_backed = any(item.metadata.get("artifact_id") for item in evidence_items)
integrity_attested = any(
independent = bool(chain and chain.independent_validation_observed)
source_count = int(finding_consensus.source_count if finding_consensus else 0)
chain_integrity = bool(
corroborated = bool(finding_consensus and finding_consensus.corroborated)
⋮----
components = {
score = round(min(1.0, sum(components.values())), 4)
⋮----
issues: list[str] = []
⋮----
@router.get("/api/campaigns/{campaign_id}/evidence-quality")
def campaign_evidence_quality(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
quality = build_evidence_quality(graph)
````

## File: backend/app/finding_cluster_consensus.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class ClusterConsensus
⋮----
cluster_id: str
finding_ids: tuple[str, ...]
cluster_confidence: float
mean_readiness: float
min_readiness: float
max_readiness: float
report_ready_count: int
needs_validation_count: int
blocked_count: int
contradictory_count: int
status: str
blockers: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Aggregate finding readiness conservatively at cluster level."""
⋮----
readiness = {
⋮----
results: list[ClusterConsensus] = []
⋮----
members = [
scores = [item.readiness_score for item in members]
mean_readiness = round(sum(scores) / len(scores), 4) if scores else 0.0
min_readiness = round(min(scores), 4) if scores else 0.0
max_readiness = round(max(scores), 4) if scores else 0.0
⋮----
report_ready_count = sum(item.readiness == "report_review_ready" for item in members)
needs_validation_count = sum(item.readiness == "needs_validation" for item in members)
blocked_count = sum(item.readiness == "blocked" for item in members)
contradictory_count = sum(item.contradictory for item in members)
⋮----
blockers: list[str] = []
⋮----
status = "blocked"
⋮----
status = "report_review_ready"
⋮----
status = "needs_review"
⋮----
status = "needs_validation"
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-cluster-consensus")
def campaign_finding_cluster_consensus(campaign_id: str, threshold: float = 0.75)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
graph = load_observation_graph(store, campaign.id)
snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
consensus = build_cluster_consensus(
````

## File: backend/app/finding_cluster_saturation.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class ClusterSaturation
⋮----
cluster_id: str
finding_ids: tuple[str, ...]
cluster_confidence: float
saturated: bool
representative_finding_id: str | None
validations_saved: int
criteria: dict[str, bool]
reason: str
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
quality_by_id = {
observed_validated = {
⋮----
results: list[ClusterSaturation] = []
⋮----
representative = None
representative_quality = None
⋮----
quality = quality_by_id.get(finding_id)
⋮----
representative = finding_id
representative_quality = quality
⋮----
criteria = {
saturated = all(criteria.values())
validations_saved = max(0, len(cluster.finding_ids) - 1) if saturated else 0
reason = (
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-cluster-saturation")
def campaign_finding_cluster_saturation(campaign_id: str, threshold: float = 0.75)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
saturation = build_cluster_saturation(
````

## File: backend/app/finding_consensus.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class FindingConsensus
⋮----
finding_id: str
source_count: int
independent_validator_count: int
evidence_backed_validator_count: int
evidence_source_count: int
corroborated: bool
consensus_level: str
score: float
sources: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _children(graph: ObservationGraph) -> dict[str, list[Any]]
⋮----
result: dict[str, list[Any]] = {}
⋮----
def build_finding_consensus(graph: ObservationGraph) -> list[FindingConsensus]
⋮----
"""Measure independent evidence-backed corroboration from recorded observations."""
children = _children(graph)
results: list[FindingConsensus] = []
⋮----
validations = [
independent_validations = [
evidence_by_validation: dict[str, list[Any]] = {
evidence = [
⋮----
validator_sources = {item.source for item in independent_validations}
evidence_backed_validator_sources = {
evidence_sources = {item.source for item in evidence}
all_sources = {finding.source, *validator_sources, *evidence_sources}
⋮----
corroborated = bool(evidence_backed_validator_sources)
⋮----
consensus_level = "quorum"
⋮----
consensus_level = "single_evidence_backed_validator"
⋮----
consensus_level = "none"
⋮----
score = 0.30
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-consensus")
def campaign_finding_consensus(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
consensus = build_finding_consensus(graph)
````

## File: backend/app/finding_correlation.py
````python
router = APIRouter()
⋮----
_SEVERITY_ORDER = {
⋮----
def _canonical_url(value: str | None) -> str | None
⋮----
parsed = urlsplit(value)
host = (parsed.hostname or "").lower().rstrip(".")
⋮----
port = parsed.port
⋮----
port = None
⋮----
netloc = f"{host}:{port}"
⋮----
netloc = host
⋮----
@dataclass(frozen=True)
class FindingCorrelation
⋮----
key: str
finding_ids: tuple[str, ...]
asset: str
endpoint: str | None
cwe: str | None
highest_severity: str
duplicate_candidate: bool
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def correlate_findings(findings: list[Any]) -> list[FindingCorrelation]
⋮----
"""Group likely duplicates conservatively without auto-merging records."""
grouped: dict[tuple[str, str | None, str | None, str | None], list[Any]] = {}
⋮----
asset = _canonical_url(str(finding.asset)) or str(finding.asset).strip().lower()
endpoint = _canonical_url(finding.endpoint)
cwe = str(finding.cwe).strip().upper() if finding.cwe else None
title = str(finding.title).strip().lower() if finding.title else None
strong_identity = cwe or title
⋮----
correlations = []
⋮----
ordered = sorted(items, key=lambda item: str(item.id))
highest = max(
key = "|".join((asset, endpoint or "-", cwe or "-", strong_identity or "-"))
duplicate_candidate = len(ordered) > 1 and bool(endpoint or cwe)
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-correlations")
def campaign_finding_correlations(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
correlations = correlate_findings(campaign.findings)
duplicate_groups = [item for item in correlations if item.duplicate_candidate]
duplicate_findings = sum(len(item.finding_ids) for item in duplicate_groups)
⋮----
def _title_tokens(value: str | None) -> set[str]
⋮----
def _jaccard(left: set[str], right: set[str]) -> float
⋮----
@dataclass(frozen=True)
class FindingSimilarity
⋮----
left_id: str
right_id: str
score: float
same_asset: bool
same_endpoint: bool
same_cwe: bool
title_similarity: float
reasons: tuple[str, ...]
⋮----
@dataclass(frozen=True)
class FindingCluster
⋮----
cluster_id: str
⋮----
confidence: float
pair_scores: tuple[float, ...]
auto_merge: bool = False
⋮----
def score_finding_similarity(left: Any, right: Any) -> FindingSimilarity
⋮----
"""Return a conservative duplicate-likelihood score without merging findings."""
left_asset = _canonical_url(str(left.asset)) or str(left.asset).strip().lower()
right_asset = _canonical_url(str(right.asset)) or str(right.asset).strip().lower()
left_endpoint = _canonical_url(getattr(left, "endpoint", None))
right_endpoint = _canonical_url(getattr(right, "endpoint", None))
left_cwe = str(left.cwe).strip().upper() if getattr(left, "cwe", None) else None
right_cwe = str(right.cwe).strip().upper() if getattr(right, "cwe", None) else None
⋮----
same_asset = left_asset == right_asset
same_endpoint = bool(left_endpoint and right_endpoint and left_endpoint == right_endpoint)
same_cwe = bool(left_cwe and right_cwe and left_cwe == right_cwe)
title_similarity = _jaccard(
⋮----
components = {
score = round(sum(components.values()), 4)
⋮----
# Fail closed: cross-asset records never become duplicate candidates solely
# because they share a generic title/CWE.
⋮----
score = min(score, 0.40)
⋮----
reasons = tuple(
⋮----
"""Cluster likely duplicates non-destructively using high-confidence links."""
⋮----
ordered = sorted(findings, key=lambda item: str(item.id))
similarities: list[FindingSimilarity] = []
adjacency: dict[str, set[str]] = {str(item.id): set() for item in ordered}
⋮----
similarity = score_finding_similarity(left, right)
⋮----
clusters: list[FindingCluster] = []
visited: set[str] = set()
⋮----
root = str(finding.id)
⋮----
stack = [root]
component: set[str] = set()
⋮----
current = stack.pop()
⋮----
ids = tuple(sorted(component))
pair_scores = tuple(
confidence = round(
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-clusters")
def campaign_finding_clusters(campaign_id: str, threshold: float = 0.75)
````

## File: backend/app/finding_intelligence.py
````python
router = APIRouter()
⋮----
readiness = build_finding_readiness(
triage = build_finding_triage(findings, graph)
⋮----
cluster_consensus = build_cluster_consensus(
saturation = build_cluster_saturation(
differential_signals = build_differential_signals(graph)
⋮----
readiness_by_id = {item.finding_id: item for item in readiness}
triage_by_id = {item.finding_id: item for item in triage}
cluster_by_member = {
consensus_by_cluster = {item.cluster_id: item for item in cluster_consensus}
saturation_by_cluster = {item.cluster_id: item for item in saturation}
⋮----
finding_rows = []
⋮----
finding_id = str(finding.id)
readiness_item = readiness_by_id.get(finding_id)
triage_item = triage_by_id.get(finding_id)
cluster = cluster_by_member.get(finding_id)
cluster_id = cluster.cluster_id if cluster else None
differential_item = differential_signals.get(
⋮----
cluster_rows = []
⋮----
consensus = consensus_by_cluster.get(cluster.cluster_id)
saturated = saturation_by_cluster.get(cluster.cluster_id)
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-intelligence")
def campaign_finding_intelligence(campaign_id: str, threshold: float = 0.75)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
graph = load_observation_graph(store, campaign.id)
snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
payload = build_finding_intelligence(
````

## File: backend/app/finding_lifecycle.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class FindingLifecycleAdvice
⋮----
finding_id: str
current_state: str
recommended_state: str
transition_allowed: bool
prerequisites: tuple[str, ...]
human_decision_required: bool
graph_observed: bool
evidence_chain_integrity_ok: bool
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def build_finding_lifecycle(findings: list[Any], graph: ObservationGraph) -> list[FindingLifecycleAdvice]
⋮----
"""Recommend conservative finding-state transitions from existing evidence.

    This is read-only advisory logic. It cannot mutate findings, execute target
    actions, approve reports, or submit reports.
    """
validation = analyze_validation_state(graph)
chains = {item.finding_id: item for item in build_evidence_chains(graph)}
observed_finding_ids = {item.id for item in graph.by_kind("finding")}
duplicate_ids = {
⋮----
advice: list[FindingLifecycleAdvice] = []
⋮----
finding_id = str(finding.id)
graph_id = f"finding:{finding_id}"
current = str(finding.status)
graph_observed = graph_id in observed_finding_ids
independent = graph_id in validation.observed_independent_finding_ids
chain = chains.get(graph_id)
chain_complete = bool(chain and chain.complete)
chain_integrity_ok = bool(
duplicate = finding_id in duplicate_ids
⋮----
prerequisites: list[str] = []
human_required = False
⋮----
recommended = "validation_required"
allowed = True
⋮----
recommended = "human_confirm_or_reject"
allowed = not prerequisites
human_required = True
⋮----
recommended = "human_report_review"
⋮----
recommended = "terminal"
allowed = False
⋮----
recommended = "hold"
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-lifecycle")
def campaign_finding_lifecycle(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
advice = build_finding_lifecycle(campaign.findings, graph)
````

## File: backend/app/finding_readiness.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class FindingReadiness
⋮----
finding_id: str
readiness_score: float
readiness: str
severity_weight: float
confidence: float
evidence_quality: float
consensus_score: float
stability_score: float
contradictory: bool
blockers: tuple[str, ...]
components: dict[str, float]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Build an explainable, read-only readiness verdict for each finding."""
confidence_by_id = {
quality_by_id = {
consensus_by_id = {
stability_by_id = {
⋮----
results: list[FindingReadiness] = []
⋮----
finding_id = str(finding.id)
confidence = float(confidence_by_id.get(finding_id, 0.0))
quality = quality_by_id.get(finding_id)
consensus = consensus_by_id.get(finding_id)
stability = stability_by_id.get(finding_id, {})
⋮----
evidence_quality = float(quality.score if quality else 0.0)
consensus_score = float(consensus.score if consensus else 0.0)
stability_score = float(stability.get("stability_score", 0.0))
contradictory = stability.get("stability") == "contradictory"
⋮----
components = {
score = round(sum(components.values()), 4)
⋮----
blockers: list[str] = []
⋮----
readiness = "blocked"
⋮----
readiness = "report_review_ready"
⋮----
readiness = "needs_review"
⋮----
readiness = "needs_validation"
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-readiness")
def campaign_finding_readiness(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
graph = load_observation_graph(store, campaign.id)
snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
readiness = build_finding_readiness(
````

## File: backend/app/finding_triage.py
````python
router = APIRouter()
⋮----
_SEVERITY_WEIGHT = {
⋮----
@dataclass(frozen=True)
class FindingTriage
⋮----
finding_id: str
score: float
severity: str
confidence: float
evidence_chain_complete: bool
source_consensus_score: float
corroborated: bool
evidence_quality_score: float
evidence_quality_grade: str
duplicate_candidate: bool
duplicate_group_size: int
recommended_state: str
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def build_finding_triage(findings: list[Any], graph: ObservationGraph) -> list[FindingTriage]
⋮----
"""Rank findings using impact, evidence quality and duplicate pressure.

    This is an advisory, read-only ranking layer. It never confirms findings,
    merges records, queues jobs, or performs target actions.
    """
confidence_by_id = {
consensus_by_id = {
chains = {item.finding_id: item for item in build_evidence_chains(graph)}
quality_by_id = {item.finding_id: item for item in build_evidence_quality(graph)}
observed_finding_ids = {item.id for item in graph.by_kind("finding")}
duplicate_size: dict[str, int] = {}
⋮----
size = len(group.finding_ids)
⋮----
size = len(cluster.finding_ids)
⋮----
ranked: list[FindingTriage] = []
⋮----
finding_id = str(finding.id)
graph_id = f"finding:{finding_id}"
severity = str(finding.severity)
severity_weight = _SEVERITY_WEIGHT.get(severity, 0.0)
confidence = confidence_by_id.get(graph_id, 0.0)
consensus = consensus_by_id.get(finding_id)
consensus_score = consensus.score if consensus else 0.0
corroborated = bool(consensus and consensus.corroborated)
quality = quality_by_id.get(finding_id)
evidence_quality_score = quality.score if quality else 0.0
evidence_quality_grade = quality.grade if quality else "low"
chain = chains.get(graph_id)
chain_complete = bool(chain and chain.complete)
group_size = duplicate_size.get(finding_id, 1)
duplicate = group_size > 1
observed = graph_id in observed_finding_ids
⋮----
evidence_gap = 1.0 - confidence
chain_gap = 0.0 if chain_complete else 1.0
duplicate_discount = min(0.15, 0.05 * max(0, group_size - 1))
score = round(
⋮----
recommended = "resolved"
⋮----
recommended = "review_duplicate"
⋮----
recommended = "validate"
⋮----
recommended = "review_for_report"
⋮----
@router.get("/api/campaigns/{campaign_id}/finding-triage")
def campaign_finding_triage(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
triage = build_finding_triage(campaign.findings, graph)
````

## File: backend/app/hackerone_api.py
````python
router = APIRouter()
⋮----
class HackerOneProgramPolicyInput(BaseModel)
⋮----
model_config = ConfigDict(extra="forbid")
⋮----
authorization_reference: str = Field(min_length=3, max_length=2048)
policy_version: str = Field(min_length=1, max_length=256)
reviewed_at: datetime
reviewed_by: str = Field(min_length=1, max_length=256)
safe_harbor_confirmed: StrictBool
automated_scanning: StrictBool
max_requests_per_second: float = Field(gt=0, le=20)
test_account_required: StrictBool
test_account_constraints: str = Field(max_length=4096)
additional_restrictions: list[str] = Field(max_length=100)
program_notes: str = Field(max_length=8192)
⋮----
@field_validator("reviewed_at")
@classmethod
    def reviewed_at_must_be_timezone_aware(cls, value: datetime) -> datetime
⋮----
@field_validator("max_requests_per_second", mode="before")
@classmethod
    def request_rate_must_be_explicit_number(cls, value: Any) -> Any
⋮----
class HackerOneRulesPreviewInput(BaseModel)
⋮----
document: dict[str, Any]
policy: HackerOneProgramPolicyInput
⋮----
class HackerOneCampaignTargetInput(BaseModel)
⋮----
name: str = Field(min_length=2, max_length=120)
primary_url: HttpUrl
⋮----
class HackerOneCampaignAdmissionInput(HackerOneRulesPreviewInput)
⋮----
target: HackerOneCampaignTargetInput
⋮----
def _policy_from_input(payload: HackerOneProgramPolicyInput)
⋮----
def _json_sha256(value: Any) -> str
⋮----
encoded = json.dumps(
⋮----
def _conservative_admission_reason(policy: Any) -> str | None
⋮----
@router.post("/api/imports/hackerone/rules-preview")
def preview_hackerone_rules(payload: HackerOneRulesPreviewInput)
⋮----
"""Preview exact executable rules without persisting or starting a campaign."""
⋮----
preview = import_hackerone_structured_scope(payload.document)
policy = _policy_from_input(payload.policy)
rules = preview.to_program_rules(policy=policy)
⋮----
@router.post("/api/imports/hackerone/campaigns")
def admit_hackerone_campaign(payload: HackerOneCampaignAdmissionInput)
⋮----
reason = _conservative_admission_reason(policy)
⋮----
target = TargetInput(
⋮----
campaign = Campaign(target=target, state=CampaignState.ready)
policy_snapshot = policy.to_snapshot()
policy_snapshot_sha256 = _json_sha256(policy_snapshot)
campaign_policy_fingerprint = policy_snapshot_fingerprint(campaign)
binding_fingerprint = _json_sha256(
⋮----
@router.post("/api/imports/hackerone/campaigns/launch")
def launch_hackerone_campaign(payload: HackerOneCampaignAdmissionInput)
⋮----
"""Admit a reviewed HackerOne policy and start it in one authenticated mutation."""
⋮----
admitted = admit_hackerone_campaign(payload)
campaign_id = admitted["campaign"]["id"]
started = start_campaign(campaign_id)
campaign = assert_campaign_exists(campaign_id)
````

## File: backend/app/hackerone_binding.py
````python
def canonical_json_sha256(value: Any) -> str
⋮----
encoded = json.dumps(
⋮----
binding_events = [
⋮----
reasons: list[str] = []
⋮----
audit = verify_campaign_event_chain(campaign.events)
⋮----
binding = binding_events[-1]
⋮----
snapshot = binding.get("policy_snapshot")
⋮----
snapshot = {}
⋮----
declared_snapshot_hash = str(binding.get("policy_snapshot_sha256") or "")
actual_snapshot_hash = canonical_json_sha256(snapshot)
⋮----
restrictions = snapshot.get("additional_restrictions")
⋮----
declared_policy_fingerprint = str(binding.get("campaign_policy_fingerprint") or "")
⋮----
expected_binding_fingerprint = _binding_fingerprint(
declared_binding_fingerprint = str(binding.get("binding_fingerprint") or "")
````

## File: backend/app/hackerone_scope_import.py
````python
_MAX_SCOPE_ASSETS = 5000
_MAX_IDENTIFIER_CHARS = 2048
_MAX_POLICY_TEXT_CHARS = 8192
_MAX_RESTRICTIONS = 100
_MAX_RESTRICTION_CHARS = 1024
⋮----
class HackerOneScopeImportError(RuntimeError)
⋮----
def _reviewed_at(value: Any) -> str
⋮----
parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
⋮----
def _restrictions(value: Any) -> tuple[str, ...]
⋮----
normalized: list[str] = []
seen: set[str] = set()
⋮----
restriction = _explicit_text(
⋮----
@dataclass(frozen=True)
class HackerOneProgramPolicy
⋮----
"""Human-reviewed HackerOne program constraints required for rule conversion.

    StructuredScope describes assets only. It does not grant automation permission,
    define a safe request rate, or capture program-specific operating constraints.
    Every field here is therefore explicit and included in an immutable preview
    snapshot before a scope can become executable ProgramRules.
    """
⋮----
authorization_reference: str
policy_version: str
reviewed_at: str
reviewed_by: str
safe_harbor_confirmed: bool
automated_scanning: bool
max_requests_per_second: float
test_account_required: bool
test_account_constraints: str
additional_restrictions: tuple[str, ...]
program_notes: str
⋮----
def __post_init__(self) -> None
⋮----
rate = self.max_requests_per_second
⋮----
normalized_rate = float(rate)
⋮----
constraints = _explicit_text(
⋮----
def to_snapshot(self) -> dict[str, Any]
⋮----
@dataclass(frozen=True)
class HackerOneScopeAsset
⋮----
identifier: str
asset_type: str
eligible_for_submission: bool
host_pattern: str | None
compatible: bool
reason: str | None = None
⋮----
@dataclass(frozen=True)
class HackerOneScopePreview
⋮----
assets: tuple[HackerOneScopeAsset, ...]
allowed_targets: tuple[str, ...]
denied_targets: tuple[str, ...]
complete: bool
conflicts: tuple[str, ...]
unsupported: tuple[str, ...]
⋮----
def _clean_identifier(value: Any) -> str
⋮----
identifier = value.strip()
⋮----
def _canonical_asset_type(value: Any) -> str
⋮----
key = "".join(ch for ch in value.strip().lower() if ch.isalnum())
mapping = {
⋮----
def _ascii_domain(value: str) -> str
⋮----
candidate = value.rstrip(".").lower()
⋮----
ascii_value = candidate.encode("idna").decode("ascii")
⋮----
labels = ascii_value.split(".")
⋮----
def _compatible_host_pattern(asset_type: str, identifier: str) -> tuple[str | None, str | None]
⋮----
suffix = _ascii_domain(identifier[2:])
⋮----
parsed = urlparse(identifier)
hostname = parsed.hostname
username = parsed.username
password = parsed.password
⋮----
def _resource_attributes(resource: Any) -> dict[str, Any]
⋮----
attributes = resource.get("attributes")
⋮----
def import_hackerone_structured_scope(document: dict[str, Any]) -> HackerOneScopePreview
⋮----
links = document.get("links")
⋮----
data = document.get("data")
⋮----
resources = [data]
⋮----
resources = data
⋮----
assets: list[HackerOneScopeAsset] = []
statuses: dict[str, set[bool]] = {}
unsupported_labels: set[str] = set()
⋮----
attributes = _resource_attributes(resource)
identifier = _clean_identifier(attributes.get("asset_identifier"))
asset_type = _canonical_asset_type(attributes.get("asset_type"))
eligible = attributes.get("eligible_for_submission")
⋮----
compatible = host_pattern is not None
⋮----
conflicts = tuple(
allowed = tuple(
denied = tuple(
unsupported = tuple(sorted(unsupported_labels))
complete = not conflicts and not unsupported
````

## File: backend/app/hypothesis_engine.py
````python
HypothesisKind = Literal[
NextAction = Literal["scan", "validate", "stop"]
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class Hypothesis
⋮----
kind: HypothesisKind
target: str
reason: str
confidence: float
evidence_ids: tuple[str, ...]
next_action: NextAction
parameter_names: tuple[str, ...] = ()
dependency_depth: int = 0
read_only: bool = True
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _safe_endpoint(value: str) -> tuple[str, tuple[str, ...]]
⋮----
"""Return an endpoint representation that never exposes query values/fragments."""
parsed = urlsplit(value)
host = (parsed.hostname or "").lower().rstrip(".")
⋮----
port = parsed.port
⋮----
port = None
⋮----
netloc = f"{host}:{port}"
⋮----
netloc = host
safe_url = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))
parameter_names = tuple(sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}))
⋮----
def _lineage_hosts(graph: ObservationGraph, observation_id: str) -> set[str]
⋮----
by_id = {item.id: item for item in graph.values()}
hosts: set[str] = set()
seen: set[str] = set()
stack = [observation_id]
⋮----
current_id = stack.pop()
⋮----
current = by_id.get(current_id)
⋮----
host = current.value.strip().lower().rstrip(".")
⋮----
host = (urlsplit(host).hostname or "").lower().rstrip(".")
⋮----
host = (urlsplit(current.value).hostname or "").lower().rstrip(".")
⋮----
hosts = _lineage_hosts(graph, observation_id)
⋮----
"""Derive bounded, scope-aware review hypotheses from existing observations.

    This layer never emits payloads, exploit instructions, shell commands, or new
    network capabilities. When a scope checker is supplied, observations whose
    known lineage is entirely outside scope are excluded from review suggestions.
    """
⋮----
hypotheses: list[Hypothesis] = []
validation_state = analyze_validation_state(graph)
⋮----
path = urlsplit(endpoint.value).path.lower()
⋮----
input_names = tuple(
⋮----
confidence = float(waf.metadata.get("confidence", 0.5))
confidence = max(0.0, min(1.0, confidence))
⋮----
deduped: dict[tuple[str, str], Hypothesis] = {}
⋮----
key = (item.kind, item.target)
previous = deduped.get(key)
⋮----
@router.get("/api/campaigns/{campaign_id}/hypotheses")
def campaign_hypotheses(campaign_id: str, limit: int = 20)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
hypotheses = build_hypotheses(
counts: dict[str, int] = {}
````

## File: backend/app/hypothesis_memory.py
````python
@dataclass(frozen=True)
class Hypothesis
⋮----
id: str
finding_id: str
statement: str
confidence: float
status: str
graph_fingerprint: str
evidence_ids: tuple[str, ...] = ()
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def hypothesis_graph_fingerprint(graph: ObservationGraph) -> str
⋮----
relevant_ids = {item.id for item in graph.by_kind("finding")}
⋮----
payload = [
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
⋮----
def hypothesis_snapshot_is_current(hypothesis: Hypothesis, graph: ObservationGraph) -> bool
⋮----
def build_hypotheses(graph: ObservationGraph) -> list[Hypothesis]
⋮----
"""Build deterministic, read-only hypotheses from recorded findings.

    Hypotheses never authorize execution. They summarize evidence gaps for the
    bounded planner and preserve the existing policy/validation boundary.
    """
fingerprint = hypothesis_graph_fingerprint(graph)
validations = graph.by_kind("validation")
evidence = graph.by_kind("evidence")
result: list[Hypothesis] = []
⋮----
linked_validations = [
validation_ids = {item.id for item in linked_validations}
linked_evidence = [
observed = any(item.value == "observed" for item in linked_validations)
confidence = 0.35 + (0.40 if observed else 0.0) + (0.20 if linked_evidence else 0.0)
status = "supported" if observed and linked_evidence else (
⋮----
previous_items = {
current_items = {
⋮----
changes = []
⋮----
before = previous_items.get(finding_id)
after = current_items.get(finding_id)
⋮----
before_evidence = set(before.get("evidence_ids", []))
after_evidence = set(after.get("evidence_ids", []))
confidence_before = float(before.get("confidence", 0.0))
confidence_after = float(after.get("confidence", 0.0))
status_before = str(before.get("status", ""))
status_after = str(after.get("status", ""))
⋮----
evidence_added = sorted(after_evidence - before_evidence)
evidence_removed = sorted(before_evidence - after_evidence)
confidence_delta = round(confidence_after - confidence_before, 4)
⋮----
"""Summarize temporal stability from newest-first persisted snapshots."""
⋮----
ordered = list(reversed(snapshots))
finding_ids = sorted(
result = []
⋮----
timeline = []
⋮----
match = next(
⋮----
latest = timeline[-1]
stable_streak = 1
⋮----
status_transitions = sum(
confidence_reversals = 0
previous_direction = 0
⋮----
delta = round(after["confidence"] - before["confidence"], 4)
direction = 1 if delta > 0 else (-1 if delta < 0 else 0)
⋮----
previous_direction = direction
⋮----
contradictory = confidence_reversals > 0 or status_transitions >= 2
⋮----
stability = "contradictory"
⋮----
stability = "stable"
⋮----
stability = "fresh"
⋮----
stability = "evolving"
⋮----
score = 0.40
⋮----
score = round(max(0.0, min(1.0, score)), 2)
````

## File: backend/app/incident_api.py
````python
class IncidentApiConflict(RuntimeError)
⋮----
def read_incident_status(store: IncidentStore) -> dict[str, Any]
⋮----
active_by_domain = active_incidents_by_domain(history)
active = [item for item in active_by_domain.values() if item is not None]
⋮----
updated = acknowledge_incident(history, fingerprint)
⋮----
new_version = store.write(updated, expected_version=current_version)
````

## File: backend/app/incident_domains.py
````python
_SEVERITY = {"healthy": 0, "degraded": 1, "critical": 2}
⋮----
def _state(value: Any) -> str
⋮----
raw = str(value or "healthy").lower()
⋮----
def _fingerprint(domain: str, signals: list[dict[str, str]]) -> str
⋮----
raw = json.dumps(
⋮----
"""Create independent redacted incident snapshots per operational domain."""
domain_sources = {
⋮----
incidents: dict[str, dict[str, Any] | None] = {}
overall = "healthy"
⋮----
signals = [
⋮----
severity = max((item["state"] for item in signals), key=lambda s: _SEVERITY[s])
⋮----
overall = severity
fingerprint = _fingerprint(domain, signals)
````

## File: backend/app/incident_engine.py
````python
_SEVERITY = {"healthy": 0, "degraded": 1, "warning": 1, "critical": 2, "error": 2}
⋮----
def _state(value: Any) -> str
⋮----
raw = str(value or "healthy").lower()
⋮----
def _fingerprint(signals: list[dict[str, str]]) -> str
⋮----
canonical = json.dumps(signals, sort_keys=True, separators=(",", ":")).encode()
⋮----
"""Fuse redacted operational signals into one deterministic incident snapshot."""
sources = {
overall = max(sources.values(), key=lambda item: _SEVERITY[item])
⋮----
signals: list[dict[str, str]] = []
⋮----
incident = None
⋮----
incident = {
````

## File: backend/app/incident_lifecycle.py
````python
MAX_HISTORY = 1000
⋮----
def _now(value: datetime | None = None) -> str
⋮----
"""Persist lifecycle transitions from a redacted incident snapshot."""
items = [dict(item) for item in history[-MAX_HISTORY:]]
incident = snapshot.get("incident")
active = next((item for item in reversed(items) if item.get("status") != "resolved"), None)
⋮----
fingerprint = str(incident["fingerprint"])
severity = str(incident["severity"])
⋮----
timestamp = _now(now)
⋮----
def incident_reliability_stats(history: list[dict[str, Any]]) -> dict[str, Any]
⋮----
durations = []
openings = []
⋮----
opened = datetime.fromisoformat(str(item["opened_at"]))
⋮----
resolved = datetime.fromisoformat(str(item["resolved_at"]))
⋮----
mttr = sum(durations) / len(durations) if durations else None
gaps = [
mtbf = sum(gaps) / len(gaps) if gaps else None
````

## File: backend/app/incident_observer.py
````python
"""Evaluate and persist operational incident state without execution side effects."""
slo = build_operational_slo(metrics)
budget = build_error_budget_status(telemetry)
watchdog = metrics.get("worker_watchdog") or {"status": "error"}
observer_metrics = observer_health_metrics(observer_runtime().snapshot())
observer_slo = build_observer_slo(observer_metrics)
snapshot = build_domain_incidents(watchdog, slo, budget, observer_slo)
⋮----
updated = apply_domain_incidents(history, snapshot)
⋮----
new_version = store.write(
⋮----
"""Single scheduler-friendly observation pass."""
````

## File: backend/app/incident_store.py
````python
class IncidentStoreConflict(RuntimeError)
⋮----
class IncidentFenceConflict(IncidentStoreConflict)
⋮----
class IncidentStore
⋮----
"""Transactional SQLite persistence for redacted operational incident history."""
⋮----
def __init__(self, db_path: str)
⋮----
def _connect(self)
⋮----
db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
⋮----
def _init(self) -> None
⋮----
def read(self) -> tuple[list[dict[str, Any]], int]
⋮----
row = db.execute(
⋮----
document = json.dumps(history, sort_keys=True, separators=(",", ":"))
⋮----
lease = db.execute(
⋮----
now = datetime.now(timezone.utc)
expires = datetime.fromisoformat(lease["expires_at"]) if lease["expires_at"] else None
⋮----
cursor = db.execute(
````

## File: backend/app/job_provenance.py
````python
PROVENANCE_SCHEMA = "job-provenance-v1"
⋮----
class JobProvenanceError(RuntimeError)
⋮----
def stable_policy_snapshot(campaign: Any) -> dict[str, Any]
⋮----
"""Return deterministic policy state relevant to worker admission."""
rules = campaign.target.rules
host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
⋮----
def policy_snapshot_fingerprint(campaign: Any) -> str
⋮----
encoded = json.dumps(
⋮----
snapshot = stable_policy_snapshot(campaign)
policy_fingerprint = policy_snapshot_fingerprint(campaign)
binding = verify_hackerone_campaign_binding(
⋮----
provenance = {
⋮----
def verify_job_provenance(job: dict[str, Any], campaign: Any) -> dict[str, Any]
⋮----
payload = job.get("payload")
provenance = payload.get("_provenance") if isinstance(payload, dict) else None
reasons: list[str] = []
⋮----
expected = policy_snapshot_fingerprint(campaign)
actual = str(provenance.get("policy_fingerprint") or "")
⋮----
declared_rps = float(provenance.get("request_rate_limit"))
⋮----
def require_job_provenance(job: dict[str, Any], campaign: Any) -> dict[str, Any]
⋮----
verification = verify_job_provenance(job, campaign)
⋮----
GOVERNED_JOB_KINDS = frozenset(
⋮----
def provenance_required_for_job_kind(job_kind: str) -> bool
````

## File: backend/app/jobqueue.py
````python
TERMINAL = {"completed", "failed", "cancelled"}
⋮----
def utcnow() -> str
⋮----
def _bounded_identifier(value: str, name: str, *, max_length: int = 200) -> str
⋮----
normalized = value.strip()
⋮----
def _job_lease_seconds() -> int
⋮----
raw = os.getenv("XBOW_JOB_LEASE_SECONDS", "21600")
⋮----
lease_seconds = int(raw)
⋮----
def _harden_db_permissions(path: Path) -> None
⋮----
def _max_job_payload_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_JOB_PAYLOAD_BYTES", "65536")
⋮----
limit = int(raw)
⋮----
class JobQueue
⋮----
"""Small durable SQLite queue for self-hosted single-node deployments.

    Jobs contain only validated execution plans, never arbitrary shell strings.
    Workers claim jobs atomically. Running jobs use a durable lease so a worker
    crash cannot strand a campaign forever; expired leases are recovered on the
    next claim without bypassing retry limits.
    """
⋮----
def __init__(self, path: str | None = None)
⋮----
@contextmanager
    def connect(self)
⋮----
db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
⋮----
def _init(self) -> None
⋮----
columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
⋮----
def health(self) -> dict[str, Any]
⋮----
"""Return minimal storage health without exposing job payloads."""
⋮----
quick_check = db.execute("PRAGMA quick_check").fetchone()[0]
count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
⋮----
campaign_id = _bounded_identifier(campaign_id, "campaign_id")
⋮----
dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")
⋮----
encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
⋮----
existing = db.execute(
⋮----
decoded = self._decode(existing)
⋮----
result = self.get(job_id)
⋮----
def get(self, job_id: str) -> dict[str, Any] | None
⋮----
job_id = _bounded_identifier(job_id, "job_id")
⋮----
row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
⋮----
kind = _bounded_identifier(kind, "kind")
⋮----
row = db.execute(
⋮----
def stats(self) -> dict[str, Any]
⋮----
"""Return bounded operational queue telemetry without exposing payloads."""
⋮----
rows = db.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
total = db.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
oldest = db.execute(
oldest_running = db.execute(
counts = {status: 0 for status in ("queued", "running", "completed", "failed", "cancelled")}
⋮----
def campaign_job_counts(self, campaign_id: str) -> dict[str, int]
⋮----
"""Return durable job counts for one campaign without exposing payloads."""
⋮----
rows = db.execute(
counts = {kind: 0 for kind in ("strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status")}
⋮----
def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]
⋮----
"""Return per-status job counts for one campaign without exposing payloads."""
⋮----
def cancel_queued(self, campaign_id: str) -> int
⋮----
"""Cancel queued jobs for a campaign without stealing running leases."""
⋮----
now = utcnow()
⋮----
cursor = db.execute(
⋮----
def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict[str, Any] | None
⋮----
"""Cancel a running job only when the caller still owns its lease."""
⋮----
worker_id = _bounded_identifier(worker_id, "worker_id")
reason = reason.strip()
⋮----
reason = reason[-4000:]
⋮----
def _recover_expired_leases(self, db: sqlite3.Connection, now: datetime) -> int
⋮----
lease_seconds = _job_lease_seconds()
cutoff = (now - timedelta(seconds=lease_seconds)).isoformat()
stale = db.execute(
⋮----
exhausted = row["attempts"] >= row["max_attempts"]
status = "failed" if exhausted else "queued"
⋮----
def recover_expired_leases(self) -> int
⋮----
"""Recover jobs abandoned by dead workers while respecting max_attempts."""
⋮----
count = self._recover_expired_leases(db, datetime.now(timezone.utc))
⋮----
def claim(self, worker_id: str) -> dict[str, Any] | None
⋮----
now_dt = datetime.now(timezone.utc)
⋮----
now = now_dt.isoformat()
⋮----
claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
⋮----
def claim_allowed(self, worker_id: str, kinds: tuple[str, ...] | list[str]) -> dict[str, Any] | None
⋮----
"""Atomically claim the oldest queued job among an explicit set of kinds."""
⋮----
allowed_kinds = {
normalized = tuple(dict.fromkeys(_bounded_identifier(kind, "kind") for kind in kinds))
⋮----
placeholders = ",".join("?" for _ in normalized)
⋮----
def claim_kind(self, worker_id: str, kind: str) -> dict[str, Any] | None
⋮----
"""Atomically claim only one explicitly requested job kind."""
⋮----
allowed_kinds = {"strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status"}
⋮----
def heartbeat(self, job_id: str, worker_id: str) -> bool
⋮----
"""Renew a running job lease only when the caller still owns it."""
⋮----
"""Finish a job only if the caller still owns its running lease.

        Returns None when ownership has already been lost. This prevents a stale
        worker from completing or requeueing work that another worker has claimed.
        """
⋮----
status = "completed" if success else ("queued" if row["attempts"] < row["max_attempts"] else "failed")
⋮----
@staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]
⋮----
result = dict(row)
````

## File: backend/app/knowledge_memory.py
````python
SEVERITY_WEIGHTS = {
⋮----
REVIEW_SEVERITY_BONUS = {
⋮----
TEMPORAL_NEED = {
⋮----
def severity_weight(value: Any) -> float
⋮----
def review_severity_bonus(value: Any) -> float
⋮----
def temporal_need(value: Any) -> float
⋮----
@dataclass(frozen=True)
class FindingConfidence
⋮----
finding_id: str
score: float
validation_count: int
evidence_count: int
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
@dataclass(frozen=True)
class FindingPriority
⋮----
severity_weight: float
confidence: float
⋮----
@dataclass(frozen=True)
class KnowledgeSnapshot
⋮----
observations: int
assets: int
endpoints: int
findings: int
validations: int
evidence: int
finding_confidence: tuple[FindingConfidence, ...]
⋮----
payload = asdict(self)
⋮----
def _validation_quality(value: str) -> float
⋮----
"""Return bounded confidence credit for a validator outcome.

    A dry run proves policy/plumbing only, an error proves nothing about the target,
    and an observed response is useful evidence without self-confirming a finding.
    Unknown outcomes fail closed and receive no validation credit.
    """
⋮----
def build_knowledge_snapshot(graph: ObservationGraph) -> KnowledgeSnapshot
⋮----
assets = graph.by_kind("asset")
endpoints = graph.by_kind("endpoint")
findings = graph.by_kind("finding")
validations = graph.by_kind("validation")
evidence = graph.by_kind("evidence")
⋮----
scores: list[FindingConfidence] = []
⋮----
linked_validations = [item for item in validations if finding.id in item.parent_ids]
independent_validations = [item for item in linked_validations if item.source != finding.source]
credited_validations = [
observed_validation_ids = {
observed_evidence = [
⋮----
best_validation_credit = max(
score = 0.35 + best_validation_credit
⋮----
def rank_findings(findings: list[Any], graph: ObservationGraph) -> list[FindingPriority]
⋮----
"""Rank findings for independent validation using impact and evidence gaps.

    Higher severity raises priority while stronger existing evidence lowers the
    urgency for another validation pass. Ties are deterministic by finding id.
    """
confidence = {
ranked = []
⋮----
finding_id = f"finding:{finding.id}"
confidence_score = confidence.get(finding_id, 0.0)
severity_weight_value = severity_weight(finding.severity)
score = round((severity_weight_value * 0.70) + ((1.0 - confidence_score) * 0.30), 4)
⋮----
"""Return a read-only global ranking with auditable score components."""
⋮----
finding_id = str(finding.id)
⋮----
temporal = (stability or {}).get(finding_id, {})
temporal_state = temporal.get("stability")
temporal_need_value = temporal_need(temporal_state)
evidence_gap = 1.0 - confidence_score
components = {
score = round(sum(components.values()), 4)
⋮----
def decision_history(graph: ObservationGraph) -> list[dict[str, Any]]
⋮----
history = []
````

## File: backend/app/learning_memory.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class TechniqueMemory
⋮----
technique: str
attempts: int
successes: int
failures: int
inconclusive: int
success_rate: float
confidence: float
source_count: int
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def build_learning_memory(graph: ObservationGraph, *, limit: int = 50) -> list[TechniqueMemory]
⋮----
"""Aggregate safe technique outcomes from existing evidence only.

    Evidence contributes only when it carries an explicit technique and outcome.
    No target interaction, payload generation, or autonomous execution happens here.
    """
⋮----
buckets: dict[str, dict[str, Any]] = defaultdict(
⋮----
technique = str(item.metadata.get("technique", "")).strip().lower()
outcome = str(item.metadata.get("outcome", "")).strip().lower()
⋮----
bucket = buckets[technique]
⋮----
memories: list[TechniqueMemory] = []
⋮----
attempts = int(bucket["attempts"])
successes = int(bucket["successes"])
failures = int(bucket["failures"])
conclusive = successes + failures
success_rate = round(successes / conclusive, 4) if conclusive else 0.0
confidence = round(min(1.0, conclusive / 5) * min(1.0, len(bucket["sources"]) / 2), 4)
⋮----
@router.get("/api/campaigns/{campaign_id}/learning-memory")
def campaign_learning_memory(campaign_id: str, limit: int = 50)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
memories = build_learning_memory(graph, limit=limit)
⋮----
_ALLOWED_JOB_KINDS = {
_ALLOWED_JOB_STATUSES = {"queued", "completed", "failed", "cancelled"}
⋮----
def worker_outcome_event(job: dict[str, Any], *, success: bool, status: str) -> dict[str, Any]
⋮----
"""Build a bounded learning event without persisting job payloads or errors."""
kind = str(job.get("kind") or "")
⋮----
attempts = int(job.get("attempts") or 0)
⋮----
totals = {"completed": 0, "failed": 0, "cancelled": 0, "requeued": 0}
by_kind: dict[str, dict[str, int]] = defaultdict(
recent: list[dict[str, Any]] = []
⋮----
kind = str(event.get("job_kind") or "")
status = str(event.get("status") or "")
⋮----
bucket = "requeued" if status == "queued" else status
````

## File: backend/app/main.py
````python
app = FastAPI(title="xbow-perso", version="0.4.0")
⋮----
@app.middleware("http")
async def authenticate_control_api(request: Request, call_next)
⋮----
headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
⋮----
def utcnow() -> str
⋮----
def storage() -> StorageBackend
⋮----
def queue() -> QueueBackend
⋮----
def incident_store() -> IncidentStore
⋮----
store = storage()
db_path = getattr(store, "db_path", None)
⋮----
def _stable_key(prefix: str, *parts: str) -> str
⋮----
digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
⋮----
class CampaignState(str, Enum)
⋮----
draft = "draft"
ready = "ready"
running = "running"
validating = "validating"
completed = "completed"
failed = "failed"
cancelled = "cancelled"
⋮----
class ProgramRules(BaseModel)
⋮----
authorization_reference: str = Field(min_length=3)
allowed_targets: list[str] = Field(min_length=1)
denied_targets: list[str] = Field(default_factory=list)
max_requests_per_second: float = Field(default=2.0, gt=0, le=20)
destructive_testing: bool = False
denial_of_service: bool = False
social_engineering: bool = False
credential_attacks: bool = False
automated_scanning: bool = True
notes: str = ""
⋮----
class TargetInput(BaseModel)
⋮----
name: str = Field(min_length=2, max_length=120)
primary_url: HttpUrl
rules: ProgramRules
credentials_note: str | None = None
⋮----
@model_validator(mode="after")
    def primary_target_must_be_allowed(self)
⋮----
parsed = urlparse(str(self.primary_url))
host = (parsed.hostname or "").lower()
⋮----
class Finding(BaseModel)
⋮----
id: str = Field(default_factory=lambda: str(uuid4()))
title: str
severity: Literal["info", "low", "medium", "high", "critical"]
asset: str
endpoint: str | None = None
summary: str
evidence: list[str] = Field(default_factory=list)
reproduction_steps: list[str] = Field(default_factory=list)
impact: str = ""
remediation: str = ""
cwe: str | None = None
cvss: float | None = Field(default=None, ge=0, le=10)
status: Literal["candidate", "validation_required", "confirmed", "rejected"] = "candidate"
discovered_by: str = "unknown"
validated_by: str | None = None
⋮----
class Campaign(BaseModel)
⋮----
target: TargetInput
state: CampaignState = CampaignState.draft
created_at: str = Field(default_factory=utcnow)
updated_at: str = Field(default_factory=utcnow)
findings: list[Finding] = Field(default_factory=list)
events: list[dict[str, Any]] = Field(default_factory=list)
⋮----
class EvidenceInput(BaseModel)
⋮----
kind: Literal["scanner_stdout", "scanner_stderr", "http_evidence", "validation", "report"]
content: str = Field(max_length=1_000_000)
media_type: str = Field(default="text/plain", max_length=120)
finding_id: str | None = None
⋮----
class HackerOneScopePreviewInput(BaseModel)
⋮----
document: dict[str, Any]
⋮----
class IncidentAcknowledgeInput(BaseModel)
⋮----
fingerprint: str = Field(min_length=1, max_length=64, pattern=r"^[0-9a-f]+$")
expected_version: int = Field(ge=1)
⋮----
def normalize_pattern(pattern: str) -> str
⋮----
value = pattern.strip().lower()
⋮----
value = (urlparse(value).hostname or value).lower()
⋮----
def is_host_allowed(host: str, allowed: list[str], denied: list[str]) -> bool
⋮----
host = host.lower().rstrip(".")
denied_patterns = [normalize_pattern(x) for x in denied]
⋮----
allowed_patterns = [normalize_pattern(x) for x in allowed]
⋮----
def save_campaign(campaign: Campaign, *, expected_version: int | None = None) -> int
⋮----
def assert_campaign_record(campaign_id: str) -> tuple[Campaign, int]
⋮----
record = storage().get_campaign_record(campaign_id)
⋮----
def assert_campaign_exists(campaign_id: str) -> Campaign
⋮----
def _reject_cancelled_campaign(campaign: Campaign) -> None
⋮----
def _reject_new_findings_for_closed_campaign(campaign: Campaign) -> None
⋮----
def _campaign_graph(campaign_id: str)
⋮----
def _has_evidence_backed_independent_validation(campaign_id: str, finding: Finding) -> bool
⋮----
graph = _campaign_graph(campaign_id)
⋮----
def policy_receipt(campaign: Campaign, host: str, action: str) -> dict[str, Any]
⋮----
rules = campaign.target.rules
allowed = is_host_allowed(host, rules.allowed_targets, rules.denied_targets)
blocked_actions = {
action_known = action in blocked_actions
action_blocked = blocked_actions.get(action, True)
⋮----
"""Return deterministic worker input suitable for queue idempotency.

    The audit receipt keeps its timestamp in campaign events/API responses, but
    transient timestamps must never enter a deduplicated queue payload.
    """
transient = {"timestamp", "receipt_hash", "signature", "signature_alg", "integrity_mode"}
stable_receipt = {key: value for key, value in receipt.items() if key not in transient}
payload = {
⋮----
@app.get("/live")
def live()
⋮----
@app.get("/ready")
def ready()
⋮----
dependencies = dependency_readiness()
⋮----
@app.get("/health")
def health()
⋮----
database_ok = bool(queue().health().get("ok"))
⋮----
database_ok = False
⋮----
@app.get("/api/deployment/preflight")
def deployment_preflight()
⋮----
@app.get("/api/capabilities")
def system_capabilities()
⋮----
pentagi = safe_pentagi_runtime_capability()
scanners = safe_scanner_runtime_capability()
⋮----
@app.get("/api/observer/health")
def get_observer_health()
⋮----
@app.get("/api/incidents")
def get_incidents()
⋮----
@app.post("/api/incidents/acknowledge")
def acknowledge_incident(payload: IncidentAcknowledgeInput)
⋮----
@app.get("/api/agents")
def list_agents()
⋮----
@app.post("/api/imports/hackerone/scope-preview")
def preview_hackerone_scope(payload: HackerOneScopePreviewInput)
⋮----
preview = import_hackerone_structured_scope(payload.document)
⋮----
@app.post("/api/campaigns", response_model=Campaign)
def create_campaign(target: TargetInput)
⋮----
campaign = Campaign(target=target, state=CampaignState.ready)
⋮----
@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns()
⋮----
@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/outbox")
def campaign_outbox_status(campaign_id: str, limit: int = 100)
⋮----
campaign = assert_campaign_exists(campaign_id)
⋮----
snapshot = outbox_snapshot(campaign.events, max_items=limit)
⋮----
@app.get("/api/campaigns/{campaign_id}/outbox/recovery")
def campaign_outbox_recovery(campaign_id: str)
⋮----
diagnostics = diagnose_outbox_recovery(
⋮----
repaired = 0
skipped_ambiguous = 0
⋮----
intent = diagnostic.get("_intent") or {}
job = diagnostic.get("_job") or {}
⋮----
job_status = str(job.get("status") or "")
⋮----
event = local_completion_event(diagnostic, at=utcnow())
⋮----
@app.post("/api/campaigns/{campaign_id}/outbox/reconcile-local")
def reconcile_campaign_outbox_local(campaign_id: str)
⋮----
jobs = queue()
last_conflict: HTTPException | None = None
⋮----
last_conflict = exc
⋮----
latest = assert_campaign_exists(campaign.id)
remaining = diagnose_outbox_recovery(
⋮----
@app.get("/api/campaigns/{campaign_id}/pentagi/preview")
def preview_pentagi_campaign(campaign_id: str)
⋮----
preview = prepare_pentagi_control_preview(campaign)
⋮----
def _pentagi_dispatch_fingerprint(idempotency_key: str) -> str
⋮----
@app.post("/api/campaigns/{campaign_id}/pentagi/dispatch")
def dispatch_pentagi_campaign(campaign_id: str)
⋮----
preview = require_pentagi_control_ready(campaign)
permit = prepare_pentagi_execution_permit(campaign, preview.plan)
dispatch_fingerprint = _pentagi_dispatch_fingerprint(permit.idempotency_key)
⋮----
job = enqueue_pentagi_flow(
⋮----
campaign = _reconcile_pentagi_queued_event(
safe_job = {
⋮----
@app.get("/api/campaigns/{campaign_id}/pentagi")
def pentagi_campaign_status(campaign_id: str)
⋮----
counts = queue().campaign_job_counts(campaign.id)
artifacts = [
⋮----
@app.get("/api/campaigns/{campaign_id}/observations")
def list_campaign_observations(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/audit/decisions")
def campaign_decision_audit(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/audit/events")
def campaign_event_audit(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/audit/workers")
def campaign_worker_audit(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/knowledge")
def campaign_knowledge(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/findings/ranking")
def campaign_finding_ranking(campaign_id: str, history_limit: int = 50)
⋮----
snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=history_limit)
⋮----
stability = {
⋮----
@app.get("/api/campaigns/{campaign_id}/advisory/history")
def campaign_advisory_history(campaign_id: str, limit: int = 50)
⋮----
@app.get("/api/campaigns/{campaign_id}/advisory/delta")
def campaign_advisory_delta(campaign_id: str)
⋮----
snapshots = storage().list_advisory_focus_snapshots(campaign_id, limit=2)
current = snapshots[0] if snapshots else None
previous = snapshots[1] if len(snapshots) > 1 else None
⋮----
@app.get("/api/campaigns/{campaign_id}/advisory/journal")
def campaign_advisory_journal(campaign_id: str, limit: int = 100)
⋮----
snapshots = storage().list_advisory_focus_snapshots(campaign_id, limit=min(limit + 1, 500))
⋮----
@app.get("/api/campaigns/{campaign_id}/hypotheses/history")
def campaign_hypothesis_history(campaign_id: str, limit: int = 50)
⋮----
@app.get("/api/campaigns/{campaign_id}/hypotheses/delta")
def campaign_hypothesis_delta(campaign_id: str)
⋮----
snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=2)
⋮----
@app.get("/api/campaigns/{campaign_id}/hypotheses/stability")
def campaign_hypothesis_stability(campaign_id: str, limit: int = 50)
⋮----
snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=limit)
⋮----
@app.get("/api/campaigns/{campaign_id}/plan")
def campaign_plan(campaign_id: str)
⋮----
limits = planner_budget_from_env()
planner_actions = AdaptivePlanner().plan(campaign, graph)
actions = [apply_budget(item, graph, jobs, campaign.id, limits)[0] for item in planner_actions]
usage = budget_usage(graph, jobs, campaign.id, limits)
⋮----
snapshots = storage().list_hypothesis_snapshots(campaign.id, limit=50)
⋮----
advisory = build_advisory_planner_context(
advisory_fingerprint = advisory_focus_fingerprint(advisory)
⋮----
@app.post("/api/campaigns/{campaign_id}/policy-check")
def check_policy(campaign_id: str, host: str, action: str = "automated_scan")
⋮----
receipt = policy_receipt(campaign, host, action)
⋮----
@app.post("/api/campaigns/{campaign_id}/policy-verify")
def verify_campaign_policy_receipt(campaign_id: str, receipt: dict[str, Any] = Body(...))
⋮----
def _pending_campaign_start_request(campaign: Campaign) -> str | None
⋮----
@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str)
⋮----
host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
receipt = policy_receipt(campaign, host, "automated_scan")
⋮----
hackerone_bound = any(
job_kind = "nuclei_scan" if hackerone_bound else "strix_scan"
payload = sanitized_scan_payload(campaign, receipt, job_kind=job_kind)
request_id = _pending_campaign_start_request(campaign) or str(uuid4())
⋮----
job = queue().enqueue(
campaign = _reconcile_campaign_started(
⋮----
@app.post("/api/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: str)
⋮----
statuses = jobs.campaign_job_status_counts(campaign.id)
⋮----
cancelled = jobs.cancel_queued(campaign.id)
⋮----
@app.get("/api/jobs/{job_id}")
def get_job(job_id: str)
⋮----
job = queue().get(job_id)
⋮----
@app.get("/api/jobs/{job_id}/provenance")
def get_job_provenance_status(job_id: str)
⋮----
campaign = assert_campaign_exists(str(job["campaign_id"]))
verification = verify_job_provenance(job, campaign)
⋮----
def _validation_request_id(finding_id: str) -> str
⋮----
current = next((item for item in campaign.findings if item.id == finding_id), None)
⋮----
@app.post("/api/campaigns/{campaign_id}/findings", response_model=Finding)
def add_finding(campaign_id: str, finding: Finding)
⋮----
host = (urlparse(finding.asset).hostname or finding.asset.split(":")[0]).lower()
⋮----
request_id = _validation_request_id(finding.id)
existing = next((item for item in campaign.findings if item.id == finding.id), None)
⋮----
candidate = finding.model_copy(update={"status": existing.status, "validated_by": existing.validated_by})
⋮----
current = next((item for item in latest.findings if item.id == finding.id), None)
⋮----
validation_job = queue().enqueue(
⋮----
identity = {
⋮----
def _ensure_completion_report(campaign: Campaign, version: int) -> Campaign
⋮----
request_id = "report:generic:completed"
platform = "generic"
purpose = "campaign_completion"
⋮----
report_job = queue().enqueue(
⋮----
@app.post("/api/campaigns/{campaign_id}/findings/{finding_id}/validate")
def validate_finding(campaign_id: str, finding_id: str, confirmed: bool, validator: str = "independent-validator")
⋮----
finding = next((x for x in campaign.findings if x.id == finding_id), None)
⋮----
desired_status = "confirmed" if confirmed else "rejected"
⋮----
completed = _ensure_completion_report(campaign, version)
⋮----
should_complete = bool(
⋮----
completed = _ensure_completion_report(latest, latest_version)
⋮----
@app.post("/api/campaigns/{campaign_id}/reports")
def queue_report(campaign_id: str, platform: Literal["generic", "hackerone", "bugcrowd"] = "generic")
⋮----
purpose = "manual"
request_id = pending_request_id(
⋮----
@app.post("/api/campaigns/{campaign_id}/artifacts")
def add_text_artifact(campaign_id: str, evidence: EvidenceInput = Body(...))
⋮----
content = evidence.content.encode("utf-8")
idempotency_key = _stable_key(
⋮----
artifact = storage().put_artifact(
⋮----
@app.get("/api/campaigns/{campaign_id}/artifacts")
def list_artifacts(campaign_id: str)
⋮----
@app.get("/api/campaigns/{campaign_id}/artifacts/{artifact_id}")
def download_artifact(campaign_id: str, artifact_id: str)
⋮----
from .browser import router as browser_router  # noqa: E402
from .campaign_control import router as campaign_control_router  # noqa: E402
from .coverage import router as coverage_router  # noqa: E402
from .decision_timeline import router as decision_timeline_router  # noqa: E402
from .evidence_quality import router as evidence_quality_router  # noqa: E402
from .finding_cluster_consensus import router as finding_cluster_consensus_router  # noqa: E402
from .finding_cluster_saturation import router as finding_cluster_saturation_router  # noqa: E402
from .finding_intelligence import router as finding_intelligence_router  # noqa: E402
from .finding_correlation import router as finding_correlation_router  # noqa: E402
from .finding_readiness import router as finding_readiness_router  # noqa: E402
from .metrics import router as metrics_router  # noqa: E402
from .operational_alerts import router as alerts_router  # noqa: E402
from .report_readiness import router as report_readiness_router  # noqa: E402
from .review_queue import router as review_queue_router  # noqa: E402
````

## File: backend/app/metrics.py
````python
router = APIRouter()
⋮----
def _age_seconds(value: Any, *, now: datetime | None = None) -> int | None
⋮----
created = datetime.fromisoformat(str(value))
⋮----
created = created.replace(tzinfo=timezone.utc)
current = now or datetime.now(timezone.utc)
⋮----
def build_operational_metrics(queue_backend, storage_backend) -> dict[str, Any]
⋮----
queue_stats = queue_backend.stats()
campaigns = storage_backend.list_campaigns()
states = Counter(str(item.get("state") or "unknown") for item in campaigns)
⋮----
by_status = dict(queue_stats.get("by_status") or {})
oldest_queued_age_seconds = _age_seconds(queue_stats.get("oldest_queued_at"))
oldest_running_lease_age_seconds = _age_seconds(
⋮----
pending_outbox_total = 0
pending_outbox_by_kind: Counter[str] = Counter()
oldest_outbox_age_seconds = None
⋮----
events = campaign.get("events") or []
⋮----
snapshot = outbox_snapshot(events, max_items=1)
⋮----
age = _age_seconds(snapshot.get("oldest_pending_at"))
⋮----
oldest_outbox_age_seconds = (
⋮----
metrics = {
⋮----
watchdog = build_worker_watchdog(metrics)
⋮----
watchdog = {
⋮----
@router.get("/api/metrics")
def operational_metrics()
````

## File: backend/app/nuclei_parser.py
````python
class NucleiParserError(RuntimeError)
⋮----
def _max_nuclei_jsonl_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_NUCLEI_JSONL_BYTES", str(10 * 1024 * 1024))
⋮----
limit = int(raw)
⋮----
def parse_nuclei_jsonl(path: str | Path, campaign: Campaign) -> list[Finding]
⋮----
path = Path(path)
⋮----
normalized = []
⋮----
line = raw_line.strip()
⋮----
item = json.loads(line)
⋮----
finding = normalize_nuclei_item(item, campaign)
````

## File: backend/app/observation_graph.py
````python
ObservationKind = Literal[
ActionKind = Literal["inventory", "crawl", "scan", "validate", "report", "stop"]
⋮----
@dataclass(frozen=True)
class Observation
⋮----
id: str
kind: ObservationKind
value: str
source: str
parent_ids: tuple[str, ...] = ()
metadata: dict[str, Any] = field(default_factory=dict)
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
@dataclass(frozen=True)
class PlannedAction
⋮----
kind: ActionKind
target: str | None
reason: str
priority: int
⋮----
class ObservationGraph
⋮----
"""Small deterministic observation graph used by the planner and tests."""
⋮----
def __init__(self) -> None
⋮----
def add(self, observation: Observation) -> None
⋮----
missing = [parent for parent in observation.parent_ids if parent not in self._items]
⋮----
existing = self._items.get(observation.id)
⋮----
@classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> ObservationGraph
⋮----
graph = cls()
pending = [
⋮----
remaining = []
progressed = False
⋮----
progressed = True
⋮----
pending = remaining
⋮----
def values(self) -> list[Observation]
⋮----
def by_kind(self, kind: ObservationKind) -> list[Observation]
⋮----
def load_observation_graph(store: Any, campaign_id: str) -> ObservationGraph
⋮----
"""Load the durable observation graph for a campaign from storage."""
⋮----
def _campaign_finding_id(observation: Observation) -> str
⋮----
"""Map canonical graph finding IDs to campaign IDs while preserving old fixtures."""
prefix = "finding:"
⋮----
class AdaptivePlanner
⋮----
"""Deterministic, bounded decision layer for authorized campaign progression."""
⋮----
def plan(self, campaign: Any, graph: ObservationGraph) -> list[PlannedAction]
⋮----
target = str(campaign.target.primary_url)
host = (urlparse(target).hostname or "").lower()
⋮----
rules = campaign.target.rules
⋮----
limit_violation = planner_limit_violation(graph)
⋮----
observations = graph.values()
assets = graph.by_kind("asset")
endpoints = graph.by_kind("endpoint")
findings = graph.by_kind("finding")
evidence = graph.by_kind("evidence")
⋮----
campaign_findings = list(getattr(campaign, "findings", ()))
⋮----
graph_finding_ids = {_campaign_finding_id(item) for item in findings}
campaign_finding_ids = {str(item.id) for item in campaign_findings}
⋮----
validation_state = analyze_validation_state(graph)
⋮----
unresolved_findings = [
⋮----
confirmed_findings = [
⋮----
report_exists = any(item.metadata.get("artifact_kind") == "report" for item in evidence)
⋮----
scan_completed = any(
````

## File: backend/app/observation_writer.py
````python
def observation_id(prefix: str, value: str) -> str
⋮----
digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
⋮----
observation = Observation(
⋮----
asset_id = record_asset(store, campaign, finding.asset, finding.discovered_by)
parent_id = asset_id
⋮----
endpoint_value = str(finding.endpoint)
⋮----
endpoint_value = str(finding.asset).rstrip("/") + endpoint_value
parent_id = record_endpoint(
⋮----
evidence_observation = Observation(
⋮----
payload = json.loads(content.decode("utf-8"))
⋮----
differential = payload.get("differential")
⋮----
artifact_metadata = {
⋮----
differential_metadata = _differential_artifact_metadata(
````

## File: backend/app/observer_heartbeat.py
````python
@dataclass
class LeaseHeartbeat
⋮----
lease: ObserverLease
owner: str
generation: int
ttl_seconds: int
interval_seconds: float
⋮----
def run(self, stop: Event) -> None
⋮----
"""Run a bounded callback while renewing only the current fenced lease."""
stop = Event()
heartbeat = LeaseHeartbeat(
thread = Thread(target=heartbeat.run, args=(stop,), daemon=True)
````

## File: backend/app/observer_lease.py
````python
class ObserverLease
⋮----
"""Small SQLite lease ensuring one active incident observer per shared DB."""
⋮----
def __init__(self, db_path: str)
⋮----
def _connect(self)
⋮----
db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
⋮----
def _init(self)
⋮----
def acquire(self, owner: str, *, ttl_seconds: int, now: datetime | None = None) -> int | None
⋮----
current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
expires = current + timedelta(seconds=ttl_seconds)
⋮----
row = db.execute(
active_until = (
⋮----
generation = int(row["generation"]) + (0 if row["owner"] == owner else 1)
⋮----
def heartbeat(self, owner: str, generation: int, *, ttl_seconds: int, now: datetime | None = None) -> bool
⋮----
cursor = db.execute(
⋮----
def is_current(self, owner: str, generation: int, *, now: datetime | None = None) -> bool
⋮----
def release(self, owner: str, generation: int | None = None) -> bool
````

## File: backend/app/observer_metrics.py
````python
def observer_health_metrics(snapshot: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]
⋮----
current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
⋮----
def age(value)
⋮----
parsed = datetime.fromisoformat(str(value))
⋮----
parsed = parsed.replace(tzinfo=timezone.utc)
````

## File: backend/app/observer_resilience.py
````python
@dataclass
class ObserverHealth
⋮----
consecutive_failures: int = 0
last_success_at: str | None = None
last_failure_at: str | None = None
leadership_changes: int = 0
last_generation: int | None = None
circuit_open_until: str | None = None
last_cycle_duration_seconds: float | None = None
deadline_exceeded_count: int = 0
leadership_lost_count: int = 0
⋮----
def note_generation(self, generation: int) -> None
⋮----
def circuit_open(self, now: datetime | None = None) -> bool
⋮----
current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
⋮----
def note_cycle_duration(self, seconds: float) -> None
⋮----
def note_deadline_exceeded(self) -> None
⋮----
def note_leadership_lost(self) -> None
⋮----
def success(self, now: datetime | None = None) -> None
⋮----
def snapshot(self) -> dict[str, Any]
````

## File: backend/app/observer_runtime.py
````python
class ObserverRuntime
⋮----
"""Process-local owner of scheduler health with synchronized snapshots."""
⋮----
def __init__(self)
⋮----
@property
    def health(self) -> ObserverHealth
⋮----
def snapshot(self) -> dict
⋮----
_runtime = ObserverRuntime()
⋮----
def observer_runtime() -> ObserverRuntime
````

## File: backend/app/observer_scheduler.py
````python
def scheduler_config() -> dict[str, int]
⋮----
interval = int(os.getenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "30"))
ttl = int(os.getenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "90"))
⋮----
deadline = int(os.getenv("XBOW_INCIDENT_OBSERVER_DEADLINE_SECONDS", "60"))
⋮----
"""Perform one leader-gated observation pass; external scheduler controls timing."""
config = scheduler_config()
health = health or observer_runtime().health
⋮----
generation = lease.acquire(owner, ttl_seconds=config["lease_ttl_seconds"])
⋮----
started = time.monotonic()
⋮----
result = with_lease_heartbeat(
⋮----
elapsed = time.monotonic() - started
````

## File: backend/app/observer_slo.py
````python
def build_observer_slo(metrics: dict[str, Any]) -> dict[str, Any]
⋮----
"""Classify health of the incident-observation control plane itself."""
failures = int(metrics.get("consecutive_failures") or 0)
last_success_age = metrics.get("last_success_age_seconds")
deadline_count = int(metrics.get("deadline_exceeded_count") or 0)
leadership_lost = int(metrics.get("leadership_lost_count") or 0)
circuit_open = bool(metrics.get("circuit_open"))
⋮----
reasons: list[str] = []
state = "healthy"
⋮----
state = "critical"
⋮----
state = "degraded"
````

## File: backend/app/operational_alerts.py
````python
router = APIRouter()
⋮----
def _threshold(name: str, default: int, low: int, high: int) -> int
⋮----
raw = os.getenv(name, str(default)).strip()
⋮----
value = int(raw)
⋮----
def build_operational_alerts(metrics: dict[str, Any]) -> dict[str, Any]
⋮----
failed_limit = _threshold("XBOW_ALERT_FAILED_JOBS", 1, 1, 100000)
queued_limit = _threshold("XBOW_ALERT_QUEUED_JOBS", 20, 1, 100000)
running_limit = _threshold("XBOW_ALERT_RUNNING_JOBS", 20, 1, 100000)
queue_age_limit = _threshold("XBOW_ALERT_QUEUE_AGE_SECONDS", 300, 30, 86400)
running_lease_age_limit = _threshold(
outbox_limit = _threshold("XBOW_ALERT_PENDING_OUTBOX", 20, 1, 100000)
outbox_age_limit = _threshold("XBOW_ALERT_OUTBOX_AGE_SECONDS", 300, 30, 86400)
⋮----
statuses = metrics.get("jobs_by_status") or {}
failed = int(statuses.get("failed") or 0)
queued = int(statuses.get("queued") or 0)
running = int(statuses.get("running") or 0)
queue_age = metrics.get("oldest_queued_age_seconds")
running_lease_age = metrics.get("oldest_running_lease_age_seconds")
pending_outbox = int(metrics.get("pending_outbox_total") or 0)
outbox_age = metrics.get("oldest_outbox_pending_age_seconds")
⋮----
alerts: list[dict[str, Any]] = []
⋮----
@router.get("/api/alerts")
def operational_alerts()
⋮----
metrics = build_operational_metrics(queue(), storage())
⋮----
@router.post("/api/alerts/deliver")
def deliver_operational_alerts()
⋮----
alerts = build_operational_alerts(metrics)
````

## File: backend/app/operational_slo.py
````python
def _threshold(name: str, default: int, minimum: int, maximum: int) -> int
⋮----
raw = os.getenv(name, str(default))
⋮----
value = int(raw)
⋮----
def build_operational_slo(metrics: dict[str, Any]) -> dict[str, Any]
⋮----
"""Classify aggregate service health without inspecting work content."""
warn_queue = _threshold("XBOW_SLO_WARN_QUEUE_AGE_SECONDS", 120, 1, 86400)
critical_queue = _threshold("XBOW_SLO_CRITICAL_QUEUE_AGE_SECONDS", 600, 1, 86400)
warn_failed = _threshold("XBOW_SLO_WARN_FAILED_JOBS", 2, 0, 100000)
critical_failed = _threshold("XBOW_SLO_CRITICAL_FAILED_JOBS", 10, 0, 100000)
warn_outbox = _threshold("XBOW_SLO_WARN_OUTBOX_AGE_SECONDS", 60, 1, 86400)
critical_outbox = _threshold("XBOW_SLO_CRITICAL_OUTBOX_AGE_SECONDS", 300, 1, 86400)
⋮----
queue_age = int(metrics.get("oldest_queued_age_seconds") or 0)
failed = int((metrics.get("jobs_by_status") or {}).get("failed") or 0)
outbox_age = int(metrics.get("oldest_outbox_pending_age_seconds") or 0)
⋮----
signals: list[dict[str, Any]] = []
⋮----
def classify(name: str, value: int, warning: int, critical: int) -> None
⋮----
watchdog = str((metrics.get("worker_watchdog") or {}).get("status") or "ok")
⋮----
state = (
````

## File: backend/app/orchestrator.py
````python
def _stable_id(prefix: str, *parts: str) -> str
⋮----
digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
⋮----
def _graph_fingerprint(graph: ObservationGraph) -> str
⋮----
payload = [
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
⋮----
def _load_graph(store: Storage, campaign_id: str) -> ObservationGraph
⋮----
def _seed_primary_target(store: Storage, campaign: Campaign) -> None
⋮----
target = str(campaign.target.primary_url)
host = (urlparse(target).hostname or "").lower()
⋮----
asset_id = _stable_id("asset", host, "planner-seed")
⋮----
def _minimum_enrichment_score() -> float
⋮----
raw = os.getenv("XBOW_MIN_RECON_ENRICHMENT_SCORE", "0.40")
⋮----
value = float(raw)
⋮----
rules = campaign.target.rules
surface = build_attack_surface(
score = float(surface["summary"]["enrichment_score"])
threshold = _minimum_enrichment_score()
⋮----
def scope_checker(host: str) -> bool
⋮----
decisions = build_red_team_decisions(
consensus = build_decision_consensus(decisions)
risk = build_campaign_risk(
usage = budget_usage(graph, queue, campaign.id, budget)
job_statuses = queue.campaign_job_status_counts(campaign.id)
gate = build_autonomy_gate(
memories = build_learning_memory(graph)
worker_outcomes = summarize_worker_outcomes(campaign.events)
cycle = build_adaptive_cycle(gate, planned_actions, memories, worker_outcomes)
recon_plan = build_recon_plan(
swarm = coordinate_recon_swarm(recon_plan)
coverage = build_evidence_coverage(graph, scope_checker=scope_checker)
coverage_guidance = build_coverage_guidance(coverage)
scanner_adaptation = adapt_scanner_engines(
⋮----
"""Return clusters whose validated representative has strong independent evidence.

    This only suppresses additional automatic validation fan-out. It never marks
    sibling findings as validated, confirmed, or report-ready.
    """
⋮----
quality_by_id = {
observed_validated = {
⋮----
saturated: set[str] = set()
⋮----
quality = quality_by_id.get(finding_id)
⋮----
def _pending_findings(campaign: Campaign, graph: ObservationGraph) -> list
⋮----
observed_validated = observed_independent_finding_ids(graph)
pending = [
priorities = {item.finding_id: item for item in rank_findings(pending, graph)}
hypotheses = {item.finding_id: item for item in build_hypotheses(graph)}
ordered = sorted(
⋮----
# Validate only one representative from each high-confidence duplicate cluster
# per planner cycle. After that representative is independently observed, the
# next campaign advance re-evaluates the graph and may select another member.
⋮----
cluster_by_member = {
selected_clusters: set[str] = set()
saturated_clusters = _validation_saturated_cluster_ids(campaign, graph)
selected: list = []
⋮----
cluster_id = cluster_by_member.get(str(finding.id))
⋮----
fingerprint = _graph_fingerprint(graph)
jobs: list[dict] = []
⋮----
def _scan_engines() -> tuple[str, ...]
⋮----
raw = os.getenv("XBOW_SCAN_ENGINES", "strix")
values = tuple(dict.fromkeys(part.strip().lower() for part in raw.split(",") if part.strip()))
⋮----
unsupported = [value for value in values if value not in {"strix", "nuclei"}]
⋮----
host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
receipt = policy_receipt(campaign, host, "automated_scan")
⋮----
stable_receipt = {key: value for key, value in receipt.items() if key != "timestamp"}
jobs = []
engines = scan_engines if scan_engines is not None else _scan_engines()
⋮----
kind = "strix_scan" if engine == "strix" else "nuclei_scan"
payload = sanitized_scan_payload(
⋮----
pending = _pending_findings(campaign, graph)
⋮----
pending = pending[:validation_limit]
⋮----
def _decision_explanation(intelligence: dict | None) -> dict | None
⋮----
gate = intelligence["gate"].to_dict()
risk = intelligence["risk"].to_dict()
consensus = intelligence["consensus"].to_dict()
cycle = intelligence["cycle"].to_dict()
surface = dict(intelligence["surface_enrichment"])
coverage = dict(intelligence["coverage"])
⋮----
observation_id = _stable_id("decision", action.kind, action.reason, fingerprint)
⋮----
explanation = _decision_explanation(intelligence)
metadata = seal_decision_metadata(
observation = Observation(
⋮----
agent = agent_for_action(action.kind)
⋮----
refreshed_graph = _load_graph(store, campaign.id)
hypotheses = build_hypotheses(refreshed_graph)
⋮----
memory = build_knowledge_snapshot(refreshed_graph)
usage = budget_usage(refreshed_graph, queue, campaign.id, budget)
⋮----
usage = type(usage)(**{**usage.to_dict(), "exhausted": True, "reason": action.reason})
intelligence_payload = None
⋮----
intelligence_payload = {
⋮----
"""Advance one authorized campaign toward its next bounded planner action.

    Inventory/crawl bootstrap is local-only: it records the declared primary target
    as a known asset/endpoint. Network actions are delegated only through existing
    policy-checked queue job kinds and are attributed to a registered agent role.
    Durable queue counts and planner history cap scans, validation fan-out, reports,
    total planner decisions, and wall-clock runtime so autonomous campaigns fail
    closed when any configured budget is exhausted.
    """
planner = AdaptivePlanner()
initial_graph = _load_graph(store, campaign.id)
breaker = circuit_breaker_state(initial_graph)
⋮----
stability = planner_stability_from_graph(initial_graph)
stability_reason = planner_stability_breaker_reason(stability)
⋮----
limits = budget if budget is not None else planner_budget_from_env()
effective_runtime_limit = (
runtime = runtime_status(campaign.created_at, effective_runtime_limit)
⋮----
graph = _load_graph(store, campaign.id)
⋮----
planned_actions = planner.plan(campaign, graph)
action = planned_actions[0]
⋮----
intelligence = _intelligence_context(
cycle = intelligence["cycle"]
⋮----
breaker_blockers = {"failed_jobs", "runtime_exhausted", "budget_blocked", "campaign_risk_blocked"}
⋮----
stop_reason = cycle.reason
⋮----
stop_reason = f"human review required: {cycle.reason}"
stop_action = PlannedAction(
⋮----
recon_jobs = _enqueue_recon_tasks(
⋮----
enrichment = intelligence["surface_enrichment"]
recon_action = PlannedAction(
⋮----
validation_limit = None
scan_engines = None
⋮----
selected = intelligence["scanner_adaptation"].selected_engines
coordination = coordinate_pipeline_action(
scan_engines = selected[:coordination.allocated_items]
⋮----
pending_count = len(_pending_findings(campaign, graph))
⋮----
validation_limit = coordination.allocated_items
⋮----
jobs = _enqueue_action(
⋮----
action = PlannedAction(
⋮----
action = planner.plan(campaign, graph)[0]
````

## File: backend/app/outbox_recovery.py
````python
_TERMINAL = {"failed", "cancelled"}
⋮----
def _digest(value: str) -> str
⋮----
diagnostics: list[dict[str, Any]] = []
⋮----
raw_identity = str(intent["raw_identity"])
dedupe_key = intent.get("dedupe_key")
job_kind = intent.get("job_kind")
item: dict[str, Any] = {
⋮----
job = queue.get_by_dedupe(campaign_id, job_kind, dedupe_key)
⋮----
status = str(job.get("status") or "unknown")
⋮----
intent = diagnostic.get("_intent") or {}
job = diagnostic.get("_job")
⋮----
request = intent.get("request_event") or {}
completion_type = intent.get("completion_type")
⋮----
event: dict[str, Any] = {
kind = intent.get("kind")
````

## File: backend/app/pentagi_adapter.py
````python
_CREATE_FLOW_MUTATION = """
⋮----
_PROVIDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
⋮----
class PentagiPolicyError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiFlowPlan
⋮----
endpoint: str
payload: dict[str, object]
target: str
model_provider: str
dry_run: bool = True
execution_supported: bool = False
⋮----
def _configured_base_url() -> str
⋮----
value = (os.getenv("XBOW_PENTAGI_BASE_URL") or "").strip()
⋮----
def _configured_provider() -> str
⋮----
value = (os.getenv("XBOW_PENTAGI_MODEL_PROVIDER") or "").strip()
⋮----
def _graphql_endpoint(base_url: str) -> str
⋮----
parsed = urlparse(base_url)
hostname = parsed.hostname
username = parsed.username
password = parsed.password
port = parsed.port
⋮----
def _safe_campaign_target(campaign: Campaign) -> str
⋮----
target = str(campaign.target.primary_url)
⋮----
parsed = urlparse(target)
host = (parsed.hostname or "").lower()
⋮----
rules = campaign.target.rules
⋮----
def _flow_input(campaign: Campaign, target: str) -> str
⋮----
allowed = ", ".join(sorted(str(item) for item in rules.allowed_targets))
denied = ", ".join(sorted(str(item) for item in rules.denied_targets)) or "(none)"
⋮----
"""Build a non-executing PentAGI request plan.

    This first adapter stage intentionally cannot submit a PentAGI flow. It creates
    a deterministic, scope-constrained GraphQL request only after the same campaign
    safety invariants used by active scanner workers have been satisfied.
    """
⋮----
target = _safe_campaign_target(campaign)
configured_base = base_url if base_url is not None else _configured_base_url()
endpoint = _graphql_endpoint(configured_base.strip())
⋮----
provider = (
⋮----
payload: dict[str, object] = {
````

## File: backend/app/pentagi_admission.py
````python
class PentagiAdmissionError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiAdmissionDecision
⋮----
allowed: bool
reasons: tuple[str, ...]
campaign_id: str
target: str
max_requests_per_second: float
policy_fingerprint: str
⋮----
def _strict_bool_env(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _bounded_admission_rps() -> float
⋮----
raw = (os.getenv("XBOW_PENTAGI_MAX_ADMISSION_RPS") or "2.0").strip()
⋮----
value = float(raw)
⋮----
def _policy_fingerprint(campaign: Campaign, plan: PentagiFlowPlan) -> str
⋮----
rules = campaign.target.rules
payload = {
canonical = json.dumps(
⋮----
"""Evaluate whether a PentAGI plan may ever reach an execution transport.

    The current adapter intentionally has no enforceable egress/rate-limit transport,
    so admission remains denied even when an operator enables PentAGI. This function
    centralizes that invariant so a future transport cannot accidentally bypass it.
    """
⋮----
reasons: list[str] = []
enabled = _strict_bool_env("XBOW_ENABLE_PENTAGI", False)
active_scans = _strict_bool_env("XBOW_ENABLE_ACTIVE_SCANS", False)
dry_run = _strict_bool_env("DRY_RUN", True)
admission_cap = _bounded_admission_rps()
campaign_rps = float(campaign.target.rules.max_requests_per_second)
⋮----
decision = evaluate_pentagi_admission(campaign, plan)
````

## File: backend/app/pentagi_auth.py
````python
class PentagiAuthError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiAuth
⋮----
token: str = field(repr=False)
⋮----
def headers(self) -> dict[str, str]
⋮----
def _validate_token(value: str | None) -> str
⋮----
token = value.strip()
⋮----
encoded = token.encode("utf-8")
⋮----
def load_pentagi_auth() -> PentagiAuth
⋮----
token = resolve_secret("pentagi_api_token", "XBOW_PENTAGI_API_TOKEN")
````

## File: backend/app/pentagi_control.py
````python
class PentagiControlError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiControlPreview
⋮----
plan: PentagiFlowPlan
decision: PentagiAdmissionDecision
operational_reasons: tuple[str, ...]
⋮----
@property
    def ready(self) -> bool
⋮----
def _strict_bool_env(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def prepare_pentagi_control_preview(campaign: Campaign) -> PentagiControlPreview
⋮----
"""Build the server-configured execution candidate and evaluate all API gates."""
⋮----
preview = build_pentagi_flow_plan(campaign)
decision = evaluate_pentagi_admission(campaign, preview)
⋮----
operational_reasons: list[str] = []
⋮----
def require_pentagi_control_ready(campaign: Campaign) -> PentagiControlPreview
⋮----
preview = prepare_pentagi_control_preview(campaign)
reasons = list(preview.decision.reasons) + list(preview.operational_reasons)
````

## File: backend/app/pentagi_dispatch.py
````python
def _job_payload(permit: PentagiExecutionPermit, plan: PentagiFlowPlan) -> dict
⋮----
"""Create and verify the deterministic permit before any queue mutation."""
⋮----
permit = issue_pentagi_execution_permit(campaign, plan)
⋮----
"""Persist one admitted PentAGI flow request with atomic local deduplication.

    PentAGI createFlow is a mutating remote operation and the upstream API has no
    documented server-side idempotency contract in this integration yet.
    Therefore the queue intentionally uses max_attempts=1: an ambiguous transport
    failure must be reconciled manually instead of risking a duplicate remote flow.
    """
⋮----
permit = permit or prepare_pentagi_execution_permit(campaign, plan)
````

## File: backend/app/pentagi_execution_guard.py
````python
class PentagiExecutionGuardError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiExecutionPermit
⋮----
campaign_id: str
target: str
policy_fingerprint: str
idempotency_key: str
endpoint: str
model_provider: str
⋮----
def _canonical_plan_payload(plan: PentagiFlowPlan) -> bytes
⋮----
payload = {
⋮----
material = b"\x1f".join(
⋮----
"""Issue a deterministic permit only for an unchanged, admitted plan.

    This module deliberately does not perform any network I/O. A future transport
    must require this permit immediately before submission, then persist the
    idempotency key so retries cannot create duplicate PentAGI flows.
    """
⋮----
decision = evaluate_pentagi_admission(campaign, plan)
⋮----
"""Fail closed if policy or request content changed after permit issuance."""
⋮----
expected = issue_pentagi_execution_permit(campaign, plan)
````

## File: backend/app/pentagi_flow_status.py
````python
_ALLOWED_FLOW_STATUSES = {"created", "running", "waiting", "finished", "failed"}
⋮----
@dataclass(frozen=True)
class PentagiFlowStatus
⋮----
flow_id: str
status: str
title: str | None
body: dict[str, Any]
⋮----
def _flow_status_url(graphql_endpoint: str, flow_id: str) -> str
⋮----
flow_id = flow_id.strip()
⋮----
parsed = urlparse(graphql_endpoint)
hostname = parsed.hostname
username = parsed.username
password = parsed.password
port = parsed.port
⋮----
authority = hostname
⋮----
authority = f"[{hostname}]"
⋮----
authority = f"{authority}:{port}"
⋮----
"""Fetch one existing PentAGI flow without mutating remote state."""
⋮----
url = _flow_status_url(graphql_endpoint, flow_id)
⋮----
auth = load_pentagi_auth()
⋮----
headers = auth.headers()
⋮----
request = urllib.request.Request(url, method="GET", headers=headers)
context = ssl.create_default_context()
opener = urllib.request.build_opener(
⋮----
configured_timeout = _timeout_seconds()
⋮----
timeout = configured_timeout
⋮----
requested_timeout = float(timeout_seconds)
⋮----
timeout = min(configured_timeout, requested_timeout)
deadline = time.monotonic() + timeout
⋮----
response = opener.open(request, timeout=timeout)
status_code = int(getattr(response, "status", response.getcode()))
content_type = (response.headers.get("Content-Type") or "").lower()
⋮----
raw = _read_bounded_with_deadline(
⋮----
document = json.loads(raw.decode("utf-8"))
⋮----
remote_id = document.get("id")
remote_status = document.get("status")
title = document.get("title")
````

## File: backend/app/pentagi_status_poller.py
````python
_TERMINAL_STATUSES = {"finished", "failed"}
⋮----
class PentagiStatusPollError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiPollResult
⋮----
flow_id: str
status: str
polls: int
terminal: bool
timed_out: bool
⋮----
def _poll_interval_seconds() -> float
⋮----
raw = (os.getenv("XBOW_PENTAGI_STATUS_POLL_SECONDS") or "10").strip()
⋮----
value = float(raw)
⋮----
def _max_poll_seconds() -> float
⋮----
raw = (os.getenv("XBOW_PENTAGI_STATUS_MAX_SECONDS") or "3600").strip()
⋮----
"""Poll one existing PentAGI flow until a terminal state or bounded timeout."""
⋮----
interval = _poll_interval_seconds()
max_seconds = _max_poll_seconds()
deadline = monotonic_fn() + max_seconds
polls = 0
last: PentagiStatusSnapshot | None = None
⋮----
now = monotonic_fn()
⋮----
remaining_before_refresh = deadline - monotonic_fn()
⋮----
last = refresh_pentagi_flow_status(
⋮----
remaining = deadline - monotonic_fn()
````

## File: backend/app/pentagi_status_tracker.py
````python
class PentagiStatusTrackingError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiStatusSnapshot
⋮----
campaign_id: str
flow_id: str
status: str
artifact: dict
⋮----
"""Refresh one known PentAGI flow from its durable creation receipt."""
⋮----
receipt = json.loads(content.decode("utf-8"))
⋮----
flow_id = receipt.get("flow_id")
endpoint = receipt.get("endpoint")
idempotency_key = receipt.get("idempotency_key")
⋮----
remote: PentagiFlowStatus = fetch_pentagi_flow_status(
snapshot = {
artifact = store.put_artifact(
````

## File: backend/app/pentagi_status_worker_service.py
````python
class PentagiStatusWorkerError(RuntimeError)
⋮----
def _enabled(name: str) -> bool
⋮----
def _require_runtime() -> None
⋮----
def _receipt_id(job: dict) -> str
⋮----
payload = job.get("payload")
⋮----
value = payload.get("receipt_artifact_id")
⋮----
def process_one(queue: QueueBackend, store, worker_id: str) -> bool
⋮----
job = queue.claim_kind(worker_id, "pentagi_status")
⋮----
receipt_id = _receipt_id(job)
⋮----
result: PentagiPollResult = poll_pentagi_flow_until_terminal(
⋮----
finished = queue.finish(
⋮----
def _idle_poll_seconds() -> float
⋮----
raw = (os.getenv("XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS") or "1").strip()
⋮----
value = float(raw)
⋮----
def main() -> None
⋮----
queue = create_queue()
store = create_storage()
worker_id = os.getenv(
idle = _idle_poll_seconds()
⋮----
worked = process_one(queue, store, worker_id)
````

## File: backend/app/pentagi_transport.py
````python
class PentagiTransportError(RuntimeError)
⋮----
class _NoRedirect(urllib.request.HTTPRedirectHandler)
⋮----
def redirect_request(self, req, fp, code, msg, headers, newurl)
⋮----
@dataclass(frozen=True)
class PentagiTransportResponse
⋮----
status: int
body: dict[str, Any]
⋮----
def _timeout_seconds() -> float
⋮----
raw = (os.getenv("XBOW_PENTAGI_TIMEOUT_SECONDS") or "10").strip()
⋮----
value = float(raw)
⋮----
def _max_response_bytes() -> int
⋮----
raw = (os.getenv("XBOW_PENTAGI_MAX_RESPONSE_BYTES") or str(1024 * 1024)).strip()
⋮----
value = int(raw)
⋮----
def _validate_endpoint(endpoint: str) -> None
⋮----
parsed = urlparse(endpoint)
hostname = parsed.hostname
username = parsed.username
password = parsed.password
port = parsed.port
⋮----
def _set_response_timeout(response, timeout: float) -> None
⋮----
candidates = (
⋮----
def _read_bounded_with_deadline(response, *, limit: int, deadline: float) -> bytes
⋮----
chunks: list[bytes] = []
total = 0
⋮----
remaining = deadline - time.monotonic()
⋮----
chunk = response.read(min(65536, limit + 1 - total))
⋮----
"""Submit one already-admitted PentAGI GraphQL request.

    The queue must not automatically retry this mutating create operation until
    the remote API exposes a documented idempotency/reconciliation mechanism.
    """
⋮----
body = json.dumps(
⋮----
auth = load_pentagi_auth()
⋮----
headers = auth.headers()
⋮----
request = urllib.request.Request(
⋮----
context = ssl.create_default_context()
opener = urllib.request.build_opener(
⋮----
timeout = _timeout_seconds()
deadline = time.monotonic() + timeout
⋮----
response = opener.open(request, timeout=timeout)
status = int(getattr(response, "status", response.getcode()))
content_type = (response.headers.get("Content-Type") or "").lower()
⋮----
raw = _read_bounded_with_deadline(
⋮----
document = json.loads(raw.decode("utf-8"))
⋮----
data = document.get("data")
⋮----
create_flow = data.get("createFlow")
⋮----
flow_id = create_flow.get("id")
status_value = create_flow.get("status")
````

## File: backend/app/pentagi_worker_service.py
````python
class PentagiWorkerPolicyError(RuntimeError)
⋮----
@dataclass(frozen=True)
class PentagiWorkerPreflight
⋮----
campaign: Campaign
plan: PentagiFlowPlan
permit: PentagiExecutionPermit
⋮----
def _enabled(name: str) -> bool
⋮----
def pentagi_worker_available() -> bool
⋮----
"""Return whether the reviewed PentAGI transport is explicitly enabled."""
⋮----
def _require_worker_runtime() -> None
⋮----
def _lease_seconds() -> int
⋮----
raw = os.getenv("XBOW_JOB_LEASE_SECONDS", "21600")
⋮----
value = int(raw)
⋮----
@contextmanager
def _maintain_lease(queue: QueueBackend, job_id: str, worker_id: str)
⋮----
"""Renew ownership while the blocking remote submission is in flight."""
⋮----
stop = threading.Event()
lost = threading.Event()
interval = min(20.0, max(5.0, _lease_seconds() / 4.0))
⋮----
def heartbeat_loop() -> None
⋮----
thread = threading.Thread(
⋮----
def _payload_object(job: dict) -> dict
⋮----
payload = job.get("payload")
⋮----
def preflight_pentagi_job(job: dict, campaign: Campaign) -> PentagiWorkerPreflight
⋮----
"""Reconstruct and verify the exact admitted plan without network I/O."""
⋮----
payload = _payload_object(job)
request = payload.get("request")
⋮----
required_strings = {
⋮----
plan = PentagiFlowPlan(
permit = PentagiExecutionPermit(
⋮----
def _load_campaign(store, campaign_id: str) -> Campaign
⋮----
record = store.get_campaign_record(campaign_id)
⋮----
def process_one(queue: QueueBackend, store, worker_id: str) -> bool
⋮----
"""Claim, revalidate, submit once, and finish one PentAGI flow job."""
⋮----
job = queue.claim_kind(worker_id, "pentagi_flow")
⋮----
campaign = _load_campaign(store, job["campaign_id"])
⋮----
current_campaign = _load_campaign(store, job["campaign_id"])
preflight = preflight_pentagi_job(job, current_campaign)
⋮----
response = submit_pentagi_flow(preflight.plan, preflight.permit)
⋮----
create_flow = response.body["data"]["createFlow"]
flow_id = create_flow["id"]
remote_status = create_flow.get("status") or "unknown"
⋮----
receipt = {
receipt_artifact = store.put_artifact(
⋮----
receipt_id = receipt_artifact.get("id")
⋮----
finished = queue.finish(job["id"], worker_id, True)
⋮----
def _poll_seconds() -> float
⋮----
raw = os.getenv("XBOW_PENTAGI_WORKER_POLL_SECONDS", "1")
⋮----
value = float(raw)
⋮----
def main() -> None
⋮----
queue = create_queue()
store = create_storage()
worker_id = os.getenv(
poll = _poll_seconds()
⋮----
worked = process_one(queue, store, worker_id)
````

## File: backend/app/pipeline_swarm.py
````python
@dataclass(frozen=True)
class PipelineCoordination
⋮----
action: str
agent: str
role: str
requested_items: int
allocated_items: int
remaining_inflight_jobs: int
bounded: bool = True
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
limits = budget or PlannerBudget()
agent = agent_for_action(action)
expected_roles = {
⋮----
action_capacity = usage.remaining_scans
batch_capacity = limits.max_scans
⋮----
action_capacity = usage.remaining_validations
batch_capacity = limits.max_validation_batch
⋮----
action_capacity = usage.remaining_reports
batch_capacity = 1
⋮----
allocated = max(
````

## File: backend/app/planner_advisory.py
````python
"""Build a read-only focus context for the deterministic planner.

    This context may explain and order human review attention, but it never
    authorizes execution or changes the planner's allowed action set.
    """
⋮----
ranking = rank_findings_explainable(
selected = ranking[:top_n]
top = selected[0] if selected else None
⋮----
focus = None
rationale = "no findings are available for advisory prioritization"
⋮----
focus = top["finding_id"]
rationale = (
⋮----
focus_items = [
⋮----
def advisory_focus_fingerprint(advisory: dict[str, Any]) -> str
⋮----
payload = {
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
⋮----
before_focus = (previous or {}).get("advisory", {}).get("focus", [])
after_focus = (current or {}).get("advisory", {}).get("focus", [])
before = {str(item["finding_id"]): item for item in before_focus}
after = {str(item["finding_id"]): item for item in after_focus}
⋮----
before_order = [str(item["finding_id"]) for item in before_focus]
after_order = [str(item["finding_id"]) for item in after_focus]
entered = [finding_id for finding_id in after_order if finding_id not in before]
exited = [finding_id for finding_id in before_order if finding_id not in after]
⋮----
rank_changes = []
⋮----
old_rank = int(before[finding_id]["rank"])
new_rank = int(after[finding_id]["rank"])
⋮----
previous_top = before_order[0] if before_order else None
current_top = after_order[0] if after_order else None
top_changed = previous_top != current_top
⋮----
displacement = sum(abs(item["delta"]) for item in rank_changes)
significance_score = min(
significant = significance_score >= 0.45
⋮----
ordered = list(reversed(snapshots))
events: list[dict[str, Any]] = []
⋮----
first = ordered[0]
first_focus = first.get("advisory", {}).get("focus", [])
first_top = first_focus[0]["finding_id"] if first_focus else None
⋮----
unchanged_streak = 0
previous = first
⋮----
delta = diff_advisory_focus_snapshots(previous, current)
⋮----
previous = current
````

## File: backend/app/planner_budget.py
````python
@dataclass(frozen=True)
class PlannerBudget
⋮----
max_actions: int = 50
max_scans: int = 3
max_validations: int = 25
max_validation_batch: int = 10
max_reports: int = 5
max_inflight_jobs: int = 12
max_failed_jobs: int = 5
⋮----
def __post_init__(self) -> None
⋮----
values = (
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int
⋮----
raw = os.getenv(name)
⋮----
value = int(raw)
⋮----
def planner_budget_from_env() -> PlannerBudget
⋮----
budget = PlannerBudget(
⋮----
@dataclass(frozen=True)
class BudgetUsage
⋮----
actions: int
scans: int
validations: int
reports: int
inflight_jobs: int
failed_jobs: int
remaining_actions: int
remaining_scans: int
remaining_validations: int
remaining_reports: int
remaining_inflight_jobs: int
remaining_failed_jobs: int
blocked_actions: dict[str, str]
exhausted: bool
reason: str | None = None
⋮----
blocked: dict[str, str] = {}
⋮----
limits = budget or PlannerBudget()
history = decision_history(graph)
counts = queue.campaign_job_counts(campaign_id)
status_counts = queue.campaign_job_status_counts(campaign_id)
actions = sum(1 for item in history if item.get("action") != "stop")
scans = counts["strix_scan"] + counts["nuclei_scan"]
validations = counts["independent_validation"]
reports = counts["report"]
inflight_jobs = status_counts["queued"] + status_counts["running"]
failed_jobs = status_counts["failed"]
blocked_actions = _blocked_actions(
exhausted = actions >= limits.max_actions
⋮----
usage = budget_usage(graph, queue, campaign_id, limits)
reason = usage.blocked_actions.get(action.kind)
⋮----
def validation_batch_limit(usage: BudgetUsage, budget: PlannerBudget | None = None) -> int
````

## File: backend/app/planner_limits.py
````python
class PlannerLimitConfigError(ValueError)
⋮----
@dataclass(frozen=True)
class PlannerLimits
⋮----
max_observations: int = 5000
max_endpoints: int = 1500
max_findings: int = 250
⋮----
def _strict_positive_int(name: str, default: int, *, minimum: int, maximum: int) -> int
⋮----
raw = os.getenv(name)
⋮----
value = int(raw)
⋮----
def planner_limits() -> PlannerLimits
⋮----
def planner_limit_violation(graph: Any) -> str | None
⋮----
"""Return a non-secret fail-closed reason when autonomous planner bounds are exceeded."""
limits = planner_limits()
observations = graph.values()
endpoints = graph.by_kind("endpoint")
findings = graph.by_kind("finding")
````

## File: backend/app/planner_lock.py
````python
def _planner_lock_seconds() -> int
⋮----
raw = os.getenv("XBOW_PLANNER_LOCK_SECONDS", "30")
⋮----
value = int(raw)
⋮----
@contextmanager
def campaign_planner_lock(queue, campaign_id: str)
⋮----
"""Best-effort single-planner lease for distributed Redis deployments.

    SQLite deployments already serialize queue mutations locally and use durable
    dedupe/CAS guards, so they do not need an extra cross-process Redis lease.
    """
client = getattr(queue, "redis", None)
prefix = getattr(queue, "prefix", "")
⋮----
digest = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()
key = f"{prefix}:planner-lock:{digest}"
token = uuid4().hex
acquired = bool(client.set(key, token, nx=True, ex=_planner_lock_seconds()))
⋮----
script = """
⋮----
# Lease expiry is bounded; never delete a successor's lock.
````

## File: backend/app/policy_integrity.py
````python
_INTEGRITY_FIELDS = {"receipt_hash", "signature", "signature_alg", "integrity_mode"}
⋮----
def canonical_policy_receipt(receipt: dict[str, Any]) -> bytes
⋮----
payload = {
⋮----
def seal_policy_receipt(receipt: dict[str, Any]) -> dict[str, Any]
⋮----
sealed = dict(receipt)
canonical = canonical_policy_receipt(sealed)
⋮----
secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
⋮----
def verify_policy_receipt(receipt: dict[str, Any]) -> dict[str, Any]
⋮----
expected_hash = str(receipt.get("receipt_hash") or "")
⋮----
canonical = canonical_policy_receipt(receipt)
actual_hash = hashlib.sha256(canonical).hexdigest()
hash_valid = hmac.compare_digest(expected_hash, actual_hash)
⋮----
signature = receipt.get("signature")
algorithm = receipt.get("signature_alg")
⋮----
expected_signature = hmac.new(
signature_valid = hmac.compare_digest(str(signature), expected_signature)
````

## File: backend/app/postgres_storage.py
````python
class _PostgresCompatConnection
⋮----
def __init__(self, connection)
⋮----
@staticmethod
    def _sql(statement: str) -> str
⋮----
normalized = statement.strip()
⋮----
def execute(self, statement: str, params=())
⋮----
class PostgresStorage(Storage)
⋮----
"""PostgreSQL-backed campaign metadata with the same artifact semantics as Storage."""
⋮----
storage_name = "postgresql"
⋮----
parsed = urlparse(self.database_url)
⋮----
@contextmanager
    def connect(self)
⋮----
connection = psycopg.connect(
⋮----
def _init(self) -> None
````

## File: backend/app/queue_backend.py
````python
@runtime_checkable
class QueueBackend(Protocol)
⋮----
def health(self) -> dict: ...
def enqueue(self, campaign_id: str, kind: str, payload: dict, max_attempts: int = 2, *, dedupe_key: str | None = None) -> dict: ...
def get(self, job_id: str) -> dict | None: ...
def get_by_dedupe(self, campaign_id: str, kind: str, dedupe_key: str) -> dict | None: ...
def stats(self) -> dict: ...
def campaign_job_counts(self, campaign_id: str) -> dict[str, int]: ...
def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]: ...
def cancel_queued(self, campaign_id: str) -> int: ...
def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict | None: ...
def recover_expired_leases(self) -> int: ...
def claim(self, worker_id: str) -> dict | None: ...
def claim_allowed(self, worker_id: str, kinds: tuple[str, ...] | list[str]) -> dict | None: ...
def claim_kind(self, worker_id: str, kind: str) -> dict | None: ...
def heartbeat(self, job_id: str, worker_id: str) -> bool: ...
def finish(self, job_id: str, worker_id: str, success: bool, error: str | None = None) -> dict | None: ...
⋮----
def queue_backend_name() -> str
⋮----
value = os.getenv("XBOW_QUEUE_BACKEND", "sqlite").strip().lower()
aliases = {
value = aliases.get(value, value)
⋮----
def create_queue() -> QueueBackend
⋮----
backend = queue_backend_name()
````

## File: backend/app/readiness.py
````python
# Backward-compatible test seam; runtime still resolves through create_storage().
def Storage()
⋮----
# Backward-compatible test seam; runtime resolves through create_queue().
def JobQueue()
⋮----
def _artifact_store_ready(root: Path) -> dict[str, Any]
⋮----
"""Verify that the configured artifact store is writable by this process."""
⋮----
def readiness() -> dict[str, Any]
⋮----
"""Return dependency readiness without exposing queue payloads or secrets."""
⋮----
queue = JobQueue().health()
except Exception as exc:  # pragma: no cover - defensive boundary for container probes
queue = {"ok": False, "error": exc.__class__.__name__}
⋮----
store = Storage()
metadata = store.health()
⋮----
store = None
metadata = {"ok": False, "error": exc.__class__.__name__}
⋮----
artifacts = {"ok": False, "error": "StorageUnavailable"}
⋮----
artifacts = _artifact_store_ready(store.artifact_root)
⋮----
operational = (
watchdog = operational.get("worker_watchdog") or {"status": "error"}
⋮----
watchdog = {"status": "error"}
⋮----
def main() -> None
⋮----
result = readiness()
````

## File: backend/app/recon_swarm.py
````python
ReconTaskKind = Literal[
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class ReconCapability
⋮----
agent: str
task_kind: ReconTaskKind
observation_kinds: tuple[str, ...]
network_access: bool
same_origin_only: bool
read_only: bool
allowed_methods: tuple[str, ...]
max_targets_per_batch: int
max_requests_per_target: int
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
@dataclass(frozen=True)
class ReconTask
⋮----
kind: ReconTaskKind
⋮----
target: str
priority: int
reason: str
max_requests: int
allowed_methods: tuple[str, ...] = ("GET", "HEAD")
same_origin_only: bool = True
read_only: bool = True
⋮----
_CAPABILITIES = (
⋮----
def recon_capabilities() -> tuple[ReconCapability, ...]
⋮----
def _asset_host(value: str) -> str
⋮----
parsed = urlsplit(value if "://" in value else f"//{value}")
⋮----
def _safe_target(value: str) -> tuple[str, str]
⋮----
parsed = urlsplit(value)
scheme = parsed.scheme.lower()
host = (parsed.hostname or "").lower().rstrip(".")
⋮----
port = parsed.port
⋮----
netloc = f"{host}:{port}"
⋮----
netloc = host
⋮----
"""Build a bounded passive/low-impact recon plan without executing requests."""
⋮----
observed_assets = {
⋮----
endpoints = graph.by_kind("endpoint")
forms = graph.by_kind("form")
technologies = graph.by_kind("technology")
wafs = graph.by_kind("waf")
tasks: list[ReconTask] = []
⋮----
@router.get("/api/recon-swarm/capabilities")
def recon_swarm_capabilities()
⋮----
@router.get("/api/campaigns/{campaign_id}/recon-plan")
def campaign_recon_plan(campaign_id: str, limit: int = 10)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
tasks = build_recon_plan(
````

## File: backend/app/recon_worker.py
````python
class ReconPolicyError(RuntimeError)
⋮----
class _NoRedirect(HTTPRedirectHandler)
⋮----
def redirect_request(self, req, fp, code, msg, headers, newurl)
⋮----
@dataclass(frozen=True)
class ReconResult
⋮----
status: str
target: str
endpoints: tuple[str, ...] = ()
forms: tuple[dict, ...] = ()
technologies: tuple[str, ...] = ()
waf: tuple[str, ...] = ()
http_status: int | None = None
error: str | None = None
requests_made: int = 0
bytes_read: int = 0
max_depth_reached: int = 0
skipped_out_of_scope: int = 0
skipped_cross_origin: int = 0
wall_time_seconds: float = 0.0
stopped_by_time_budget: bool = False
request_budget: int = 0
frontier_remaining: int = 0
stopped_by_request_budget: bool = False
deferred_by_request_budget: int = 0
coverage_complete: bool = False
⋮----
_MAX_DISCOVERED_LINKS = 500
_MAX_DISCOVERED_FORMS = 100
_MAX_FORM_INPUT_NAMES = 100
⋮----
class _SurfaceParser(HTMLParser)
⋮----
def __init__(self, base_url: str) -> None
⋮----
def handle_starttag(self, tag: str, attrs)
⋮----
values = {str(k).lower(): str(v or "") for k, v in attrs}
tag = tag.lower()
candidate = ""
⋮----
candidate = values.get("href", "")
⋮----
candidate = values.get("src", "")
⋮----
action = urljoin(self.base_url, values.get("action") or self.base_url)
⋮----
name = values.get("name", "").strip()
⋮----
def handle_endtag(self, tag: str)
⋮----
def _timeout_seconds() -> float
⋮----
raw = os.getenv("XBOW_RECON_TIMEOUT_SECONDS", "10")
⋮----
value = float(raw)
⋮----
def _max_bytes() -> int
⋮----
raw = os.getenv("XBOW_RECON_MAX_BYTES", "262144")
⋮----
value = int(raw)
⋮----
def _max_crawl_requests() -> int
⋮----
raw = os.getenv("XBOW_RECON_MAX_REQUESTS", "40")
⋮----
def _max_crawl_depth() -> int
⋮----
raw = os.getenv("XBOW_RECON_MAX_DEPTH", "2")
⋮----
def _max_wall_seconds() -> float
⋮----
raw = os.getenv("XBOW_RECON_MAX_WALL_SECONDS", "120")
⋮----
def _recon_rps(campaign) -> float
⋮----
campaign_rps = float(campaign.target.rules.max_requests_per_second)
⋮----
raw = os.getenv("XBOW_RECON_MAX_RPS", "2.0")
⋮----
local_cap = float(raw)
⋮----
def _enabled() -> bool
⋮----
raw = os.getenv("XBOW_ENABLE_RECON", "0").strip().lower()
⋮----
def _safe_url(campaign, candidate: str) -> str
⋮----
parsed = urlparse(candidate)
⋮----
host = parsed.hostname.lower().rstrip(".")
rules = campaign.target.rules
⋮----
def _same_origin(base: str, candidate: str) -> bool
⋮----
def _fetch_page(opener, target: str, max_bytes: int, timeout_seconds: float)
⋮----
request = Request(
⋮----
def execute_recon_task(campaign, payload: dict) -> ReconResult
⋮----
kind = str(payload.get("kind") or "")
⋮----
target = _safe_url(campaign, str(payload.get("target") or ""))
⋮----
requested = payload.get("max_requests", 1)
⋮----
requested = int(requested)
⋮----
request_budget = min(requested, _max_crawl_requests())
max_depth = _max_crawl_depth()
min_interval = 1.0 / _recon_rps(campaign)
max_bytes = _max_bytes()
request_timeout = _timeout_seconds()
started_at = time.monotonic()
deadline = started_at + _max_wall_seconds()
opener = build_opener(_NoRedirect())
⋮----
pending: list[tuple[str, int]] = [(target, 0)]
visited: set[str] = set()
endpoints: set[str] = set()
forms: list[dict] = []
technologies: set[str] = set()
waf: set[str] = set()
first_status: int | None = None
first_error: str | None = None
last_request_at: float | None = None
bytes_read = 0
max_depth_reached = 0
skipped_out_of_scope = 0
skipped_cross_origin = 0
stopped_by_time_budget = False
deferred_by_request_budget = 0
⋮----
stopped_by_time_budget = True
⋮----
current = _safe_url(campaign, current)
⋮----
delay = min_interval - (time.monotonic() - last_request_at)
⋮----
remaining = deadline - time.monotonic()
⋮----
last_request_at = time.monotonic()
⋮----
max_depth_reached = max(max_depth_reached, depth)
⋮----
first_status = status
⋮----
first_error = first_error or error
⋮----
content_type = (headers.get("Content-Type") or "").lower() if headers else ""
text = body.decode("utf-8", errors="replace") if "html" in content_type else ""
parser = _SurfaceParser(current)
⋮----
safe = _safe_url(campaign, candidate)
⋮----
action = _safe_url(campaign, form["action"])
⋮----
normalized = {
⋮----
value = headers.get(header)
⋮----
wall_time_seconds = max(0.0, time.monotonic() - started_at)
frontier_remaining = len(pending)
stopped_by_request_budget = bool(
coverage_complete = bool(
````

## File: backend/app/red_team_coverage.py
````python
router = APIRouter()
⋮----
@dataclass(frozen=True)
class CoverageDomain
⋮----
name: str
observed: int
reviewed: int
validated: int
gaps: int
score: float
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def _ratio(numerator: int, denominator: int) -> float
⋮----
def _reviewed_parent_ids(graph: ObservationGraph, review_types: set[str]) -> set[str]
⋮----
reviewed: set[str] = set()
⋮----
"""Summarize bounded, evidence-backed and optionally scope-aware coverage."""
surface = build_attack_surface(graph, scope_checker=scope_checker)
hypotheses = build_hypotheses(graph, limit=100, scope_checker=scope_checker)
chains = build_evidence_chains(graph)
validation = analyze_validation_state(graph)
⋮----
valid_endpoint_ids = {
valid_form_ids = {
technology_ids = {
waf_ids = {
endpoints = len(valid_endpoint_ids)
forms = len(valid_form_ids)
technologies = len(technology_ids)
wafs = len(waf_ids)
⋮----
in_scope_finding_ids = {
⋮----
finding_ids = set(validation.finding_ids)
⋮----
finding_ids = set(validation.observed_independent_finding_ids) | in_scope_finding_ids
findings = len(finding_ids)
⋮----
input_reviews = sum(item.kind == "input_surface_review" for item in hypotheses)
authorization_reviews = sum(item.kind == "authorization_surface_review" for item in hypotheses)
form_reviews = sum(item.kind == "form_surface_review" for item in hypotheses)
technology_reviews = sum(item.kind == "technology_surface_review" for item in hypotheses)
protection_reviews = sum(item.kind == "protection_surface_review" for item in hypotheses)
validation_gaps = sum(item.kind == "validation_gap" for item in hypotheses)
complete_chain_ids = {item.finding_id for item in chains if item.complete}
complete_chains = len(complete_chain_ids & finding_ids)
⋮----
endpoint_reviewed_ids = _reviewed_parent_ids(
form_reviewed_ids = _reviewed_parent_ids(graph, {"form_surface_review"}) & valid_form_ids
technology_reviewed_ids = _reviewed_parent_ids(
waf_reviewed_ids = _reviewed_parent_ids(graph, {"protection_surface_review"}) & waf_ids
validated_finding_ids = set(validation.observed_independent_finding_ids) & finding_ids
attempted_finding_ids = set(validation.attempted_finding_ids) & finding_ids
⋮----
domains = (
⋮----
weighted_denominator = sum(max(1, item.observed) for item in domains)
weighted_score = round(
⋮----
gaps = []
⋮----
@router.get("/api/campaigns/{campaign_id}/red-team-coverage")
def campaign_red_team_coverage(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
````

## File: backend/app/red_team_decision.py
````python
DecisionKind = Literal[
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class RedTeamDecision
⋮----
kind: DecisionKind
priority: float
reason: str
finding_ids: tuple[str, ...] = ()
evidence_ids: tuple[str, ...] = ()
blocked_from_execution: bool = True
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Rank safe red-team work from existing state without executing target actions."""
⋮----
surface = build_attack_surface(graph, scope_checker=scope_checker)
coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
triage = build_finding_triage(findings, graph)
readiness = build_finding_readiness(
readiness_by_id = {item.finding_id: item for item in readiness}
cluster_consensus = build_cluster_consensus(
cluster_status_by_member: dict[str, str] = {}
blocked_cluster_members: set[str] = set()
⋮----
chains = build_evidence_chains(graph)
hypotheses = build_hypotheses(graph, limit=100, scope_checker=scope_checker)
differential_signals = build_differential_signals(graph)
⋮----
def prioritize_finding_ids(finding_ids: tuple[str, ...]) -> tuple[str, ...]
⋮----
decisions: list[RedTeamDecision] = []
⋮----
integrity_count = (
⋮----
contradiction_ids = tuple(
⋮----
validation_ids = prioritize_finding_ids(
⋮----
incomplete = [item for item in chains if not item.complete]
⋮----
incomplete_ids = prioritize_finding_ids(
⋮----
surface_hypotheses = [
⋮----
report_ids = prioritize_finding_ids(
⋮----
coverage_penalty = max(0.0, 1.0 - float(coverage["score"]))
adjusted = []
⋮----
priority = min(1.0, round(item.priority + coverage_penalty * 0.05, 4))
⋮----
@router.get("/api/campaigns/{campaign_id}/red-team-decisions")
def campaign_red_team_decisions(campaign_id: str, limit: int = 10)
⋮----
campaign = assert_campaign_exists(campaign_id)
store = storage()
graph = load_observation_graph(store, campaign.id)
snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
rules = campaign.target.rules
⋮----
def scope_checker(host: str) -> bool
⋮----
decisions = build_red_team_decisions(
````

## File: backend/app/redis_jobqueue.py
````python
_ALLOWED_KINDS = {"strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status"}
_STATUSES = ("queued", "running", "completed", "failed", "cancelled")
_DEDICATED_KINDS = {"pentagi_flow", "pentagi_status"}
⋮----
def _uses_generic_queue(kind: str) -> bool
⋮----
class RedisJobQueue
⋮----
"""Redis-backed durable queue with ownership, leases, retries and deduplication."""
⋮----
def __init__(self, url: str | None = None)
⋮----
@property
    def _queued(self) -> str
⋮----
@property
    def _running(self) -> str
⋮----
@property
    def _all(self) -> str
⋮----
def _queued_kind(self, kind: str) -> str
⋮----
digest = hashlib.sha256(kind.encode("utf-8")).hexdigest()[:24]
⋮----
def _job_key(self, job_id: str) -> str
⋮----
def _campaign_key(self, campaign_id: str) -> str
⋮----
digest = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()
⋮----
def _dedupe_key(self, campaign_id: str, kind: str) -> str
⋮----
digest = hashlib.sha256(f"{campaign_id}\0{kind}".encode("utf-8")).hexdigest()
⋮----
@staticmethod
    def _decode(row: dict[str, str] | None) -> dict[str, Any] | None
⋮----
result: dict[str, Any] = dict(row)
⋮----
def health(self) -> dict[str, Any]
⋮----
pong = bool(self.redis.ping())
⋮----
campaign_id = _bounded_identifier(campaign_id, "campaign_id")
⋮----
dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")
⋮----
encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
⋮----
job_id = str(uuid4())
now = utcnow()
score = time.time()
row = {
⋮----
created = self.get(job_id)
⋮----
dedupe_hash = self._dedupe_key(campaign_id, kind)
⋮----
existing_id = pipe.hget(dedupe_hash, dedupe_key)
⋮----
existing = self.get(existing_id)
⋮----
existing_payload = json.dumps(
⋮----
def get(self, job_id: str) -> dict[str, Any] | None
⋮----
job_id = _bounded_identifier(job_id, "job_id")
⋮----
kind = _bounded_identifier(kind, "kind")
⋮----
job_id = self.redis.hget(self._dedupe_key(campaign_id, kind), dedupe_key)
⋮----
job = self.get(job_id)
⋮----
def stats(self) -> dict[str, Any]
⋮----
ids = list(self.redis.smembers(self._all))
counts = {status: 0 for status in _STATUSES}
⋮----
statuses = pipe.execute()
⋮----
oldest_at = None
oldest_ids = self.redis.zrange(self._queued, 0, 0)
⋮----
oldest_at = self.redis.hget(self._job_key(oldest_ids[0]), "created_at")
⋮----
oldest_running_at = None
oldest_running_ids = self.redis.zrange(self._running, 0, 0)
⋮----
oldest_running_at = self.redis.hget(
⋮----
def _campaign_members(self, campaign_id: str) -> list[str]
⋮----
def campaign_job_counts(self, campaign_id: str) -> dict[str, int]
⋮----
members = self._campaign_members(campaign_id)
counts = {kind: 0 for kind in _ALLOWED_KINDS}
⋮----
kinds = pipe.execute()
⋮----
def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]
⋮----
def cancel_queued(self, campaign_id: str) -> int
⋮----
count = 0
⋮----
key = self._job_key(job_id)
⋮----
row = pipe.hgetall(key)
⋮----
def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict[str, Any] | None
⋮----
worker_id = _bounded_identifier(worker_id, "worker_id")
reason = reason.strip()
⋮----
reason = reason[-4000:]
⋮----
def recover_expired_leases(self) -> int
⋮----
lease_seconds = _job_lease_seconds()
cutoff = time.time() - lease_seconds
stale_ids = list(self.redis.zrangebyscore(self._running, "-inf", cutoff))
recovered = 0
⋮----
score = pipe.zscore(self._running, job_id)
⋮----
exhausted = int(row["attempts"]) >= int(row["max_attempts"])
status = "failed" if exhausted else "queued"
⋮----
def claim(self, worker_id: str) -> dict[str, Any] | None
⋮----
ids = pipe.zrange(self._queued, 0, 0)
⋮----
job_id = ids[0]
⋮----
def claim_allowed(self, worker_id: str, kinds: tuple[str, ...] | list[str]) -> dict[str, Any] | None
⋮----
"""Claim the oldest queued job across an explicit set of kinds."""
⋮----
normalized = tuple(dict.fromkeys(_bounded_identifier(kind, "kind") for kind in kinds))
⋮----
candidates: list[tuple[float, str, str]] = []
⋮----
rows = self.redis.zrange(
⋮----
claimed = self.claim_kind(worker_id, chosen_kind)
⋮----
def claim_kind(self, worker_id: str, kind: str) -> dict[str, Any] | None
⋮----
"""Atomically claim only one explicitly requested job kind."""
⋮----
queued_kind = self._queued_kind(kind)
⋮----
def heartbeat(self, job_id: str, worker_id: str) -> bool
⋮----
attempts = int(row["attempts"])
max_attempts = int(row["max_attempts"])
status = "completed" if success else ("queued" if attempts < max_attempts else "failed")
````

## File: backend/app/report_approval.py
````python
@dataclass(frozen=True)
class ReportApprovalStatus
⋮----
artifact_id: str
artifact_sha256: str
approved: bool
stale: bool
reviewer: str | None
approved_at: str | None
basis_digest: str
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def _finding_payload(finding: Any) -> dict[str, Any]
⋮----
def report_basis_digest(campaign: Any, artifact: dict[str, Any]) -> str
⋮----
"""Bind approval to the exact report artifact and submission-relevant campaign state."""
confirmed = [
⋮----
rules = campaign.target.rules
payload = {
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
⋮----
def approval_event(campaign: Any, artifact: dict[str, Any], reviewer: str, at: str) -> dict[str, Any]
⋮----
reviewer = reviewer.strip()
⋮----
"""Create approval only after Storage has verified the exact report bytes.

    ``read_artifact`` is intentionally used instead of trusting artifact metadata:
    it verifies the file exists and that its size and SHA-256 still match the
    durable database record before approval is recorded.
    """
⋮----
def revocation_event(artifact_id: str, reviewer: str, at: str) -> dict[str, Any]
⋮----
def approval_status(campaign: Any, artifact: dict[str, Any]) -> ReportApprovalStatus
⋮----
current_digest = report_basis_digest(campaign, artifact)
relevant = [
⋮----
latest = relevant[-1]
⋮----
stale = (
⋮----
def approval_status_from_storage(campaign: Any, store: Any, artifact_id: str) -> ReportApprovalStatus
⋮----
"""Return approval status only for report bytes that still pass integrity checks."""
````

## File: backend/app/report_readiness.py
````python
router = APIRouter()
⋮----
_CWE_RE = re.compile(r"^CWE-[1-9][0-9]{0,5}$")
⋮----
@dataclass(frozen=True)
class ReportReadiness
⋮----
finding_id: str
score: float
ready_for_human_review: bool
confirmed: bool
independent_validation_observed: bool
evidence_backed_independent_validation: bool
consensus_level: str
evidence_chain_complete: bool
duplicate_candidate: bool
blockers: tuple[str, ...]
submission_ready: bool
submission_completeness_score: float
evidence_quality_grade: str
metadata_blockers: tuple[str, ...]
metadata_checks: dict[str, bool]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Score report review readiness using existing evidence only.

    This layer is read-only and advisory. It cannot approve or submit reports.
    """
validation = analyze_validation_state(graph)
chains = {item.finding_id: item for item in build_evidence_chains(graph)}
quality_by_id = {
consensus_by_id = {
duplicate_ids = {
⋮----
readiness: list[ReportReadiness] = []
⋮----
finding_id = str(finding.id)
graph_id = f"finding:{finding_id}"
confirmed = str(finding.status) == "confirmed"
independent = graph_id in validation.observed_independent_finding_ids
evidence_backed = (
consensus = consensus_by_id.get(finding_id)
consensus_level = str(
chain = chains.get(graph_id)
chain_complete = bool(chain and chain.complete)
duplicate = finding_id in duplicate_ids
⋮----
blockers: list[str] = []
⋮----
quality = quality_by_id.get(finding_id)
evidence_grade = str(quality.grade if quality else "low")
cwe = str(getattr(finding, "cwe", "") or "").strip().upper()
cvss = getattr(finding, "cvss", None)
metadata_checks = {
metadata_blockers = tuple(
completeness = round(
⋮----
score = round(
⋮----
@router.get("/api/campaigns/{campaign_id}/report-readiness")
def campaign_report_readiness(campaign_id: str)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
readiness = build_report_readiness(campaign.findings, graph)
````

## File: backend/app/report.py
````python
ReportPlatform = Literal["generic", "hackerone", "bugcrowd"]
⋮----
"""Render a human-review draft from independently confirmed findings only."""
confirmed = [f for f in campaign.findings if f.status == "confirmed"]
platform_name = {"generic": "Security program", "hackerone": "HackerOne", "bugcrowd": "Bugcrowd"}[platform]
severity_counts = {level: sum(1 for f in confirmed if f.severity == level) for level in ("critical", "high", "medium", "low", "info")}
quality_by_id = evidence_quality or {}
high_quality = sum(
⋮----
lines = [
⋮----
quality = quality_by_id.get(str(finding.id)) if evidence_quality is not None else None
quality_grade = str((quality or {}).get("grade") or "unknown")
quality_score = float((quality or {}).get("score") or 0.0)
submission_ready = quality_grade == "high" if evidence_quality is not None else None
````

## File: backend/app/review_queue.py
````python
ReviewKind = Literal[
⋮----
router = APIRouter()
⋮----
@dataclass(frozen=True)
class ReviewTask
⋮----
kind: ReviewKind
target: str
priority: float
reason: str
evidence_ids: tuple[str, ...]
parameter_names: tuple[str, ...] = ()
score_components: dict[str, float] | None = None
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
"""Build a deterministic, bounded and optionally scope-aware review queue."""
⋮----
confidence = {
chains = {item.finding_id: item for item in build_evidence_chains(graph)}
tasks: list[ReviewTask] = []
⋮----
graph_finding_id = hypothesis.evidence_ids[0]
chain = chains.get(graph_finding_id)
chain_penalty = 0.0 if chain and chain.complete else 0.08
current_confidence = confidence.get(graph_finding_id, 0.35)
temporal = (stability or {}).get(graph_finding_id.removeprefix("finding:"), {})
temporal_state = temporal.get("stability")
temporal_bonus = 0.0
temporal_reason = ""
⋮----
temporal_bonus = 0.10
temporal_reason = "; temporal evidence is contradictory"
⋮----
temporal_bonus = 0.04
temporal_reason = "; hypothesis is still evolving"
finding_id = graph_finding_id.removeprefix("finding:")
severity = (severities or {}).get(finding_id, "info")
severity_bonus = review_severity_bonus(severity)
base_score = 0.75
confidence_gap = round((1.0 - current_confidence) * 0.17, 4)
components = {
raw_priority = round(sum(components.values()), 4)
priority = min(1.0, raw_priority)
⋮----
deduped: dict[tuple[str, str], ReviewTask] = {}
⋮----
key = (task.kind, task.target)
previous = deduped.get(key)
⋮----
@router.get("/api/campaigns/{campaign_id}/review-queue")
def campaign_review_queue(campaign_id: str, limit: int = 25)
⋮----
campaign = assert_campaign_exists(campaign_id)
graph = load_observation_graph(storage(), campaign.id)
rules = campaign.target.rules
snapshots = storage().list_hypothesis_snapshots(campaign.id, limit=50)
stability = {
severities = {str(item.id): str(item.severity) for item in campaign.findings}
tasks = build_review_queue(
````

## File: backend/app/rolling_telemetry.py
````python
ALLOWED_WINDOWS = (300, 3600)
MAX_EVENTS = 10000
⋮----
def _timestamp(value: Any) -> datetime | None
⋮----
parsed = datetime.fromisoformat(str(value))
⋮----
parsed = parsed.replace(tzinfo=timezone.utc)
⋮----
def _percentile(values: list[int], percentile: float) -> int | None
⋮----
ordered = sorted(values)
index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
⋮----
"""Build bounded rolling aggregates from redacted worker outcome events."""
current = now or datetime.now(timezone.utc)
bounded = events[-MAX_EVENTS:]
result: dict[str, Any] = {}
⋮----
cutoff = current - timedelta(seconds=seconds)
selected = []
⋮----
at = _timestamp(event.get("at"))
⋮----
statuses = Counter(str(item.get("status") or "unknown") for item in selected)
durations = [
completed = sum(statuses.values())
failed = int(statuses.get("failed") or 0)
````

## File: backend/app/runtime_capabilities.py
````python
class CapabilityConfigError(ValueError)
⋮----
def _strict_bool(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def pentagi_runtime_capability() -> dict[str, Any]
⋮----
"""Return a redacted, fail-closed summary of PentAGI runtime capability.

    Worker/transport switches are necessary runtime gates, but the current adapter
    still marks plans as non-executable because downstream scope/rate enforcement
    for remote PentAGI activity is not yet provable locally.
    """
⋮----
integration_enabled = _strict_bool("XBOW_ENABLE_PENTAGI", False)
active_scans_enabled = _strict_bool("XBOW_ENABLE_ACTIVE_SCANS", False)
dry_run = _strict_bool("DRY_RUN", True)
worker_enabled = _strict_bool("XBOW_ENABLE_PENTAGI_WORKER", False)
transport_enabled = _strict_bool("XBOW_ENABLE_PENTAGI_TRANSPORT", False)
status_worker_enabled = _strict_bool(
⋮----
execution_transport_enforceable = False
execution_reasons: list[str] = []
⋮----
mode = "disabled" if not integration_enabled else "preview_only"
⋮----
def safe_pentagi_runtime_capability() -> dict[str, Any]
⋮----
"""Return a fail-closed public capability document on configuration errors."""
⋮----
def scanner_runtime_capability() -> dict[str, Any]
⋮----
scanner_worker_enabled = _strict_bool("XBOW_ENABLE_SCANNER_WORKER", False)
nuclei_enabled = _strict_bool("XBOW_ENABLE_NUCLEI", False)
⋮----
profile = (os.getenv("XBOW_SCANNER_SANDBOX_PROFILE") or "").strip().lower()
engines = tuple(
supported_engines = {"nuclei", "strix"}
unsupported_engines = [item for item in engines if item not in supported_engines]
nuclei_allowlisted = "nuclei" in engines
nuclei_version_configured = bool(
nuclei_execution_intent = bool(
⋮----
reasons: list[str] = []
⋮----
def safe_scanner_runtime_capability() -> dict[str, Any]
````

## File: backend/app/scanner_adaptation.py
````python
_ALLOWED_ENGINES = {"strix", "nuclei"}
⋮----
@dataclass(frozen=True)
class ScannerAdaptation
⋮----
configured_engines: tuple[str, ...]
selected_engines: tuple[str, ...]
suppressed_engines: tuple[str, ...]
ranked_engines: tuple[str, ...]
reasons: dict[str, str]
advisory_only: bool = True
may_expand_configuration: bool = False
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _engine_memory(memories: Iterable[TechniqueMemory]) -> dict[str, TechniqueMemory]
⋮----
result: dict[str, TechniqueMemory] = {}
⋮----
prefix = "scanner:"
⋮----
engine = item.technique[len(prefix):].strip().lower()
⋮----
unknown = [engine for engine in configured_engines if engine not in _ALLOWED_ENGINES]
⋮----
memory = _engine_memory(memories)
by_kind = (worker_outcomes or {}).get("by_job_kind") or {}
reasons: dict[str, str] = {}
suppressed: set[str] = set()
⋮----
technique = memory.get(engine)
job_kind = f"{engine}_scan"
outcome = by_kind.get(job_kind) if isinstance(by_kind, dict) else None
completed = int((outcome or {}).get("completed") or 0) if isinstance(outcome, dict) else 0
requeued = int((outcome or {}).get("requeued") or 0) if isinstance(outcome, dict) else 0
failed = int((outcome or {}).get("failed") or 0) if isinstance(outcome, dict) else 0
⋮----
strong_memory_failure = bool(
unstable_worker = (requeued + failed) >= 2 and completed == 0
⋮----
reason_parts = []
⋮----
# Memory can reduce the configured set, but never eliminate all configured scanners.
⋮----
reasons = {
⋮----
def rank_key(engine: str) -> tuple[float, float, int, str]
⋮----
item = memory.get(engine)
⋮----
selected = tuple(
````

## File: backend/app/scanner_ingestion.py
````python
@dataclass(frozen=True)
class ScannerIngestionResult
⋮----
engine: str
artifact_path: str | None
findings_seen: int
findings_added: int
validation_jobs: int
⋮----
def to_dict(self) -> dict
⋮----
artifact = latest_scanner_artifact(engine, run_dir)
⋮----
findings = parse_scanner_artifact(engine, artifact, campaign)
existing = {finding.id for finding in campaign.findings}
added = 0
queued = 0
````

## File: backend/app/scanner_normalization.py
````python
_ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical"}
⋮----
@dataclass(frozen=True)
class NormalizedScannerFinding
⋮----
engine: str
title: str
severity: str
asset: str
endpoint: str | None
summary: str
evidence: tuple[str, ...] = ()
reproduction_steps: tuple[str, ...] = ()
impact: str = ""
remediation: str = ""
cwe: str | None = None
cvss: float | None = None
template_id: str | None = None
matcher_name: str | None = None
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _optional_str(value: Any) -> str | None
⋮----
def _optional_cvss(value: Any) -> float | None
⋮----
score = float(value)
⋮----
def _severity(value: Any) -> str
⋮----
normalized = str(value or "info").lower().strip()
⋮----
def _string_list(value: Any, *, limit: int = 50) -> tuple[str, ...]
⋮----
items = [value]
⋮----
items = list(value)
⋮----
def normalize_strix_item(item: dict[str, Any], campaign: Campaign) -> NormalizedScannerFinding | None
⋮----
asset = str(item.get("asset") or item.get("target") or campaign.target.primary_url)
host = (urlparse(asset).hostname or asset.split(":")[0]).lower()
⋮----
cwe = item.get("cwe")
⋮----
cwe = ", ".join(str(x) for x in cwe)
⋮----
def normalize_nuclei_item(item: dict[str, Any], campaign: Campaign) -> NormalizedScannerFinding | None
⋮----
matched_at = str(item.get("matched-at") or item.get("matched_at") or item.get("url") or "")
host = (urlparse(matched_at).hostname or "").lower()
⋮----
info = item.get("info") if isinstance(item.get("info"), dict) else {}
classification = info.get("classification") if isinstance(info.get("classification"), dict) else {}
cwe = classification.get("cwe-id") or classification.get("cwe_id")
⋮----
extracted = item.get("extracted-results") or item.get("extracted_results") or []
matcher = item.get("matcher-name") or item.get("matcher_name")
template_id = item.get("template-id") or item.get("template_id")
⋮----
def normalized_finding_id(item: NormalizedScannerFinding) -> str
⋮----
canonical = json.dumps(
digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
⋮----
def to_campaign_finding(item: NormalizedScannerFinding) -> Finding
⋮----
def dedupe_normalized(items: Iterable[NormalizedScannerFinding]) -> list[NormalizedScannerFinding]
⋮----
seen: set[str] = set()
result: list[NormalizedScannerFinding] = []
⋮----
finding_id = normalized_finding_id(item)
````

## File: backend/app/scanner_registry.py
````python
Parser = Callable[[str | Path, Campaign], list[Finding]]
⋮----
@dataclass(frozen=True)
class ScannerAdapter
⋮----
engine: str
format: str
parser: Parser
artifact_globs: tuple[str, ...]
⋮----
_ADAPTERS: dict[str, ScannerAdapter] = {
⋮----
def scanner_adapter(engine: str) -> ScannerAdapter
⋮----
key = str(engine).strip().lower()
⋮----
def scanner_adapters() -> tuple[ScannerAdapter, ...]
⋮----
adapter = scanner_adapter(engine)
root = Path(output_dir)
⋮----
root_resolved = root.resolve(strict=True)
⋮----
matches: dict[str, Path] = {}
⋮----
resolved = candidate.resolve(strict=True)
⋮----
artifacts = discover_scanner_artifacts(engine, output_dir)
````

## File: backend/app/scanner_sandbox.py
````python
class ScannerSandboxConfigError(ValueError)
⋮----
@dataclass(frozen=True)
class ScannerSandboxAdmission
⋮----
ready: bool
profile: str
worker_role: str
read_only_rootfs: bool
no_new_privileges: bool
cap_drop_all: bool
dedicated_worker: bool
allowed_engines: tuple[str, ...]
runtime_read_only_rootfs: bool
runtime_no_new_privileges: bool
runtime_cap_drop_all: bool
runtime_attested: bool
block_reasons: tuple[str, ...]
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
payload = asdict(self)
⋮----
def _strict_bool(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _runtime_hardening_attestation() -> dict[str, bool]
⋮----
"""Verify Linux sandbox properties from the running process, fail-closed."""
⋮----
status = Path("/proc/self/status").read_text(encoding="utf-8")
status_fields = {}
⋮----
no_new_privileges = status_fields.get("NoNewPrivs") == "1"
cap_eff_raw = status_fields.get("CapEff")
cap_drop_all = bool(cap_eff_raw) and int(cap_eff_raw, 16) == 0
⋮----
mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
rootfs_read_only = False
⋮----
parts = line.split()
⋮----
mount_options = set(parts[5].split(","))
rootfs_read_only = "ro" in mount_options and "rw" not in mount_options
⋮----
def _allowed_engines() -> tuple[str, ...]
⋮----
raw = os.getenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei").strip()
⋮----
engines = tuple(sorted({item.strip().lower() for item in raw.split(",") if item.strip()}))
supported = {"nuclei", "strix"}
⋮----
def scanner_sandbox_admission(engine: str | None = None) -> ScannerSandboxAdmission
⋮----
worker_role = (os.getenv("XBOW_WORKER_ROLE") or "").strip().lower()
profile = (os.getenv("XBOW_SCANNER_SANDBOX_PROFILE") or "").strip().lower()
read_only_rootfs = _strict_bool("XBOW_SANDBOX_READ_ONLY_ROOTFS", False)
no_new_privileges = _strict_bool("XBOW_SANDBOX_NO_NEW_PRIVILEGES", False)
cap_drop_all = _strict_bool("XBOW_SANDBOX_CAP_DROP_ALL", False)
allowed_engines = _allowed_engines()
scanner_worker_enabled = _strict_bool("XBOW_ENABLE_SCANNER_WORKER", False)
runtime = _runtime_hardening_attestation()
runtime_read_only_rootfs = bool(runtime.get("read_only_rootfs"))
runtime_no_new_privileges = bool(runtime.get("no_new_privileges"))
runtime_cap_drop_all = bool(runtime.get("cap_drop_all"))
runtime_attested = (
⋮----
reasons: list[str] = []
⋮----
def safe_scanner_sandbox_admission(engine: str | None = None) -> dict[str, Any]
⋮----
def require_scanner_sandbox(engine: str) -> ScannerSandboxAdmission
⋮----
admission = scanner_sandbox_admission(engine)
````

## File: backend/app/scanner_worker.py
````python
@dataclass(frozen=True)
class ScannerJobResult
⋮----
engine: str
status: str
ingestion: ScannerIngestionResult | None
event: dict
⋮----
def _state_after_scan(campaign: Campaign) -> CampaignState
⋮----
unresolved = any(
⋮----
run_dir = str(
plan = build_strix_plan(campaign, run_dir)
execution = execute(plan)
⋮----
event = {
⋮----
ingestion = ingest_scanner_run(
⋮----
plan = build_nuclei_plan(campaign, run_dir)
````

## File: backend/app/secret_vault.py
````python
class SecretVaultError(RuntimeError)
⋮----
def _decode_master_key(value: str) -> bytes
⋮----
key = base64.urlsafe_b64decode(value.encode("ascii"))
⋮----
def _load_key_sources(inline_name: str, file_name: str, label: str) -> bytes
⋮----
inline = os.getenv(inline_name, "").strip()
key_file = os.getenv(file_name, "").strip()
⋮----
path = Path(key_file)
⋮----
stat = path.stat()
⋮----
inline = path.read_text(encoding="utf-8").strip()
⋮----
def load_master_key() -> bytes
⋮----
def load_new_master_key() -> bytes
⋮----
def _vault_path() -> Path
⋮----
raw = os.getenv("XBOW_VAULT_PATH", "/data/secrets.vault.json").strip()
path = Path(raw)
⋮----
def _load_document(path: Path) -> dict[str, Any]
⋮----
data = json.loads(path.read_text(encoding="utf-8"))
⋮----
def _atomic_write(path: Path, payload: dict[str, Any]) -> None
⋮----
tmp = path.with_name(path.name + ".tmp")
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
⋮----
def set_secret(name: str, value: str) -> None
⋮----
key = load_master_key()
path = _vault_path()
doc = _load_document(path)
nonce = os.urandom(12)
ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))
⋮----
def get_secret(name: str) -> str
⋮----
record = doc["secrets"].get(name)
⋮----
nonce = base64.urlsafe_b64decode(record["nonce"].encode("ascii"))
ciphertext = base64.urlsafe_b64decode(record["ciphertext"].encode("ascii"))
plaintext = AESGCM(key).decrypt(nonce, ciphertext, name.encode("utf-8"))
⋮----
def vault_enabled() -> bool
⋮----
value = os.getenv("XBOW_VAULT_ENABLED", "false").strip().lower()
⋮----
def resolve_secret(vault_name: str, env_name: str) -> str | None
⋮----
enabled = vault_enabled()
inline = os.getenv(env_name)
⋮----
def rekey_vault() -> dict[str, int]
⋮----
old_key = load_master_key()
new_key = load_new_master_key()
⋮----
plaintexts: dict[str, bytes] = {}
⋮----
# Decrypt everything before writing anything. Any corrupt entry aborts the rotation.
⋮----
rotated = {"version": 1, "secrets": {}}
⋮----
ciphertext = AESGCM(new_key).encrypt(
````

## File: backend/app/storage_backend.py
````python
@runtime_checkable
class StorageBackend(Protocol)
⋮----
artifact_root: object
⋮----
def health(self) -> dict: ...
def save_campaign(self, document: dict, *, expected_version: int | None = None) -> int: ...
def get_campaign_record(self, campaign_id: str): ...
def get_campaign(self, campaign_id: str): ...
def list_campaigns(self) -> list[dict]: ...
def put_observation(self, campaign_id: str, observation: dict) -> dict: ...
def list_observations(self, campaign_id: str) -> list[dict]: ...
def put_hypothesis_snapshot(self, campaign_id: str, graph_fingerprint: str, hypotheses: list[dict]) -> dict: ...
def list_hypothesis_snapshots(self, campaign_id: str, *, limit: int = 50) -> list[dict]: ...
def put_advisory_focus_snapshot(self, campaign_id: str, fingerprint: str, advisory: dict) -> dict: ...
def list_advisory_focus_snapshots(self, campaign_id: str, *, limit: int = 50) -> list[dict]: ...
def put_artifact(self, campaign_id: str, kind: str, content: bytes, **kwargs) -> dict: ...
def list_artifacts(self, campaign_id: str) -> list[dict]: ...
def read_artifact(self, campaign_id: str, artifact_id: str): ...
def get_artifact(self, campaign_id: str, artifact_id: str): ...
def has_artifact(self, campaign_id: str, **kwargs) -> bool: ...
⋮----
def storage_backend_name() -> str
⋮----
value = os.getenv("XBOW_STORAGE_BACKEND", "sqlite").strip().lower()
aliases = {
value = aliases.get(value, value)
⋮----
def create_storage() -> StorageBackend
⋮----
backend = storage_backend_name()
````

## File: backend/app/storage.py
````python
def utcnow() -> str
⋮----
class ArtifactIntegrityError(RuntimeError)
⋮----
class CampaignConflictError(RuntimeError)
⋮----
def _max_artifact_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_ARTIFACT_BYTES", str(10 * 1024 * 1024))
⋮----
limit = int(raw)
⋮----
def _max_campaign_document_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_CAMPAIGN_DOCUMENT_BYTES", str(2 * 1024 * 1024))
⋮----
def _max_observation_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_OBSERVATION_BYTES", "65536")
⋮----
def _bounded_identifier(value: str, name: str, *, max_length: int = 200) -> str
⋮----
normalized = value.strip()
⋮----
def _harden_private_path(path: Path, mode: int) -> None
⋮----
def _validate_media_type(media_type: str) -> str
⋮----
value = media_type.strip()
⋮----
class Storage
⋮----
"""Durable campaign state plus content-addressed evidence metadata."""
⋮----
storage_name = "sqlite"
⋮----
ALLOWED_ARTIFACT_KINDS = {
ALLOWED_OBSERVATION_KINDS = {
⋮----
def __init__(self, db_path: str | None = None, artifact_root: str | None = None)
⋮----
@contextmanager
    def connect(self)
⋮----
db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
⋮----
def _init(self) -> None
⋮----
campaign_columns = {row["name"] for row in db.execute("PRAGMA table_info(campaigns)").fetchall()}
⋮----
columns = {row["name"] for row in db.execute("PRAGMA table_info(artifacts)").fetchall()}
⋮----
def health(self) -> dict[str, Any]
⋮----
row = db.execute("SELECT 1").fetchone()
⋮----
def save_campaign(self, document: dict[str, Any], *, expected_version: int | None = None) -> int
⋮----
"""Persist a campaign and optionally reject stale snapshot writes.

        Callers that perform read-modify-write cycles can pass the version returned
        by get_campaign_record(). A mismatch fails instead of silently overwriting
        a newer campaign snapshot.
        """
required = {"id", "state", "created_at", "updated_at"}
⋮----
document = dict(document)
⋮----
encoded = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
⋮----
current = db.execute("SELECT version FROM campaigns WHERE id=?", (document["id"],)).fetchone()
⋮----
current_version = int(current["version"])
⋮----
next_version = current_version + 1
cursor = db.execute(
⋮----
def get_campaign_record(self, campaign_id: str) -> tuple[dict[str, Any], int] | None
⋮----
campaign_id = _bounded_identifier(campaign_id, "campaign_id")
⋮----
row = db.execute("SELECT document,version FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
⋮----
def get_campaign(self, campaign_id: str) -> dict[str, Any] | None
⋮----
record = self.get_campaign_record(campaign_id)
⋮----
def list_campaigns(self) -> list[dict[str, Any]]
⋮----
rows = db.execute("SELECT document FROM campaigns ORDER BY created_at DESC").fetchall()
⋮----
def put_observation(self, campaign_id: str, observation: dict[str, Any]) -> dict[str, Any]
⋮----
required = {"id", "kind", "value", "source"}
⋮----
kind = str(observation["kind"])
⋮----
parent_ids = tuple(str(item) for item in observation.get("parent_ids", ()))
⋮----
parent_ids = tuple(
metadata = observation.get("metadata", {})
⋮----
record = {
⋮----
encoded_observation = json.dumps(
⋮----
placeholders = ",".join("?" for _ in parent_ids)
rows = db.execute(
⋮----
existing = db.execute(
⋮----
comparable = {
requested = {key: record[key] for key in ("kind", "value", "source", "parent_ids", "metadata")}
⋮----
def list_observations(self, campaign_id: str) -> list[dict[str, Any]]
⋮----
fingerprint = _bounded_identifier(fingerprint, "advisory_fingerprint", max_length=64)
⋮----
encoded = json.dumps(
⋮----
now = utcnow()
⋮----
graph_fingerprint = _bounded_identifier(
payload = {
⋮----
def _safe_campaign_artifact_dir(self, campaign_id: str) -> Path
⋮----
root = self.artifact_root.resolve()
candidate = self.artifact_root / campaign_id
⋮----
resolved = candidate.resolve(strict=False)
⋮----
final = resolved.resolve()
⋮----
finding_id = _bounded_identifier(finding_id, "finding_id")
⋮----
idempotency_key = idempotency_key.strip()
⋮----
max_bytes = _max_artifact_bytes()
⋮----
media_type = _validate_media_type(media_type)
digest = hashlib.sha256(content).hexdigest()
⋮----
exists = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
⋮----
artifact_id = str(uuid4())
⋮----
campaign_dir = self._safe_campaign_artifact_dir(campaign_id)
path = campaign_dir / f"{artifact_id}.bin"
tmp = path.with_suffix(".tmp")
⋮----
relative = str(path.relative_to(root))
⋮----
def list_artifacts(self, campaign_id: str) -> list[dict[str, Any]]
⋮----
def get_artifact(self, campaign_id: str, artifact_id: str) -> dict[str, Any] | None
⋮----
artifact_id = _bounded_identifier(artifact_id, "artifact_id")
⋮----
row = db.execute(
⋮----
def has_artifact(self, campaign_id: str, *, finding_id: str | None = None, kind: str | None = None) -> bool
⋮----
clauses = ["campaign_id=?"]
params: list[Any] = [campaign_id]
⋮----
row = db.execute(f"SELECT 1 FROM artifacts WHERE {' AND '.join(clauses)} LIMIT 1", params).fetchone()
⋮----
def read_artifact(self, campaign_id: str, artifact_id: str) -> tuple[dict[str, Any], bytes]
⋮----
metadata = self.get_artifact(campaign_id, artifact_id)
⋮----
path = (self.artifact_root / metadata["relative_path"]).resolve()
⋮----
content = path.read_bytes()
⋮----
public_metadata = {key: value for key, value in metadata.items() if key != "relative_path"}
````

## File: backend/app/strix_parser.py
````python
class StrixParserError(RuntimeError)
⋮----
def max_strix_json_bytes() -> int
⋮----
raw = os.getenv("XBOW_MAX_STRIX_JSON_BYTES", str(5 * 1024 * 1024))
⋮----
limit = int(raw)
⋮----
def parse_strix_json(path: str | Path, campaign: Campaign) -> list[Finding]
⋮----
path = Path(path)
⋮----
raw = json.loads(path.read_text(encoding="utf-8"))
⋮----
items = raw
⋮----
items = (
⋮----
normalized = []
⋮----
finding = normalize_strix_item(item, campaign)
````

## File: backend/app/submission_api.py
````python
router = APIRouter()
⋮----
def _context(campaign_id: str)
⋮----
def _verified_report(campaign, store, artifact_id: str) -> dict
⋮----
def _save(campaign, version: int) -> None
⋮----
def _assert_report_review_ready(campaign, store) -> None
⋮----
confirmed = [item for item in campaign.findings if str(item.status) == "confirmed"]
⋮----
graph = load_observation_graph(store, campaign.id)
readiness = {
blocked = [
⋮----
@router.get("/api/campaigns/{campaign_id}/reports/submission-states")
def list_submission_states(campaign_id: str)
⋮----
report_ids = [
states = [
counts = Counter(item["state"] for item in states)
⋮----
@router.get("/api/campaigns/{campaign_id}/reports/{artifact_id}/submission-state")
def get_submission_state(campaign_id: str, artifact_id: str)
⋮----
artifact = _verified_report(campaign, store, artifact_id)
⋮----
@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/approve")
def approve_report(campaign_id: str, artifact_id: str, reviewer: str)
⋮----
current = approval_status_from_storage(campaign, store, artifact_id)
reviewer = reviewer.strip()
⋮----
@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/revoke-approval")
def revoke_report_approval(campaign_id: str, artifact_id: str, reviewer: str)
⋮----
relevant = [
⋮----
current = submission_status(campaign, artifact)
actor = actor.strip()
````

## File: backend/app/submission_state.py
````python
SubmissionState = Literal["draft", "review_required", "approved", "submitted"]
⋮----
@dataclass(frozen=True)
class SubmissionStatus
⋮----
artifact_id: str
state: SubmissionState
approved: bool
stale: bool
reviewer: str | None
submitted_at: str | None
submitted_by: str | None
platform: str | None
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
def submission_event(artifact_id: str, actor: str, platform: str, at: str) -> dict[str, Any]
⋮----
artifact_id = artifact_id.strip()
actor = actor.strip()
platform = platform.strip()
at = at.strip()
⋮----
def _approval_events(campaign: Any, artifact_id: str) -> list[tuple[int, dict[str, Any]]]
⋮----
def submission_status(campaign: Any, artifact: dict[str, Any]) -> SubmissionStatus
⋮----
artifact_id = artifact["id"]
approval = approval_status(campaign, artifact)
approval_events = _approval_events(campaign, artifact_id)
revoked = bool(approval_events) and approval_events[-1][1].get("type") == "report_approval_revoked"
⋮----
all_submissions = [
⋮----
state: SubmissionState = "review_required" if all_submissions or approval.stale or revoked else "draft"
⋮----
latest_approval_index = approval_events[-1][0] if approval_events else -1
current_cycle_submissions = [
⋮----
latest = current_cycle_submissions[-1]
⋮----
def assert_submission_allowed(campaign: Any, artifact: dict[str, Any]) -> SubmissionStatus
⋮----
status = submission_status(campaign, artifact)
````

## File: backend/app/swarm_coordinator.py
````python
@dataclass(frozen=True)
class SwarmBudget
⋮----
max_tasks: int = 5
max_total_requests: int = 80
max_network_agents: int = 5
⋮----
def __post_init__(self) -> None
⋮----
def to_dict(self) -> dict[str, Any]
⋮----
@dataclass(frozen=True)
class SwarmCoordination
⋮----
tasks: tuple[ReconTask, ...]
request_budget_used: int
request_budget_remaining: int
active_agents: tuple[str, ...]
suppressed_tasks: tuple[str, ...]
⋮----
def _capability_by_task() -> dict[str, ReconCapability]
⋮----
capabilities = recon_capabilities()
mapping = {item.task_kind: item for item in capabilities}
⋮----
limits = budget or SwarmBudget()
capabilities = _capability_by_task()
selected: list[ReconTask] = []
suppressed: list[str] = []
agents: set[str] = set()
used = 0
⋮----
capability = capabilities.get(task.kind)
⋮----
profile = agent_by_name(task.agent)
⋮----
expected_action = f"recon:{task.kind}"
⋮----
remaining = limits.max_total_requests - used
⋮----
allocated = min(task.max_requests, remaining)
````

## File: backend/app/totp_auth.py
````python
def _strict_bool(name: str, default: bool = False) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def totp_enabled() -> bool
⋮----
def configured_totp_secret() -> bytes
⋮----
inline = os.getenv("XBOW_TOTP_SECRET", "").strip()
⋮----
use_vault = vault_enabled()
⋮----
inline = get_secret("totp_secret")
⋮----
normalized = inline.replace(" ", "").upper()
⋮----
secret = base64.b32decode(normalized, casefold=True)
⋮----
def _totp(secret: bytes, counter: int, digits: int = 6) -> str
⋮----
digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
offset = digest[-1] & 0x0F
binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
⋮----
def _matching_totp_counter(code: str, *, now: float | None = None) -> int | None
⋮----
secret = configured_totp_secret()
timestamp = time.time() if now is None else now
counter = int(timestamp // 30)
# One adjacent step tolerates small clock skew while remaining bounded.
⋮----
def verify_totp_code(code: str, *, now: float | None = None) -> bool
⋮----
_replay_lock = Lock()
_used_totp: dict[str, float] = {}
⋮----
def _replay_backend() -> str
⋮----
backend = os.getenv("XBOW_TOTP_REPLAY_BACKEND", "memory").strip().lower()
⋮----
def _consume_memory(key: str, ttl_seconds: int, now: float) -> bool
⋮----
expired = [item for item, expiry in _used_totp.items() if expiry <= now]
⋮----
def _consume_redis(key: str, ttl_seconds: int) -> bool
⋮----
url = os.getenv("XBOW_TOTP_REPLAY_REDIS_URL", "").strip()
⋮----
client = redis.Redis.from_url(
⋮----
def consume_totp_code(code: str, *, now: float | None = None) -> bool
⋮----
counter = _matching_totp_counter(code, now=timestamp)
⋮----
fingerprint = hashlib.sha256(
ttl_seconds = 90
key = f"xbow:totp-used:{fingerprint}"
⋮----
def require_totp_for_mutation(request: Request) -> None
⋮----
code = request.headers.get("x-totp-code", "").strip()
````

## File: backend/app/validation_state.py
````python
@dataclass(frozen=True)
class ValidationState
⋮----
finding_ids: frozenset[str]
attempted_finding_ids: frozenset[str]
observed_independent_finding_ids: frozenset[str]
evidence_backed_independent_finding_ids: frozenset[str]
⋮----
@property
    def unresolved_finding_ids(self) -> frozenset[str]
⋮----
@property
    def unattempted_finding_ids(self) -> frozenset[str]
⋮----
@property
    def unevidenced_finding_ids(self) -> frozenset[str]
⋮----
@property
    def all_observed_independently(self) -> bool
⋮----
@property
    def all_evidence_backed_independently(self) -> bool
⋮----
def analyze_validation_state(graph: Any) -> ValidationState
⋮----
"""Compute finding validation state once from an observation graph.

    Evidence-backed validation requires an independent observed validation node
    with at least one evidence observation directly attached to that validation.
    """
finding_by_id = {item.id: item for item in graph.by_kind("finding")}
evidence_parent_ids = {
attempted: set[str] = set()
observed_independent: set[str] = set()
evidence_backed_independent: set[str] = set()
⋮----
finding = finding_by_id.get(parent_id)
⋮----
def observed_independent_finding_ids(graph: Any) -> set[str]
⋮----
"""Return finding observation IDs backed by independent observed validation."""
⋮----
def evidence_backed_independent_finding_ids(graph: Any) -> set[str]
⋮----
"""Return findings whose independent observed validation has child evidence."""
⋮----
def attempted_finding_ids(graph: Any) -> set[str]
⋮----
"""Return finding observation IDs that have any validation attempt."""
⋮----
def has_observed_independent_validation(graph: Any, finding_id: str) -> bool
⋮----
def has_evidence_backed_independent_validation(graph: Any, finding_id: str) -> bool
````

## File: backend/app/validator.py
````python
class ValidationPolicyError(RuntimeError)
⋮----
class _NoRedirect(HTTPRedirectHandler)
⋮----
def redirect_request(self, req, fp, code, msg, headers, newurl)
⋮----
@dataclass(frozen=True)
class ProbeResult
⋮----
status: str
url: str
parameter_names: tuple[str, ...] = ()
http_status: int | None = None
content_type: str | None = None
body_preview: str = ""
error: str | None = None
differential: dict[str, object] | None = None
⋮----
def json_bytes(self) -> bytes
⋮----
@dataclass(frozen=True)
class _HttpObservation
⋮----
http_status: int | None
content_type: str | None
body: bytes
⋮----
def _bool_env(name: str, default: bool = False) -> bool
⋮----
value = os.getenv(name)
⋮----
normalized = value.strip().lower()
⋮----
def _validation_timeout_seconds() -> float
⋮----
raw = os.getenv("XBOW_VALIDATION_TIMEOUT_SECONDS", "10")
⋮----
timeout = float(raw)
⋮----
def _validation_preview_chars() -> int
⋮----
raw = os.getenv("XBOW_VALIDATION_PREVIEW_CHARS", "4096")
⋮----
limit = int(raw)
⋮----
def _preview_body(body: bytes, content_type: str | None) -> str
⋮----
media_type = (content_type or "").split(";", 1)[0].strip().lower()
text_like = (
⋮----
def _redact_query_values(preview: str, url: str) -> str
⋮----
"""Remove original query values from persisted evidence previews."""
⋮----
values = {
redacted = preview
candidates: set[str] = set()
⋮----
redacted = redacted.replace(candidate, "[redacted]")
⋮----
def _validation_max_bytes() -> int
⋮----
raw = os.getenv("XBOW_VALIDATION_MAX_BYTES", "262144")
⋮----
max_bytes = int(raw)
⋮----
def _validation_rps(campaign) -> float
⋮----
rps = float(campaign.target.rules.max_requests_per_second)
⋮----
def _evidence_url(url: str) -> tuple[str, tuple[str, ...]]
⋮----
parsed = urlparse(url)
parameter_names = tuple(
safe_url = parsed._replace(query="", fragment="").geturl()
⋮----
def _request_get(opener, url: str, *, timeout: float, max_bytes: int) -> _HttpObservation
⋮----
request = Request(
⋮----
body = response.read(max_bytes + 1)[:max_bytes]
⋮----
body = exc.read(max_bytes + 1)[:max_bytes] if exc.fp else b""
⋮----
def _differential_marker(campaign, finding, parameter: str) -> str
⋮----
seed = f"{campaign.id}:{finding.id}:{parameter}".encode("utf-8")
⋮----
def _marker_url(url: str, campaign, finding) -> tuple[str, str, str] | None
⋮----
pairs = parse_qsl(parsed.query, keep_blank_values=True)
⋮----
parameter = pairs[0][0]
marker = _differential_marker(campaign, finding, parameter)
⋮----
def build_probe_url(campaign, finding) -> str
⋮----
"""Resolve one read-only validation URL and fail closed on scope ambiguity."""
⋮----
primary = str(campaign.target.primary_url)
candidate = finding.endpoint or finding.asset or primary
⋮----
candidate = urljoin(primary, candidate)
⋮----
# Bare hosts are not sufficient for an HTTP reproduction. Falling back to
# the campaign primary URL avoids guessing a path or scheme.
candidate = primary
⋮----
parsed = urlparse(candidate)
⋮----
host = parsed.hostname.lower().rstrip(".")
rules = campaign.target.rules
⋮----
def safe_http_probe(campaign, finding) -> ProbeResult
⋮----
"""Capture bounded HTTP evidence and optionally one inert differential sample.

    Active validation and differential validation are independently gated off by
    default. Redirects are not followed, only GET is used, and a differential
    request may replace only an already-present query value with an inert marker.
    The result is evidence only; it never confirms a vulnerability.
    """
url = build_probe_url(campaign, finding)
⋮----
differential_enabled = _bool_env("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", False)
timeout = _validation_timeout_seconds()
max_bytes = _validation_max_bytes()
opener = build_opener(_NoRedirect())
baseline = _request_get(opener, url, timeout=timeout, max_bytes=max_bytes)
⋮----
marker_request = _marker_url(url, campaign, finding)
⋮----
differential = {
⋮----
marker_observation = _request_get(
⋮----
marker_bytes = marker.encode("utf-8")
⋮----
preview = _preview_body(baseline.body, baseline.content_type)
````

## File: backend/app/vault_cli.py
````python
def main() -> int
⋮----
parser = argparse.ArgumentParser(
⋮----
args = parser.parse_args()
⋮----
result = rekey_vault()
````

## File: backend/app/worker_audit.py
````python
_AUDIT_FIELDS = {
⋮----
def _canonical_worker_event(event: dict[str, Any]) -> bytes
⋮----
payload = {key: event.get(key) for key in sorted(_AUDIT_FIELDS)}
⋮----
def next_worker_audit_link(events: list[dict[str, Any]]) -> tuple[int, str | None]
⋮----
sealed = [
⋮----
latest = max(sealed, key=lambda item: int(item["audit_seq"]))
⋮----
sealed = dict(event)
⋮----
canonical = _canonical_worker_event(sealed)
⋮----
secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
⋮----
def verify_worker_audit_chain(events: list[dict[str, Any]]) -> dict[str, Any]
⋮----
outcomes = [item for item in events if item.get("type") == "worker_outcome"]
legacy = [
⋮----
expected_seq = 1
previous_hash: str | None = None
checked = 0
⋮----
canonical = _canonical_worker_event(item)
actual_hash = hashlib.sha256(canonical).hexdigest()
⋮----
signature = item.get("worker_signature")
⋮----
expected_signature = hmac.new(
⋮----
previous_hash = str(item["worker_hash"])
````

## File: backend/app/worker_service.py
````python
class CampaignCancelledError(ValueError)
⋮----
class StaleValidationJobError(ValidationPolicyError)
⋮----
class StaleBrowserJobError(BrowserPolicyError)
⋮----
# Backward-compatible re-export for existing imports/tests.
_state_after_scan = _scanner_state_after_scan
⋮----
def _save(store: Storage, campaign: Campaign, version: int) -> int
⋮----
def _campaign(store: Storage, campaign_id: str) -> tuple[Campaign, int]
⋮----
record = store.get_campaign_record(campaign_id)
⋮----
campaign = Campaign.model_validate(raw)
⋮----
def _append_event_once(campaign: Campaign, event: dict) -> None
⋮----
event_type = event.get("type")
job_id = event.get("job_id")
⋮----
# Backward-compatible aliases for historical imports/tests.
_observation_id = observation_id
_record_asset_observation = record_asset
_record_endpoint_observation = record_endpoint
_record_finding_observation = record_finding_chain
_record_artifact_observation = record_artifact
⋮----
@contextmanager
def _lease_heartbeat(queue: JobQueue, job_id: str, worker_id: str)
⋮----
"""Keep ownership of a long-running job without hiding lease loss."""
lease_seconds = int(os.getenv("XBOW_JOB_LEASE_SECONDS", "21600"))
interval = max(10.0, min(300.0, lease_seconds / 3))
stop = threading.Event()
lost = threading.Event()
⋮----
def renew() -> None
⋮----
thread = threading.Thread(target=renew, name=f"lease-{job_id[:8]}", daemon=True)
⋮----
def _process_scanner_job(job: dict, queue: JobQueue, store: Storage, runner) -> None
⋮----
result = runner(job, campaign, queue, store)
⋮----
def process_strix_scan(job: dict, queue: JobQueue, store: Storage) -> None
⋮----
def process_nuclei_scan(job: dict, queue: JobQueue, store: Storage) -> None
⋮----
def process_validation(job: dict, store: Storage) -> None
⋮----
"""Capture independent read-only HTTP evidence without self-confirming findings."""
⋮----
finding_id = str(job["payload"].get("finding_id") or "")
finding = next((f for f in campaign.findings if f.id == finding_id), None)
⋮----
finding_observation_id = record_finding_chain(store, campaign, finding)
result = safe_http_probe(campaign, finding)
artifact = store.put_artifact(
validation_observation_id = record_artifact(
⋮----
def process_browser_flow(job: dict, store: Storage) -> None
⋮----
asset_id = record_asset(store, campaign, str(campaign.target.primary_url), "browser")
result = execute_browser_flow(campaign, job["payload"])
artifacts = persist_browser_result(store, campaign.id, result, idempotency_prefix=job["id"])
⋮----
operation = observation.get("operation")
⋮----
action = str(form.get("action") or "")
⋮----
def process_recon_task(job: dict, store: Storage) -> None
⋮----
result = execute_recon_task(campaign, job["payload"])
source = f"recon:{job['payload'].get('kind', 'unknown')}"
asset_id = record_asset(
⋮----
def process_report(job: dict, store: Storage) -> None
⋮----
platform = str(job.get("payload", {}).get("platform") or "generic")
⋮----
graph = ObservationGraph.from_records(store.list_observations(campaign.id))
quality = {
report = render_markdown(
⋮----
def _record_worker_outcome(store: Storage, job: dict, *, success: bool, status: str) -> bool
⋮----
"""Persist a bounded, idempotent worker outcome without job payloads or errors."""
event = worker_outcome_event(job, success=success, status=status)
⋮----
record = store.get_campaign_record(job["campaign_id"])
⋮----
sealed = seal_worker_outcome_event(
⋮----
def _worker_bool(name: str, default: bool) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _legacy_unprovenanced_jobs_allowed() -> bool
⋮----
def _verify_policy_bound_job(job: dict, store: Storage) -> None
⋮----
payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
has_provenance = "_provenance" in payload
required = provenance_required_for_job_kind(str(job.get("kind") or ""))
⋮----
def _active_scanner_execution_requested() -> bool
⋮----
def _claim_for_role(queue: JobQueue, worker_id: str)
⋮----
role = (os.getenv("XBOW_WORKER_ROLE") or "").strip().lower()
⋮----
kinds = ["independent_validation", "browser_flow", "recon_task", "report"]
⋮----
def process_one(queue: JobQueue, store: Storage, worker_id: str) -> bool
⋮----
job = _claim_for_role(queue, worker_id)
⋮----
finished = queue.cancel_owned(job["id"], worker_id, str(exc))
⋮----
finished = queue.finish(job["id"], worker_id, False, f"campaign state changed concurrently: {exc}")
⋮----
finished = queue.finish(job["id"], worker_id, False, str(exc))
⋮----
finished = queue.finish(job["id"], worker_id, True)
⋮----
def _worker_poll_seconds() -> float
⋮----
raw = os.getenv("XBOW_WORKER_POLL_SECONDS", "1")
⋮----
poll = float(raw)
⋮----
def main() -> None
⋮----
queue = create_queue()
store = create_storage()
worker_id = os.getenv("XBOW_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
poll = _worker_poll_seconds()
⋮----
worked = process_one(queue, store, worker_id)
````

## File: backend/app/worker_watchdog.py
````python
def _positive_int(name: str, default: int, *, minimum: int, maximum: int) -> int
⋮----
raw = os.getenv(name, str(default))
⋮----
value = int(raw)
⋮----
def build_worker_watchdog(metrics: dict[str, Any]) -> dict[str, Any]
⋮----
"""Evaluate aggregate worker health without exposing jobs, targets, or payloads."""
max_queue_age = _positive_int(
max_lease_age = _positive_int(
max_failed = _positive_int(
⋮----
issues: list[dict[str, Any]] = []
queued_age = metrics.get("oldest_queued_age_seconds")
lease_age = metrics.get("oldest_running_lease_age_seconds")
failed = int((metrics.get("jobs_by_status") or {}).get("failed") or 0)
⋮----
status = (
````

## File: backend/app/worker.py
````python
@dataclass
class WorkerPlan
⋮----
engine: str
command: list[str]
target: str
dry_run: bool
output_dir: str
campaign_rps: float
admission_cap_rps: float | None
⋮----
class WorkerPolicyError(RuntimeError)
⋮----
def _strict_bool_env(name: str, default: bool) -> bool
⋮----
raw = os.getenv(name)
⋮----
value = raw.strip().lower()
⋮----
def _safe_strix_output_dir(output_dir: str) -> str
⋮----
root = Path(os.getenv("XBOW_STRIX_RUN_ROOT", "/data/strix_runs")).resolve()
candidate = Path(output_dir)
⋮----
resolved = candidate.resolve(strict=False)
⋮----
def _max_autonomous_rps() -> float
⋮----
limit = float(os.getenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0"))
⋮----
def _safe_nuclei_output_dir(output_dir: str) -> str
⋮----
root = Path(os.getenv("XBOW_NUCLEI_RUN_ROOT", "/data/nuclei_runs")).resolve()
⋮----
def _nuclei_rate_limit(rps: float) -> tuple[int, str]
⋮----
seconds = max(1, int(math.ceil(1 / rps)))
⋮----
def build_nuclei_plan(campaign: Campaign, output_dir: str = "/data/nuclei_runs") -> WorkerPlan
⋮----
output_dir = _safe_nuclei_output_dir(output_dir)
target = str(campaign.target.primary_url)
host = (urlparse(target).hostname or "").lower()
rules = campaign.target.rules
⋮----
active_enabled = _strict_bool_env("XBOW_ENABLE_ACTIVE_SCANS", False)
nuclei_enabled = _strict_bool_env("XBOW_ENABLE_NUCLEI", False)
dry_run_requested = _strict_bool_env("DRY_RUN", True)
autonomous_cap = None
⋮----
autonomous_cap = _max_autonomous_rps()
⋮----
dry_run = dry_run_requested or not active_enabled or not nuclei_enabled
⋮----
output_file = str(Path(output_dir) / "nuclei.jsonl")
cmd = [
⋮----
def build_strix_plan(campaign: Campaign, output_dir: str = "/data/strix_runs") -> WorkerPlan
⋮----
output_dir = _safe_strix_output_dir(output_dir)
⋮----
cmd = ["strix", "-n", "--target", target]
⋮----
dry_run = dry_run_requested or not active_enabled
⋮----
def _bounded_timeout() -> int
⋮----
raw = os.getenv("WORKER_TIMEOUT_SECONDS", "7200")
⋮----
timeout = int(raw)
⋮----
def _text(value: str | bytes | None) -> str
⋮----
def _verify_nuclei_runtime(environment: dict[str, str]) -> str
⋮----
expected = (os.getenv("XBOW_NUCLEI_ALLOWED_VERSION") or "").strip()
⋮----
result = subprocess.run(
⋮----
output = f"{result.stdout}\n{result.stderr}".strip()
⋮----
def execute(plan: WorkerPlan) -> dict
⋮----
timeout = _bounded_timeout()
output = Path(plan.output_dir)
⋮----
environment = _worker_env()
⋮----
isolated_home = output / ".nuclei-home"
⋮----
environment = {
⋮----
sandbox = require_scanner_sandbox(plan.engine)
⋮----
def _worker_env() -> dict[str, str]
⋮----
"""Pass an explicit environment allowlist; never inherit arbitrary secrets."""
allowed = {
environment = {k: v for k, v in os.environ.items() if k in allowed}
⋮----
use_vault = vault_enabled()
⋮----
secret = get_secret(vault_name)
⋮----
secret = os.getenv(env_name)
⋮----
def _max_strix_json_bytes() -> int
⋮----
def locate_vulnerabilities_json(output_dir: str) -> Path | None
⋮----
candidate = latest_scanner_artifact("strix", output_dir)
⋮----
def parse_strix_vulnerabilities(path: str | Path, campaign: Campaign) -> list[Finding]
⋮----
"""Compatibility wrapper around the isolated Strix parser."""
⋮----
def persist_execution_artifacts(store: Storage, campaign_id: str, result: dict) -> list[dict]
⋮----
artifacts: list[dict] = []
⋮----
content = result.get(key)
⋮----
vuln_path = locate_vulnerabilities_json(str(result.get("output_dir") or ""))
````

## File: backend/tests/test_adaptive_cycle.py
````python
def _gate(*, blocked: bool = False, human: bool = False, focus: str = "review_surface") -> AutonomyGate
⋮----
def test_cycle_halts_when_gate_is_blocked()
⋮----
cycle = build_adaptive_cycle(
⋮----
def test_cycle_maps_safe_planner_actions_to_bounded_states()
⋮----
def test_cycle_requires_human_for_report_focus()
⋮----
def test_cycle_suppresses_repeated_failed_techniques()
⋮----
memory = TechniqueMemory(
⋮----
def test_adaptive_cycle_route_is_exposed()
⋮----
def test_cycle_halts_for_human_review_after_repeated_requeues_without_success()
⋮----
worker_outcomes = {
⋮----
def test_cycle_does_not_suppress_recovered_worker_kind()
````

## File: backend/tests/test_agent_registry.py
````python
def test_agent_registry_routes_every_planner_action()
⋮----
expected = {
⋮----
def test_agent_registry_fails_closed_for_unknown_action()
⋮----
def test_public_catalog_contains_no_destructive_capability()
⋮----
serialized = str(public_agent_catalog()).lower()
⋮----
def test_specialized_recon_agents_are_registered_centrally()
⋮----
profile = agent_by_name(name)
⋮----
def test_agent_by_name_fails_closed_for_unknown_agent()
````

## File: backend/tests/test_alert_delivery.py
````python
class Response
⋮----
status = 204
⋮----
def __enter__(self)
⋮----
def __exit__(self, *_args)
⋮----
class Opener
⋮----
def __init__(self)
⋮----
def open(self, request, timeout)
⋮----
def _alerts()
⋮----
def test_webhook_delivery_is_redacted_and_https_only(monkeypatch)
⋮----
opener = Opener()
⋮----
result = deliver_alerts(_alerts())
⋮----
body = json.loads(request.data.decode("utf-8"))
⋮----
def test_webhook_delivery_skips_when_no_active_alerts(monkeypatch)
⋮----
result = deliver_alerts({"status": "ok", "alerts": []})
⋮----
def test_webhook_rejects_unsafe_destinations(monkeypatch, url)
⋮----
def test_webhook_hmac_signature(monkeypatch)
⋮----
signature = request.headers["X-xbow-signature-sha256"]
⋮----
def test_webhook_vault_mode_refuses_legacy_signing_secret(monkeypatch)
⋮----
def test_webhook_timeout_configuration_fails_closed(monkeypatch)
````

## File: backend/tests/test_api_idempotency.py
````python
def _setup(tmp_path, monkeypatch, *, findings=None)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
⋮----
def _record_observed_validation(db, artifacts, finding_id="f1")
⋮----
store = Storage(db, artifacts)
⋮----
def test_duplicate_finding_retry_returns_existing_and_keeps_one_job(tmp_path, monkeypatch)
⋮----
finding = Finding(
⋮----
first = add_finding("c1", finding.model_copy(deep=True))
second = add_finding("c1", finding.model_copy(deep=True))
⋮----
stored = Storage(db).get_campaign("c1")
⋮----
def test_resolution_requires_observed_independent_validation(tmp_path, monkeypatch)
⋮----
def test_repeated_validation_does_not_queue_duplicate_report(tmp_path, monkeypatch)
⋮----
first = validate_finding("c1", "f1", True, "human-reviewer")
second = validate_finding("c1", "f1", True, "human-reviewer")
⋮----
def test_self_sourced_observation_cannot_unlock_resolution(tmp_path, monkeypatch)
⋮----
def test_duplicate_text_artifact_retry_reuses_artifact_and_event(tmp_path, monkeypatch)
⋮----
evidence = EvidenceInput(kind="http_evidence", content="same evidence", media_type="text/plain")
⋮----
first = add_text_artifact("c1", evidence)
second = add_text_artifact("c1", evidence)
⋮----
campaign = store.get_campaign("c1")
events = [event for event in campaign["events"] if event.get("type") == "artifact_stored"]
⋮----
def test_completed_campaign_rejects_new_findings(tmp_path, monkeypatch)
⋮----
candidate = Finding(
⋮----
db = str(tmp_path / "queue.sqlite3")
⋮----
jobs = JobQueue(db)
⋮----
campaign = Campaign.model_validate(document)
⋮----
request_id = "resume-start-request"
receipt = main.policy_receipt(
⋮----
payload = main.sanitized_scan_payload(campaign, receipt)
existing = jobs.enqueue(
⋮----
result = start_campaign(campaign.id)
⋮----
persisted = store.get_campaign(campaign.id)
⋮----
requested = [
started = [
⋮----
def test_campaign_start_reconciliation_never_reopens_completed_campaign(monkeypatch)
⋮----
result = add_finding(
⋮----
queued = [
⋮----
def test_manual_report_retry_reuses_pending_request_and_job(tmp_path, monkeypatch)
⋮----
request_id = "manual-report-resume"
⋮----
result = queue_report(campaign.id, "generic")
⋮----
original_save = main.save_campaign
⋮----
def fail_save(value, expected_version=None)
````

## File: backend/tests/test_api_outbox.py
````python
def _campaign(events)
⋮----
def test_outbox_snapshot_reports_only_unresolved_intents_and_redacts_ids()
⋮----
events = [
⋮----
snapshot = outbox_snapshot(events)
⋮----
rendered = str(snapshot)
⋮----
def test_outbox_snapshot_tracks_completion_report_separately()
⋮----
def test_outbox_snapshot_bounds_visible_items()
⋮----
snapshot = outbox_snapshot(events, max_items=2)
⋮----
def test_campaign_outbox_api_is_read_only_and_redacted(monkeypatch)
⋮----
campaign = _campaign(
⋮----
result = main.campaign_outbox_status(campaign.id, limit=10)
⋮----
def test_campaign_outbox_api_rejects_invalid_limit(monkeypatch)
⋮----
campaign = _campaign([])
⋮----
def test_outbox_recovery_reports_job_missing_without_creating_job(tmp_path, monkeypatch)
⋮----
jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
⋮----
result = main.campaign_outbox_recovery(campaign.id)
⋮----
def test_outbox_recovery_reports_terminal_job_without_raw_ids(tmp_path, monkeypatch)
⋮----
job = jobs.enqueue(
claimed = jobs.claim("worker-terminal")
⋮----
failed = jobs.finish(job["id"], "worker-terminal", False, "fixture failure")
⋮----
diagnostic = result["diagnostics"][0]
⋮----
saved = []
⋮----
result = main.reconcile_campaign_outbox_local(campaign.id)
⋮----
repaired = [
⋮----
def test_local_reconcile_never_creates_missing_job(tmp_path, monkeypatch)
⋮----
def test_local_reconcile_skips_ambiguous_completed_start_job(tmp_path, monkeypatch)
⋮----
claimed = jobs.claim("worker-start")
⋮----
completed = jobs.finish(job["id"], "worker-start", True)
⋮----
base = _campaign(
⋮----
snapshots = [
⋮----
latest = {"campaign": base.model_copy(deep=True)}
⋮----
def load(_campaign_id)
⋮----
def save(value, expected_version=None)
⋮----
result = main.reconcile_campaign_outbox_local(base.id)
````

## File: backend/tests/test_api_rate_limit.py
````python
def _request(path="/api/test", headers=())
⋮----
async def _ok(_request)
⋮----
def test_rate_limit_defaults_disabled(monkeypatch)
⋮----
config = load_api_rate_limit_config()
⋮----
def test_rate_limit_rejects_invalid_configuration(monkeypatch)
⋮----
def test_fixed_window_limiter_enforces_quota_and_retry_after()
⋮----
limiter = FixedWindowLimiter()
config = ApiRateLimitConfig(enabled=True, requests=2, window_seconds=60, max_keys=100)
⋮----
def test_fixed_window_limiter_fails_closed_at_key_capacity()
⋮----
config = ApiRateLimitConfig(enabled=True, requests=10, window_seconds=60, max_keys=2)
⋮----
def test_client_key_ignores_forwarded_headers()
⋮----
request = _request(headers=[(b"x-forwarded-for", b"203.0.113.99")])
⋮----
def test_rate_limit_middleware_returns_429(monkeypatch)
⋮----
first = asyncio.run(api_rate_limit_middleware(_request(), _ok))
second = asyncio.run(api_rate_limit_middleware(_request(), _ok))
⋮----
def test_non_api_paths_are_not_rate_limited(monkeypatch)
⋮----
first = asyncio.run(api_rate_limit_middleware(_request("/healthz"), _ok))
second = asyncio.run(api_rate_limit_middleware(_request("/healthz"), _ok))
⋮----
class _FakeRedis
⋮----
def __init__(self, replies)
⋮----
def eval(self, *args)
⋮----
reply = self.replies.pop(0)
⋮----
def test_distributed_limiter_enforces_shared_counter(monkeypatch)
⋮----
limiter = object.__new__(RedisFixedWindowLimiter)
⋮----
config = ApiRateLimitConfig(
⋮----
def test_distributed_limiter_fails_closed_on_capacity()
⋮----
def test_distributed_limiter_fails_closed_on_redis_error()
⋮----
def test_rate_limit_config_supports_redis_backend(monkeypatch)
⋮----
def test_rate_limit_config_rejects_unknown_backend(monkeypatch)
⋮----
def test_client_key_uses_forwarded_ip_only_from_trusted_proxy(monkeypatch)
⋮----
request = Request(
⋮----
def test_client_key_ignores_forwarded_ip_from_untrusted_peer(monkeypatch)
⋮----
def test_client_key_fails_closed_on_invalid_forwarded_chain(monkeypatch)
⋮----
def test_client_key_rejects_invalid_trusted_proxy_cidr(monkeypatch)
````

## File: backend/tests/test_attack_surface_scope.py
````python
def test_surface_classifies_scope_and_topology_without_network_calls()
⋮----
graph = ObservationGraph()
⋮----
result = build_attack_surface(graph, scope_checker=lambda host: host == "example.test")
by_id = {item["id"]: item for item in result["endpoints"]}
⋮----
def test_surface_route_uses_campaign_scope_rules(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_attack_surface(campaign.id)
````

## File: backend/tests/test_attack_surface.py
````python
def test_canonical_host_normalizes_case_and_trailing_dot()
⋮----
def test_canonical_endpoint_redacts_query_values_and_default_port()
⋮----
result = canonical_endpoint("HTTPS://Example.TEST:443/api/items?token=secret&id=42&id=43#frag")
⋮----
def test_canonical_endpoint_flags_invalid_port_without_leaking_query_values()
⋮----
result = canonical_endpoint("https://example.test:not-a-port/api?token=secret")
⋮----
def test_attack_surface_snapshot_is_deterministic_and_read_only()
⋮----
graph = ObservationGraph()
⋮----
result = build_attack_surface(graph)
⋮----
def test_attack_surface_models_forms_and_waf_without_secrets()
⋮----
result = build_attack_surface(graph, scope_checker=lambda host: host == "example.test")
⋮----
def test_attack_surface_counts_canonical_duplicates_and_invalid_entries()
⋮----
def test_attack_surface_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_attack_surface(campaign.id)
⋮----
def test_attack_surface_enrichment_score_rewards_cross_source_context()
````

## File: backend/tests/test_auth.py
````python
def request(headers: dict[str, str] | None = None) -> Request
⋮----
raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
⋮----
def clear_secret_env(monkeypatch)
⋮----
def test_missing_server_token_fails_closed(monkeypatch)
⋮----
def test_short_server_token_fails_closed(monkeypatch)
⋮----
def test_file_backed_secret_is_supported(monkeypatch, tmp_path)
⋮----
token = "file-token-" + "z" * 32
path = tmp_path / "api-token"
⋮----
def test_missing_secret_file_fails_closed(monkeypatch, tmp_path)
⋮----
def test_conflicting_secret_sources_fail_closed(monkeypatch, tmp_path)
⋮----
def test_whitespace_inside_token_is_rejected(monkeypatch)
⋮----
def test_missing_client_token_is_unauthorized(monkeypatch)
⋮----
def test_wrong_client_token_is_forbidden(monkeypatch)
⋮----
def test_bearer_token_is_accepted(monkeypatch)
⋮----
token = "correct-token-" + "x" * 32
⋮----
def test_x_api_key_fallback_is_accepted(monkeypatch)
⋮----
token = "mobile-token-" + "y" * 32
⋮----
def _request_for_path(path: str, headers: dict[str, str] | None = None) -> Request
⋮----
def test_control_api_middleware_blocks_missing_token(monkeypatch)
⋮----
called = False
⋮----
async def call_next(_request)
⋮----
called = True
⋮----
response = asyncio.run(
⋮----
def test_control_api_middleware_accepts_valid_token(monkeypatch)
⋮----
token = "middleware-token-" + "x" * 32
⋮----
sentinel = object()
⋮----
result = asyncio.run(
⋮----
def test_health_endpoints_bypass_control_api_auth(monkeypatch)
⋮----
def test_multiple_authentication_headers_fail_closed(monkeypatch)
⋮----
token = "ambiguous-token-" + "x" * 32
⋮----
def test_malformed_authorization_does_not_fall_back_to_api_key(monkeypatch)
⋮----
token = "fallback-token-" + "y" * 32
⋮----
def test_symlinked_secret_file_fails_closed(monkeypatch, tmp_path)
⋮----
target = tmp_path / "real-token"
⋮----
link = tmp_path / "api-token"
⋮----
def test_oversized_secret_file_fails_closed(monkeypatch, tmp_path)
⋮----
def test_vault_backed_api_token_is_supported(monkeypatch, tmp_path)
⋮----
token = "vault-token-" + "v" * 32
⋮----
def test_vault_enabled_refuses_legacy_api_token_fallback(monkeypatch, tmp_path)
⋮----
def test_vault_enabled_missing_api_token_fails_closed(monkeypatch, tmp_path)
````

## File: backend/tests/test_autonomy_gate.py
````python
def _risk(*, blocked: bool = False, level: str = "low") -> CampaignRisk
⋮----
def _consensus(*, blocked: bool = False, next_focus: str = "review_surface") -> DecisionConsensus
⋮----
def test_gate_allows_only_clean_safe_state()
⋮----
gate = build_autonomy_gate(
⋮----
def test_gate_fails_closed_on_policy_runtime_budget_and_health()
⋮----
def test_report_focus_always_requires_human_review()
⋮----
def test_autonomy_gate_route_is_exposed()
````

## File: backend/tests/test_browser.py
````python
def _campaign() -> Campaign
⋮----
def test_browser_navigation_fails_closed_outside_scope()
⋮----
flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://example.com")])
⋮----
def test_browser_denied_target_overrides_wildcard_allow()
⋮----
flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://blocked.test.local")])
⋮----
def test_fill_rejects_literal_or_unscoped_secret_reference()
⋮----
def test_browser_is_dry_run_by_default(monkeypatch)
⋮----
flow = BrowserFlowInput(
result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))
⋮----
def test_browser_flow_dedupe_key_is_stable_for_same_campaign_version_and_flow()
⋮----
first = _flow_dedupe_key("c1", 4, flow)
second = _flow_dedupe_key("c1", 4, flow)
⋮----
def test_browser_flow_dedupe_key_changes_with_version_or_flow()
⋮----
first_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/a")])
second_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/b")])
⋮----
def test_browser_artifacts_are_idempotent_per_job(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
campaign = _campaign()
⋮----
result = BrowserExecutionResult(
⋮----
first = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")
second = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")
⋮----
def test_invalid_browser_automation_flag_fails_closed(monkeypatch)
⋮----
def test_browser_automation_flag_accepts_explicit_false_values(monkeypatch)
⋮----
def test_browser_automation_respects_program_disable()
⋮----
def test_browser_automation_rejects_unsafe_campaign_flags(flag)
⋮----
def test_browser_request_methods_are_read_only()
⋮----
def test_browser_surface_observations_are_persistable_shape()
⋮----
def _clear_browser_secret_env(monkeypatch)
⋮----
def _configure_browser_vault(monkeypatch, tmp_path)
⋮----
def test_browser_secret_preserves_legacy_env_when_vault_disabled(monkeypatch)
⋮----
def test_browser_secret_loads_from_vault(monkeypatch, tmp_path)
⋮----
def test_browser_secret_refuses_env_fallback_when_vault_enabled(monkeypatch, tmp_path)
⋮----
def test_browser_secret_missing_in_vault_fails_closed(monkeypatch, tmp_path)
⋮----
def test_browser_secret_invalid_vault_configuration_fails_closed(monkeypatch)
⋮----
def _browser_flow()
⋮----
def _browser_api_backends(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "browser-api.sqlite3")
artifacts = str(tmp_path / "browser-artifacts")
store = Storage(db, artifacts)
jobs = JobQueue(db)
⋮----
job = queue_browser_flow(campaign.id, _browser_flow())
⋮----
persisted = store.get_campaign(campaign.id)
⋮----
requested = [
queued = [
⋮----
def conflict(document, expected_version=None)
⋮----
flow = _browser_flow()
fingerprint = _flow_fingerprint(flow)
request_id = "browser-resume-request"
⋮----
interrupted = Campaign.model_validate(document)
⋮----
existing = jobs.enqueue(
⋮----
retried = queue_browser_flow(campaign.id, flow)
⋮----
def test_browser_pending_intent_is_visible_in_outbox(tmp_path, monkeypatch)
⋮----
pending = Campaign.model_validate(document)
⋮----
snapshot = outbox_snapshot(store.get_campaign(campaign.id)["events"])
````

## File: backend/tests/test_campaign_audit.py
````python
def test_campaign_event_chain_detects_tampering(monkeypatch)
⋮----
events = []
⋮----
tampered = copy.deepcopy(events)
⋮----
result = verify_campaign_event_chain(tampered)
⋮----
def test_campaign_event_chain_detects_reordering(monkeypatch)
⋮----
def test_campaign_event_chain_supports_hmac(monkeypatch)
⋮----
def test_campaign_event_chain_reports_legacy_prefix(monkeypatch)
⋮----
events = [{"type": "legacy", "at": "old"}]
⋮----
result = verify_campaign_event_chain(events)
````

## File: backend/tests/test_campaign_cancel.py
````python
def _setup(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
def test_cancel_campaign_cancels_queued_jobs_but_preserves_running_lease(tmp_path, monkeypatch)
⋮----
jobs = JobQueue(db)
⋮----
running = jobs.enqueue(campaign.id, "report", {"campaign_id": campaign.id}, dedupe_key="running")
claimed = jobs.claim("worker-a")
⋮----
queued = jobs.enqueue(
⋮----
result = cancel_campaign(campaign.id)
⋮----
def test_cancel_campaign_is_idempotent(tmp_path, monkeypatch)
⋮----
first = cancel_campaign(campaign.id)
second = cancel_campaign(campaign.id)
⋮----
events = [
⋮----
def test_worker_refuses_cancelled_campaign(tmp_path, monkeypatch)
⋮----
def test_completed_campaign_cannot_be_cancelled(tmp_path, monkeypatch)
⋮----
def test_running_job_becomes_cancelled_when_worker_observes_cancelled_campaign(tmp_path, monkeypatch)
⋮----
job = jobs.enqueue(
⋮----
# Put the claimed job back into the worker path without allowing a retry loop.
⋮----
final = jobs.get(job["id"])
⋮----
def test_cancelled_campaign_rejects_new_mutations(tmp_path, monkeypatch)
⋮----
candidate = Finding(
````

## File: backend/tests/test_campaign_circuit_breaker.py
````python
def _campaign()
⋮----
def test_circuit_breaker_persists_and_resets(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
campaign = _campaign()
⋮----
opened = record_circuit_open(
graph = ObservationGraph.from_records(store.list_observations(campaign.id))
⋮----
reset = record_circuit_reset(
⋮----
def test_runtime_exhaustion_opens_breaker_and_future_advance_stays_blocked(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
⋮----
first = advance_campaign(
⋮----
breaker = circuit_breaker_state(graph)
⋮----
second = advance_campaign(
⋮----
def test_control_routes_are_exposed()
⋮----
paths = app.openapi()["paths"]
⋮----
def test_control_status_reports_budget_blocker_consistently(tmp_path, monkeypatch)
⋮----
artifacts = str(tmp_path / "artifacts")
⋮----
store = Storage(db, artifacts)
⋮----
job = queue.enqueue(
claimed = queue.claim("fixture-worker")
⋮----
result = campaign_control_status(campaign.id)
⋮----
def test_control_status_exposes_scanner_stability_and_recon_telemetry(tmp_path, monkeypatch)
````

## File: backend/tests/test_campaign_overview.py
````python
def _setup(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
def test_overview_route_is_exposed()
⋮----
def test_overview_aggregates_findings_jobs_validation_and_budget(tmp_path, monkeypatch)
⋮----
result = campaign_overview(campaign.id)
⋮----
def test_overview_resolution_progress_tracks_terminal_findings(tmp_path, monkeypatch)
⋮----
def test_overview_flags_unresolved_findings(tmp_path, monkeypatch)
⋮----
def test_overview_flags_invalid_attack_surface_endpoint(tmp_path, monkeypatch)
⋮----
def test_overview_surfaces_report_integrity_failure_without_exposing_bytes(tmp_path, monkeypatch)
⋮----
artifact = store.put_artifact(campaign.id, "report", b"report", media_type="text/markdown")
metadata = store.get_artifact(campaign.id, artifact["id"])
⋮----
def test_overview_flags_runtime_exhaustion_for_active_campaign(tmp_path, monkeypatch)
⋮----
def test_overview_does_not_flag_runtime_exhaustion_for_terminal_campaign(tmp_path, monkeypatch)
⋮----
def test_overview_flags_campaign_finding_missing_from_graph(tmp_path, monkeypatch)
⋮----
def test_overview_reports_human_review_readiness_after_complete_validation(tmp_path, monkeypatch)
````

## File: backend/tests/test_campaign_review_state.py
````python
def _finding(finding_id: str, status: str = "validation_required")
⋮----
def test_review_state_prioritizes_independent_validation()
⋮----
graph = ObservationGraph()
⋮----
state = build_campaign_review_state([_finding("f1")], graph)
⋮----
def test_review_state_surfaces_human_report_review_when_ready()
⋮----
state = build_campaign_review_state([_finding("f1", "confirmed")], graph)
⋮----
def test_review_state_route_is_exposed()
````

## File: backend/tests/test_campaign_risk.py
````python
def test_campaign_risk_escalates_on_scope_integrity_and_low_coverage()
⋮----
graph = ObservationGraph()
⋮----
risk = build_campaign_risk([], graph, scope_checker=lambda host: host == "example.test")
⋮----
def test_campaign_risk_reflects_high_impact_unvalidated_finding()
⋮----
finding = Finding(
⋮----
risk = build_campaign_risk([finding], graph)
⋮----
def test_campaign_risk_route_is_exposed_and_advisory(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_risk(campaign.id)
````

## File: backend/tests/test_campaign_runtime.py
````python
def test_runtime_status_reports_remaining_budget()
⋮----
now = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
created = (now - timedelta(seconds=90)).isoformat()
⋮----
status = runtime_status(
⋮----
def test_runtime_status_exhausts_exactly_at_limit()
⋮----
created = (now - timedelta(seconds=120)).isoformat()
⋮----
def test_future_timestamp_never_produces_negative_elapsed()
⋮----
created = (now + timedelta(minutes=5)).isoformat()
⋮----
status = runtime_status(created, now=now)
⋮----
def test_runtime_rejects_naive_timestamp()
⋮----
def test_runtime_limit_rejects_unsafe_tiny_values()
````

## File: backend/tests/test_chain_detector.py
````python
def test_complete_validation_chain_is_prioritized()
⋮----
graph = ObservationGraph()
⋮----
chains = detect_chains(graph)
⋮----
def test_chain_detection_is_deterministic_and_bounded()
⋮----
first = detect_chains(graph, limit=2)
second = detect_chains(graph, limit=2)
⋮----
def test_max_depth_truncates_long_provenance_path()
⋮----
chains = detect_chains(graph, max_depth=2)
⋮----
def test_invalid_bounds_fail_closed()
````

## File: backend/tests/test_control_views.py
````python
def _campaign() -> Campaign
⋮----
def _configure(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
store = Storage(db, artifacts)
campaign = _campaign()
⋮----
def test_agent_catalog_exposes_bounded_roles()
⋮----
agents = list_agents()
roles = {item["role"] for item in agents}
⋮----
def test_observation_and_knowledge_views_are_read_only(tmp_path, monkeypatch)
⋮----
before = len(store.list_observations(campaign.id))
⋮----
observations = list_campaign_observations(campaign.id)
knowledge = campaign_knowledge(campaign.id)
⋮----
def test_plan_view_does_not_enqueue_or_persist_decisions(tmp_path, monkeypatch)
⋮----
plan = campaign_plan(campaign.id)
⋮----
def test_plan_view_matches_validation_budget_stop(tmp_path, monkeypatch)
⋮----
jobs = JobQueue()
⋮----
before_observations = len(store.list_observations(campaign.id))
before_jobs = jobs.campaign_job_counts(campaign.id)
````

## File: backend/tests/test_coverage.py
````python
def test_coverage_is_read_only_and_does_not_claim_unknown_completeness()
⋮----
graph = ObservationGraph()
⋮----
result = build_evidence_coverage(graph, scope_checker=lambda _host: True)
⋮----
def test_coverage_counts_scan_and_independent_validation()
⋮----
def test_coverage_route_is_exposed()
⋮----
def test_coverage_guidance_is_advisory_only()
⋮----
guidance = build_coverage_guidance(
⋮----
def test_coverage_guidance_prioritizes_validation_after_scan()
````

## File: backend/tests/test_decision_audit.py
````python
def _decision(seq, previous_hash, *, observation_id=None, action="scan")
⋮----
observation_id = observation_id or f"d{seq}"
metadata = seal_decision_metadata(
⋮----
def test_decision_audit_chain_verifies_and_links()
⋮----
graph = ObservationGraph()
first = _decision(1, None)
⋮----
second = _decision(2, first.metadata["decision_hash"])
⋮----
result = verify_decision_audit_chain(graph)
⋮----
def test_decision_audit_chain_detects_rewrite()
⋮----
tampered = Observation(
⋮----
def test_decision_audit_chain_detects_sequence_gap()
⋮----
def test_decision_audit_chain_preserves_legacy_unsealed_entries()
⋮----
def test_signed_decision_fails_closed_without_key(monkeypatch)
````

## File: backend/tests/test_decision_consensus.py
````python
def test_scope_integrity_blocks_downstream_work()
⋮----
decisions = [
⋮----
result = build_decision_consensus(decisions)
⋮----
def test_near_equal_signals_fail_closed()
⋮----
def test_clear_leader_remains_advisory_but_unblocked()
⋮----
def test_empty_decisions_are_stable_idle_consensus()
⋮----
result = build_decision_consensus([])
⋮----
def test_contradictory_history_is_a_blocking_consensus_signal()
````

## File: backend/tests/test_decision_timeline.py
````python
def _campaign()
⋮----
def _graph()
⋮----
graph = ObservationGraph()
⋮----
def test_decision_timeline_combines_timestamped_planner_and_campaign_events(monkeypatch)
⋮----
graph = _graph()
⋮----
result = build_decision_timeline(_campaign(), graph)
⋮----
def test_decision_timeline_keeps_un_timestamped_legacy_decisions_out_of_merged_timeline(monkeypatch)
⋮----
item = graph._items["decision:1"]
⋮----
def test_decision_timeline_route_is_exposed()
⋮----
def test_decision_timeline_exposes_historical_why_snapshot(monkeypatch)
⋮----
why = result["planner_decisions"][0]["why"]
⋮----
def test_decision_timeline_diffs_successive_why_snapshots(monkeypatch)
⋮----
first = graph._items["decision:1"]
⋮----
second = result["planner_decisions"][1]
⋮----
by_signal = {item["signal"]: item for item in second["signal_diff"]}
⋮----
def test_decision_timeline_builds_deterministic_causal_summary(monkeypatch)
⋮----
summary = result["planner_decisions"][1]["causal_summary"]
⋮----
def _add_decision(graph, seq, action, at)
⋮----
def test_planner_stability_is_high_for_monotonic_progress(monkeypatch)
⋮----
stability = result["planner_stability"]
⋮----
def test_planner_stability_detects_oscillation(monkeypatch)
⋮----
def test_planner_stability_flags_action_after_stop(monkeypatch)
````

## File: backend/tests/test_deployment_config.py
````python
def _compose() -> str
⋮----
def _env_example() -> str
⋮----
def test_compose_declares_backend_and_worker_healthchecks()
⋮----
compose = _compose()
⋮----
def test_compose_keeps_services_hardened()
⋮----
def test_differential_validation_gate_is_disabled_in_example_environment()
⋮----
def test_compose_keeps_state_private_and_shared_only_where_needed()
⋮----
# Control plane, generic worker, dedicated scanner worker, PentAGI creator
# and PentAGI status tracker require private shared state. Frontend is stateless.
⋮----
frontend = compose.split("  frontend:", 1)[1]
⋮----
def test_compose_enforces_resource_and_shutdown_bounds()
````

## File: backend/tests/test_deployment_preflight.py
````python
_ENV_NAMES = (
⋮----
def _clear(monkeypatch)
⋮----
def test_preflight_is_ok_with_optional_pentagi_disabled(monkeypatch)
⋮----
result = build_deployment_preflight({"ok": True})
⋮----
def test_preflight_errors_when_core_dependencies_are_not_ready(monkeypatch)
⋮----
result = build_deployment_preflight({"ok": False})
⋮----
def test_preflight_reports_missing_pentagi_configuration_without_values(monkeypatch)
⋮----
codes = {item["code"] for item in result["issues"]}
⋮----
def test_preflight_warns_when_execution_intent_cannot_be_enforced(monkeypatch)
⋮----
rendered = str(result)
⋮----
def test_preflight_warns_on_orphan_pentagi_flags(monkeypatch)
⋮----
def test_preflight_reports_invalid_boolean_configuration_fail_closed(monkeypatch)
⋮----
def test_preflight_endpoint_uses_dependency_readiness(monkeypatch)
⋮----
result = main.deployment_preflight()
⋮----
def test_production_preflight_requires_digest_pinned_images(monkeypatch)
⋮----
def test_production_preflight_accepts_digest_pinned_images(monkeypatch)
⋮----
digest = "a" * 64
⋮----
def test_production_preflight_rejects_mutable_tags(monkeypatch)
⋮----
def test_preflight_reports_strict_job_provenance_by_default(monkeypatch)
⋮----
def test_preflight_warns_when_legacy_unprovenanced_jobs_are_enabled(monkeypatch)
⋮----
def test_preflight_rejects_invalid_legacy_provenance_boolean(monkeypatch)
````

## File: backend/tests/test_differential_evidence_integration.py
````python
def _finding(fid: str) -> Finding
⋮----
def _campaign(*findings: Finding) -> Campaign
⋮----
def test_validation_worker_persists_sanitized_differential_signal_without_confirming(tmp_path, monkeypatch)
⋮----
finding = _finding("f1")
campaign = _campaign(finding)
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
⋮----
graph = load_observation_graph(store, campaign.id)
validation = graph.by_kind("validation")[0]
⋮----
persisted = Campaign.model_validate(store.get_campaign(campaign.id))
⋮----
event = next(item for item in persisted.events if item.get("type") == "independent_validation_observation")
⋮----
def test_finding_intelligence_surfaces_differential_signal_and_summary(tmp_path, monkeypatch)
⋮----
result = build_finding_intelligence(persisted.findings, graph)
row = result["findings"][0]
⋮----
def test_red_team_decision_prioritizes_strong_signal_inside_existing_review_work()
⋮----
findings = [_finding("f-none"), _finding("f-strong")]
graph = ObservationGraph()
⋮----
decisions = build_red_team_decisions(findings, graph)
strengthen = next(item for item in decisions if item.kind == "strengthen_evidence")
````

## File: backend/tests/test_differential_intelligence.py
````python
def test_differential_signal_classification_is_conservative()
⋮----
def test_graph_signal_aggregation_prefers_strong_and_preserves_provenance()
⋮----
graph = ObservationGraph()
⋮----
signals = build_differential_signals(graph)
signal = signals["f1"]
⋮----
def test_graph_signal_aggregation_defaults_to_none_for_findings_without_differential_metadata()
````

## File: backend/tests/test_distributed_concurrency.py
````python
def _postgres_url()
⋮----
def _redis_url()
⋮----
@pytest.mark.skipif(not _postgres_url(), reason="PostgreSQL integration URL unavailable")
def test_postgres_campaign_cas_detects_concurrent_lost_update(tmp_path)
⋮----
campaign_id = f"cas-{uuid4()}"
store = PostgresStorage(
original = {
⋮----
barrier = threading.Barrier(2)
⋮----
@contextmanager
    def synchronized_connect()
⋮----
connection = psycopg.connect(
⋮----
class BarrierConnection(_PostgresCompatConnection)
⋮----
def execute(self, statement, params=())
⋮----
cursor = super().execute(statement, params)
⋮----
outcomes = []
lock = threading.Lock()
⋮----
def write(state)
⋮----
document = {
⋮----
version = store.save_campaign(document, expected_version=1)
result = ("ok", version)
⋮----
result = ("conflict", None)
⋮----
threads = [
⋮----
@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_dedupe_is_atomic_under_concurrent_enqueue(monkeypatch)
⋮----
prefix = f"xbow:test:{uuid4().hex}"
⋮----
queue = RedisJobQueue(_redis_url())
campaign_id = f"campaign-{uuid4()}"
barrier = threading.Barrier(8)
job_ids = []
errors = []
⋮----
def enqueue()
⋮----
job = queue.enqueue(
⋮----
threads = [threading.Thread(target=enqueue) for _ in range(8)]
⋮----
keys = list(queue.redis.scan_iter(f"{prefix}:*"))
⋮----
@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_campaign_planner_lock_has_single_concurrent_owner(monkeypatch)
⋮----
release = threading.Event()
owners = []
contenders = []
⋮----
def compete()
⋮----
threads = [threading.Thread(target=compete, name=f"planner-{i}") for i in range(8)]
⋮----
def test_planner_lock_configuration_fails_closed(monkeypatch, tmp_path)
⋮----
queue = JobQueue(str(tmp_path / "queue.sqlite3"))
⋮----
# Local SQLite mode does not depend on the distributed lease configuration.
⋮----
@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_planner_lock_rejects_invalid_lease(monkeypatch)
⋮----
@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_totp_replay_is_atomic_across_concurrent_consumers(monkeypatch)
⋮----
secret = base64.b32encode(uuid4().bytes).decode("ascii")
⋮----
code = _totp(configured_totp_secret(), 1)
⋮----
results = []
⋮----
def consume()
⋮----
accepted = consume_totp_code(code, now=30.0)
⋮----
threads = [threading.Thread(target=consume) for _ in range(8)]
⋮----
@pytest.mark.skipif(not _postgres_url(), reason="PostgreSQL integration URL unavailable")
def test_postgres_cas_stress_has_exactly_one_winner(tmp_path)
⋮----
campaign_id = f"stress-cas-{uuid4()}"
⋮----
contenders = 16
barrier = threading.Barrier(contenders)
original_connect = store.connect
⋮----
class BarrierConnection
⋮----
cursor = base.execute(statement, params)
⋮----
def write(index)
⋮----
@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_claim_stress_has_no_duplicate_or_lost_jobs(monkeypatch)
⋮----
prefix = f"xbow:stress:{uuid4().hex}"
⋮----
workers = 32
⋮----
created_ids = []
⋮----
barrier = threading.Barrier(workers)
claimed = []
⋮----
def claim(index)
⋮----
job = queue.claim(f"worker-{index}")
⋮----
claimed_ids = [job["id"] for job in claimed]
⋮----
stats = queue.stats()
⋮----
def test_sqlite_cas_stress_has_exactly_one_winner_and_preserves_event(tmp_path)
⋮----
store = Storage(
campaign_id = f"sqlite-stress-{uuid4()}"
⋮----
result = ("ok", version, index)
⋮----
result = ("conflict", None, index)
⋮----
winners = [
````

## File: backend/tests/test_domain_incident_lifecycle.py
````python
T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def incident(domain, fingerprint, severity="degraded")
⋮----
def snapshot(**domains)
⋮----
values = {"workload": None, "control_plane": None, "observability": None}
⋮----
def test_multiple_domains_can_be_active_simultaneously()
⋮----
history = apply_domain_incidents(
active = active_incidents_by_domain(history)
⋮----
def test_recovery_of_one_domain_does_not_resolve_another()
⋮----
def test_changed_fingerprint_rotates_only_its_domain()
⋮----
def test_repeated_domain_fingerprint_is_deduplicated()
````

## File: backend/tests/test_domain_lifecycle_integration.py
````python
def telemetry()
⋮----
def metrics(watchdog="ok", failed=0)
⋮----
def test_observer_persists_independent_domain_incidents(tmp_path, monkeypatch)
⋮----
store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
⋮----
status = read_incident_status(store)
⋮----
def test_domain_recovery_does_not_close_other_active_incident(tmp_path, monkeypatch)
````

## File: backend/tests/test_dr_cli.py
````python
def test_manifest_cli_refuses_output_collision(monkeypatch, tmp_path, capsys)
⋮----
postgres = tmp_path / "postgres.dump"
redis = tmp_path / "dump.rdb"
vault = tmp_path / "secrets.vault.json"
⋮----
output = capsys.readouterr().out
````

## File: backend/tests/test_dr_manifest.py
````python
def _files(tmp_path)
⋮----
postgres = tmp_path / "postgres.dump"
redis = tmp_path / "dump.rdb"
vault = tmp_path / "secrets.vault.json"
⋮----
def _canonical_legacy_v1(manifest)
⋮----
payload = {
⋮----
def test_backup_manifest_contains_only_integrity_metadata(tmp_path)
⋮----
manifest = build_backup_manifest(
⋮----
rendered = str(manifest)
⋮----
def test_manifest_roundtrip_verifies(tmp_path)
⋮----
manifest_path = tmp_path / "manifest.json"
⋮----
result = verify_backup_manifest(
⋮----
def test_manifest_detects_modified_backup(tmp_path)
⋮----
def test_manifest_rejects_symlink_backup(tmp_path)
⋮----
symlink = tmp_path / "postgres-link.dump"
⋮----
def test_manifest_rejects_empty_backup(tmp_path)
⋮----
def test_manifest_rejects_symlink_destination(tmp_path)
⋮----
real = tmp_path / "real.json"
⋮----
link = tmp_path / "manifest.json"
⋮----
def test_manifest_rejects_invalid_artifact_size_schema(tmp_path)
⋮----
def test_signed_manifest_detects_manifest_rewrite(tmp_path, monkeypatch)
⋮----
saved = json.loads(manifest_path.read_text(encoding="utf-8"))
⋮----
def test_signed_manifest_rejects_signature_field_stripping(tmp_path, monkeypatch)
⋮----
def test_signed_manifest_authenticates_integrity_mode(tmp_path, monkeypatch)
⋮----
def test_signed_manifest_requires_matching_verification_key(tmp_path, monkeypatch)
⋮----
def test_unsigned_manifest_remains_backward_compatible(tmp_path, monkeypatch)
⋮----
def test_legacy_signed_v1_manifest_remains_backward_compatible(tmp_path, monkeypatch)
⋮----
def test_legacy_v1_rejects_partial_signature_stripping(tmp_path, monkeypatch)
⋮----
def test_signed_manifest_fails_closed_when_key_becomes_unavailable(tmp_path, monkeypatch)
````

## File: backend/tests/test_error_budget.py
````python
def telemetry(short_rate, long_rate, short_events=100, long_events=1000)
⋮----
def test_error_budget_is_healthy_with_low_failure_rates(monkeypatch)
⋮----
result = build_error_budget_status(telemetry(0.001, 0.002))
⋮----
def test_fast_multiwindow_burn_is_critical(monkeypatch)
⋮----
result = build_error_budget_status(telemetry(0.15, 0.07))
⋮----
def test_elevated_multiwindow_burn_is_degraded(monkeypatch)
⋮----
result = build_error_budget_status(telemetry(0.07, 0.04))
⋮----
def test_low_sample_volume_does_not_page(monkeypatch)
⋮----
result = build_error_budget_status(
⋮----
def test_invalid_success_target_fails_closed(monkeypatch)
````

## File: backend/tests/test_evidence_backed_planner.py
````python
def _campaign(status="validation_required")
⋮----
def _observed_graph(*, with_evidence: bool) -> ObservationGraph
⋮----
graph = ObservationGraph()
⋮----
def test_planner_fails_closed_when_observed_validation_lacks_attached_evidence()
⋮----
action = AdaptivePlanner().plan(_campaign(), _observed_graph(with_evidence=False))[0]
⋮----
def test_planner_allows_resolution_gate_after_evidence_backed_validation()
⋮----
action = AdaptivePlanner().plan(_campaign(), _observed_graph(with_evidence=True))[0]
⋮----
def test_planner_allows_report_phase_only_after_evidence_backed_resolution()
⋮----
action = AdaptivePlanner().plan(
````

## File: backend/tests/test_evidence_chain.py
````python
def test_incomplete_chain_reports_missing_support()
⋮----
graph = ObservationGraph()
⋮----
chains = build_evidence_chains(graph)
⋮----
chain = chains[0]
⋮----
def test_complete_chain_correlates_ancestors_validation_and_evidence()
⋮----
chain = build_evidence_chains(graph)[0]
⋮----
def test_self_validation_keeps_chain_incomplete()
⋮----
def test_dangling_parent_reference_is_reported_for_corrupted_graph_fixture()
⋮----
def test_ancestry_cycle_is_detected_for_corrupted_graph_fixture()
⋮----
def test_evidence_chain_route_is_exposed_and_read_only(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_evidence_chains(campaign.id)
````

## File: backend/tests/test_evidence_quality.py
````python
def _base_graph() -> ObservationGraph
⋮----
graph = ObservationGraph()
⋮----
def test_unvalidated_finding_has_low_evidence_quality()
⋮----
item = build_evidence_quality(_base_graph())[0]
⋮----
def test_independent_artifact_backed_multi_source_evidence_is_high_quality()
⋮----
graph = _base_graph()
⋮----
item = build_evidence_quality(graph)[0]
⋮----
def test_plain_linked_evidence_does_not_receive_artifact_credit()
⋮----
def test_corrupt_chain_loses_integrity_credit()
⋮----
def test_evidence_quality_route_is_exposed(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_evidence_quality(campaign.id)
⋮----
def test_artifact_reference_without_sha256_is_not_high_grade()
````

## File: backend/tests/test_finding_cluster_consensus.py
````python
def _finding(fid: str, endpoint: str)
⋮----
def _graph_for(ids)
⋮----
graph = ObservationGraph()
⋮----
def test_cluster_consensus_ready_only_when_all_members_are_ready()
⋮----
findings = [
snapshots = [
⋮----
result = build_cluster_consensus(
⋮----
cluster = result[0]
⋮----
def test_cluster_consensus_does_not_promote_mixed_cluster()
⋮----
graph = _graph_for(["f1", "f2"])
# Remove support for f2 so the cluster is intentionally mixed.
⋮----
cluster = build_cluster_consensus(
⋮----
def test_cluster_consensus_blocks_on_any_contradictory_member()
⋮----
def test_cluster_consensus_route_is_exposed()
````

## File: backend/tests/test_finding_cluster_saturation.py
````python
def _finding(fid: str, endpoint: str)
⋮----
def _base_graph()
⋮----
graph = ObservationGraph()
⋮----
def test_cluster_saturation_reports_strong_representative_and_saved_validations()
⋮----
findings = [
graph = _base_graph()
⋮----
item = build_cluster_saturation(findings, graph)[0]
⋮----
def test_cluster_saturation_explains_missing_quality_requirements()
⋮----
def test_cluster_saturation_route_is_exposed()
````

## File: backend/tests/test_finding_consensus.py
````python
def _graph() -> ObservationGraph
⋮----
graph = ObservationGraph()
⋮----
def test_single_source_finding_is_not_corroborated()
⋮----
result = build_finding_consensus(_graph())
⋮----
def test_independent_validation_and_evidence_raise_consensus()
⋮----
graph = _graph()
⋮----
result = build_finding_consensus(graph)[0]
⋮----
def test_observed_validation_without_evidence_has_no_consensus()
⋮----
def test_two_evidence_backed_validators_form_quorum()
⋮----
def test_self_validation_does_not_count_as_independent_consensus()
⋮----
def test_finding_consensus_route_is_exposed()
````

## File: backend/tests/test_finding_correlation.py
````python
def _finding(finding_id: str, endpoint: str, *, severity: str = "medium")
⋮----
def test_correlates_canonical_duplicate_findings_without_query_values()
⋮----
findings = [
⋮----
groups = correlate_findings(findings)
⋮----
group = groups[0]
⋮----
def test_different_cwe_or_endpoint_stays_separate()
⋮----
first = _finding("f1", "https://example.test/a")
second = _finding("f2", "https://example.test/b")
⋮----
groups = correlate_findings([first, second])
⋮----
def test_correlation_route_is_exposed_and_does_not_auto_merge(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_finding_correlations(campaign.id)
⋮----
def test_similarity_scores_same_asset_endpoint_and_cwe_highly()
⋮----
left = _finding("f1", "https://example.test/a?id=one")
right = _finding("f2", "https://EXAMPLE.TEST:443/a?id=two")
⋮----
similarity = score_finding_similarity(left, right)
⋮----
def test_similarity_caps_cross_asset_generic_matches()
⋮----
left = _finding("f1", "https://example.test/a")
right = _finding("f2", "https://other.test/a")
⋮----
def test_cluster_findings_groups_high_confidence_pairs_without_merging()
⋮----
first = _finding("f1", "https://example.test/a?id=1")
second = _finding("f2", "https://example.test/a?id=2")
third = _finding("f3", "https://example.test/b")
⋮----
def test_cluster_threshold_fails_closed()
⋮----
findings = [_finding("f1", "https://example.test/a")]
⋮----
def test_cluster_route_is_exposed(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "clusters.sqlite3")
⋮----
result = campaign_finding_clusters(campaign.id)
````

## File: backend/tests/test_finding_intelligence.py
````python
def _finding(fid: str, endpoint: str, severity: str = "high")
⋮----
def _graph()
⋮----
graph = ObservationGraph()
⋮----
def test_finding_intelligence_consolidates_member_and_cluster_views()
⋮----
findings = [
snapshots = [
⋮----
result = build_finding_intelligence(
⋮----
by_id = {item["finding_id"]: item for item in result["findings"]}
⋮----
def test_finding_intelligence_summary_reflects_cluster_saturation()
⋮----
result = build_finding_intelligence(findings, _graph())
⋮----
cluster = result["clusters"][0]
⋮----
def test_finding_intelligence_does_not_expose_query_values()
⋮----
serialized = str(result)
⋮----
def test_finding_intelligence_route_is_exposed()
````

## File: backend/tests/test_finding_lifecycle.py
````python
def _finding(finding_id: str, status: str)
⋮----
def test_candidate_recommends_validation_without_execution_authority()
⋮----
item = build_finding_lifecycle([_finding("f1", "candidate")], ObservationGraph())[0]
⋮----
def test_validation_required_blocks_until_independent_complete_evidence()
⋮----
graph = ObservationGraph()
⋮----
item = build_finding_lifecycle([_finding("f1", "validation_required")], graph)[0]
⋮----
def test_confirmed_finding_with_complete_chain_is_ready_for_human_report_review()
⋮----
item = build_finding_lifecycle([_finding("f1", "confirmed")], graph)[0]
⋮----
def test_rejected_finding_is_terminal()
⋮----
item = build_finding_lifecycle([_finding("f1", "rejected")], ObservationGraph())[0]
⋮----
def test_finding_lifecycle_route_is_exposed()
````

## File: backend/tests/test_finding_readiness.py
````python
def _finding(finding_id="f1", severity="high")
⋮----
def _strong_graph()
⋮----
graph = ObservationGraph()
⋮----
def test_readiness_requires_validation_for_weak_evidence()
⋮----
item = build_finding_readiness([_finding()], graph)[0]
⋮----
def test_readiness_can_be_report_review_ready_with_strong_independent_evidence()
⋮----
snapshots = [
⋮----
item = build_finding_readiness(
⋮----
def test_contradictory_history_blocks_readiness_even_with_strong_evidence()
⋮----
def test_readiness_route_is_exposed()
````

## File: backend/tests/test_finding_triage.py
````python
def _finding(finding_id: str, severity: str, *, endpoint: str | None = None, cwe: str | None = None)
⋮----
def test_triage_prioritizes_critical_unvalidated_finding()
⋮----
findings = [
graph = ObservationGraph()
⋮----
triage = build_finding_triage(findings, graph)
⋮----
def test_triage_marks_duplicate_candidates_without_merging()
⋮----
endpoint = "https://example.test/api?id=secret"
⋮----
def test_triage_resolves_only_terminal_finding_with_complete_chain()
⋮----
finding = _finding("f1", "high")
⋮----
triage = build_finding_triage([finding], graph)
⋮----
def test_finding_triage_route_is_exposed(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_finding_triage(campaign.id)
⋮----
def test_triage_requires_high_quality_evidence_before_report_review()
⋮----
finding = _finding("quality", "high")
⋮----
triage = build_finding_triage([finding], graph)[0]
⋮----
def test_triage_allows_report_review_with_high_quality_artifact_backed_evidence()
⋮----
finding = _finding("quality-high", "high")
````

## File: backend/tests/test_form_waf_reasoning.py
````python
def _graph() -> ObservationGraph
⋮----
graph = ObservationGraph()
⋮----
def test_forms_and_wafs_generate_safe_bounded_hypotheses()
⋮----
hypotheses = build_hypotheses(_graph())
by_kind = {item.kind: item for item in hypotheses}
⋮----
def test_review_queue_prioritizes_form_and_protection_context()
⋮----
tasks = build_review_queue(_graph())
kinds = {item.kind for item in tasks}
⋮----
def test_coverage_requires_recorded_form_and_waf_review_evidence()
⋮----
graph = _graph()
before = build_red_team_coverage(graph)
⋮----
after = build_red_team_coverage(graph)
````

## File: backend/tests/test_frontend_policy_launcher.py
````python
ROOT = Path(__file__).resolve().parents[2]
⋮----
def test_hackerone_single_mutation_launch_route_exists()
⋮----
schema = app.openapi()
⋮----
def test_frontend_requires_authorization_and_scope_review_before_launch()
⋮----
html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")
⋮----
required_ids = (
````

## File: backend/tests/test_hackerone_binding.py
````python
def _admission_payload()
⋮----
def _admitted_campaign(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "campaigns.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
admitted = admit_hackerone_campaign(_admission_payload())
⋮----
def test_hackerone_start_rejects_policy_drift_before_enqueue(tmp_path, monkeypatch)
⋮----
queue_db = str(tmp_path / "jobs.sqlite3")
⋮----
campaign_id = admitted["campaign"]["id"]
⋮----
store = Storage(db, artifacts)
⋮----
jobs = JobQueue(queue_db)
⋮----
def test_hackerone_binding_is_embedded_in_job_provenance(tmp_path, monkeypatch)
⋮----
payload = attach_job_provenance(
⋮----
def test_hackerone_provenance_rejects_binding_substitution(tmp_path, monkeypatch)
⋮----
job = {
⋮----
verification = verify_job_provenance(job, campaign)
⋮----
def test_hackerone_conservative_dry_run_queues_one_verified_nuclei_job(tmp_path, monkeypatch)
⋮----
start_result = main.start_campaign(campaign_id)
⋮----
persisted = Storage(db, artifacts).get_campaign(campaign_id)
⋮----
started = main.Campaign.model_validate(persisted)
⋮----
started_events = [event for event in started.events if event.get("type") == "campaign_started"]
⋮----
job = jobs.get(started_events[0]["job_id"])
⋮----
verification = verify_job_provenance(job, started)
⋮----
def test_non_hackerone_start_keeps_strix_routing(tmp_path, monkeypatch)
⋮----
campaign = main.Campaign(
⋮----
start_result = main.start_campaign(campaign.id)
⋮----
provenance = start_result["job"]["payload"]["_provenance"]
````

## File: backend/tests/test_hackerone_launch_api.py
````python
def _resource(identifier: str, eligible: bool = True)
⋮----
def _payload()
⋮----
def test_hackerone_launch_creates_bound_running_campaign(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "launch.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
api = FastAPI()
⋮----
response = TestClient(api).post(
⋮----
result = response.json()
⋮----
persisted = Storage(db, artifacts).get_campaign(result["campaign"]["id"])
⋮----
event_types = [event.get("type") for event in persisted["events"]]
````

## File: backend/tests/test_hackerone_scope_preview_api.py
````python
def _resource(identifier: str, asset_type: str, eligible: bool)
⋮----
def _policy_values(**overrides)
⋮----
values = {
⋮----
def _policy_input(**overrides)
⋮----
def test_hackerone_scope_preview_api_is_non_persisting()
⋮----
result = preview_hackerone_scope(
⋮----
def test_hackerone_scope_preview_api_surfaces_unsupported_without_converting()
⋮----
def test_hackerone_scope_preview_api_rejects_partial_page()
⋮----
def test_hackerone_scope_preview_route_is_in_authenticated_api_namespace()
⋮----
schema = app.openapi()
⋮----
def test_hackerone_scope_preview_input_requires_document()
⋮----
def test_hackerone_rules_preview_requires_explicit_policy_and_does_not_persist()
⋮----
payload = HackerOneRulesPreviewInput(
⋮----
result = preview_hackerone_rules(payload)
⋮----
@pytest.mark.parametrize("missing", ["automated_scanning", "max_requests_per_second"])
def test_hackerone_rules_preview_has_no_automation_or_rate_defaults(missing)
⋮----
policy = _policy_values()
⋮----
def test_hackerone_policy_requires_review_metadata_before_rules_preview(missing)
⋮----
def test_hackerone_policy_rejects_naive_review_timestamp()
⋮----
def test_hackerone_policy_rejects_implicit_boolean_request_rate()
⋮----
def test_hackerone_rules_preview_rejects_unsupported_scope_fail_closed()
⋮----
def test_hackerone_rules_preview_route_is_in_authenticated_api_namespace()
⋮----
def test_hackerone_conservative_campaign_admission_route_exists()
⋮----
def test_hackerone_conservative_admission_persists_policy_binding(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "hackerone.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
api = FastAPI()
⋮----
client = TestClient(api)
response = client.post(
⋮----
result = response.json()
⋮----
persisted = Storage(db, artifacts).get_campaign(result["campaign"]["id"])
⋮----
bound = [event for event in persisted["events"] if event.get("type") == "hackerone_policy_bound"]
⋮----
db = str(tmp_path / "blocked.sqlite3")
⋮----
admission_policy = {
````

## File: backend/tests/test_health.py
````python
class HealthyQueue
⋮----
def health(self)
⋮----
class UnhealthyQueue
⋮----
class BrokenQueue
⋮----
def test_live_is_dependency_independent()
⋮----
result = main.live()
⋮----
def test_ready_reports_status_without_dependency_details(monkeypatch)
⋮----
result = main.ready()
⋮----
def test_ready_returns_503_when_dependency_unhealthy(monkeypatch)
⋮----
def test_health_reports_status_without_database_details(monkeypatch)
⋮----
result = main.health()
⋮----
def test_health_returns_503_when_database_unhealthy(monkeypatch)
⋮----
def test_health_returns_503_when_database_probe_raises(monkeypatch)
````

## File: backend/tests/test_hypothesis_engine.py
````python
def test_hypotheses_are_bounded_and_deterministic()
⋮----
graph = ObservationGraph()
⋮----
first = build_hypotheses(graph, limit=2)
second = build_hypotheses(graph, limit=2)
⋮----
def test_hypothesis_redacts_query_values_and_keeps_parameter_names()
⋮----
hypotheses = build_hypotheses(graph)
payload = [item.to_dict() for item in hypotheses]
⋮----
def test_scope_checker_filters_out_of_scope_lineage()
⋮----
hypotheses = build_hypotheses(
⋮----
def test_unvalidated_finding_gets_high_priority_validation_gap()
⋮----
def test_observed_independent_validation_closes_validation_gap()
⋮----
def test_self_validation_does_not_close_validation_gap()
⋮----
def test_hypothesis_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_hypotheses(campaign.id)
⋮----
def test_limit_fails_closed_outside_bounds()
````

## File: backend/tests/test_hypothesis_memory.py
````python
def _graph()
⋮----
graph = ObservationGraph()
⋮----
def test_hypothesis_starts_unvalidated()
⋮----
hypotheses = build_hypotheses(_graph())
⋮----
item = hypotheses[0]
⋮----
def test_hypothesis_becomes_partially_supported_after_independent_validation()
⋮----
graph = _graph()
⋮----
item = build_hypotheses(graph)[0]
⋮----
def test_hypothesis_requires_observed_validation_and_evidence_for_support()
⋮----
partial = build_hypotheses(graph)[0]
⋮----
supported = build_hypotheses(graph)[0]
⋮----
def test_self_validation_never_supports_hypothesis()
⋮----
def test_hypothesis_snapshot_becomes_stale_when_graph_changes()
⋮----
def test_hypothesis_fingerprint_ignores_planner_decision_memory()
⋮----
def test_hypothesis_fingerprint_ignores_unrelated_evidence()
⋮----
def test_hypothesis_delta_explains_confidence_status_and_evidence_changes()
⋮----
previous = {
current = {
⋮----
delta = diff_hypothesis_snapshots(previous, current)
⋮----
change = delta["changes"][0]
⋮----
def test_hypothesis_delta_tracks_added_and_removed_findings()
⋮----
changes = {
⋮----
def test_hypothesis_delta_is_empty_for_equivalent_snapshots()
⋮----
snapshot = {
⋮----
delta = diff_hypothesis_snapshots(snapshot, snapshot)
⋮----
def test_stability_marks_single_snapshot_as_fresh()
⋮----
snapshots = [
⋮----
item = summarize_hypothesis_stability(snapshots)[0]
⋮----
def test_stability_marks_three_identical_snapshots_as_stable()
⋮----
def test_stability_detects_confidence_reversal_as_contradictory()
````

## File: backend/tests/test_incident_api.py
````python
def seeded_store(tmp_path)
⋮----
store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
⋮----
def test_read_contract_exposes_active_history_and_version(tmp_path)
⋮----
result = read_incident_status(seeded_store(tmp_path))
⋮----
def test_acknowledge_requires_current_version(tmp_path)
⋮----
store = seeded_store(tmp_path)
⋮----
result = acknowledge_incident_versioned(store, "abc", expected_version=version)
⋮----
def test_stale_acknowledgement_is_conflict(tmp_path)
⋮----
def test_unknown_or_non_open_incident_is_noop(tmp_path)
⋮----
result = acknowledge_incident_versioned(store, "missing", expected_version=version)
````

## File: backend/tests/test_incident_domains.py
````python
def test_domains_are_independent()
⋮----
result = build_domain_incidents(
⋮----
def test_healthy_domain_has_no_incident()
⋮----
def test_same_signals_in_different_domains_have_distinct_fingerprints()
⋮----
def test_output_is_redacted()
````

## File: backend/tests/test_incident_engine.py
````python
def test_healthy_sources_produce_no_incident()
⋮----
result = build_incident_snapshot(
⋮----
def test_degraded_source_produces_degraded_incident()
⋮----
def test_critical_source_dominates()
⋮----
def test_fingerprint_is_deterministic_and_redacted()
⋮----
a = build_incident_snapshot(
b = build_incident_snapshot(
⋮----
def test_incident_engine_never_enables_recovery_or_retry()
````

## File: backend/tests/test_incident_http_api.py
````python
TOKEN = "t" * 32
⋮----
def client(monkeypatch, tmp_path)
⋮----
db_path = str(tmp_path / "incidents.sqlite3")
⋮----
class Store
⋮----
def __init__(self)
⋮----
def auth()
⋮----
def test_incident_read_requires_authentication(monkeypatch, tmp_path)
⋮----
response = client(monkeypatch, tmp_path).get("/api/incidents")
⋮----
def test_incident_read_returns_versioned_state(monkeypatch, tmp_path)
⋮----
response = client(monkeypatch, tmp_path).get("/api/incidents", headers=auth())
⋮----
payload = response.json()
⋮----
def test_acknowledge_unknown_incident_is_safe_noop(monkeypatch, tmp_path)
⋮----
c = client(monkeypatch, tmp_path)
current = c.get("/api/incidents", headers=auth()).json()
response = c.post(
⋮----
def test_acknowledge_rejects_stale_version(monkeypatch, tmp_path)
⋮----
store = main.incident_store()
````

## File: backend/tests/test_incident_lifecycle.py
````python
T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def snap(fingerprint="abc", severity="degraded")
⋮----
def test_opens_and_deduplicates_same_incident()
⋮----
history = apply_incident_snapshot([], snap(), now=T0)
history = apply_incident_snapshot(history, snap(), now=T0 + timedelta(minutes=1))
⋮----
def test_acknowledges_open_incident()
⋮----
history = acknowledge_incident(history, "abc", now=T0 + timedelta(minutes=2))
⋮----
def test_healthy_snapshot_resolves_active_incident()
⋮----
history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(minutes=3))
⋮----
def test_new_fingerprint_resolves_previous_and_opens_new()
⋮----
history = apply_incident_snapshot([], snap("one"), now=T0)
history = apply_incident_snapshot(history, snap("two", "critical"), now=T0 + timedelta(minutes=1))
⋮----
def test_reliability_stats_compute_mttr_and_mtbf()
⋮----
history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(seconds=30))
history = apply_incident_snapshot(history, snap("two"), now=T0 + timedelta(seconds=120))
history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(seconds=180))
stats = incident_reliability_stats(history)
````

## File: backend/tests/test_incident_observer.py
````python
def healthy_metrics()
⋮----
def healthy_telemetry()
⋮----
def test_healthy_observation_does_not_create_incident(tmp_path)
⋮----
store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
result = observe_incidents(store, healthy_metrics(), healthy_telemetry())
⋮----
def test_critical_watchdog_opens_incident(tmp_path)
⋮----
metrics = healthy_metrics()
⋮----
result = observe_incidents(store, metrics, healthy_telemetry())
⋮----
def test_repeated_identical_incident_is_deduplicated(tmp_path)
⋮----
def test_healthy_observation_resolves_active_incident(tmp_path)
````

## File: backend/tests/test_incident_store_fencing.py
````python
def test_current_leader_can_commit(tmp_path)
⋮----
path = str(tmp_path / "shared.sqlite3")
lease = ObserverLease(path)
store = IncidentStore(path)
generation = lease.acquire("leader", ttl_seconds=90)
⋮----
new_version = store.write(
⋮----
def test_stale_leader_cannot_commit_after_failover(tmp_path)
⋮----
now = datetime.now(timezone.utc)
old_generation = lease.acquire("old", ttl_seconds=10, now=now)
new_generation = lease.acquire("new", ttl_seconds=10, now=now + timedelta(seconds=11))
⋮----
def test_incomplete_fence_fails_closed(tmp_path)
````

## File: backend/tests/test_incident_store.py
````python
def test_incident_store_round_trip(tmp_path)
⋮----
store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
⋮----
new_version = store.write([{"fingerprint": "abc", "status": "opened"}], expected_version=version)
⋮----
def test_incident_store_rejects_stale_version(tmp_path)
⋮----
def test_incident_store_instances_share_state(tmp_path)
⋮----
path = str(tmp_path / "incidents.sqlite3")
first = IncidentStore(path)
second = IncidentStore(path)
````

## File: backend/tests/test_job_provenance_api_integration.py
````python
def _campaign(*, findings=None)
⋮----
def _runtime(tmp_path, monkeypatch, *, campaign=None)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
jobs = JobQueue(db)
campaign = campaign or _campaign()
⋮----
def _assert_bound(job, campaign, expected_kind)
⋮----
def test_campaign_start_direct_enqueue_is_provenanced(tmp_path, monkeypatch)
⋮----
result = main.start_campaign(campaign.id)
latest = main.assert_campaign_exists(campaign.id)
⋮----
def test_add_finding_direct_validation_enqueue_is_provenanced(tmp_path, monkeypatch)
⋮----
finding = Finding(
⋮----
job = jobs.get_by_dedupe(campaign.id, "independent_validation", "validation:f1")
⋮----
def test_manual_report_direct_enqueue_is_provenanced(tmp_path, monkeypatch)
⋮----
job = main.queue_report(campaign.id, platform="generic")
⋮----
def test_completion_report_direct_enqueue_is_provenanced(tmp_path, monkeypatch)
⋮----
job = jobs.get_by_dedupe(campaign.id, "report", "report:generic:completed")
⋮----
def test_resolution_rejects_observed_validation_without_attached_evidence(tmp_path, monkeypatch)
⋮----
def test_resolution_accepts_evidence_backed_independent_validation(tmp_path, monkeypatch)
⋮----
result = main.validate_finding(campaign.id, "f1", confirmed=True, validator="validator")
report_job = jobs.get_by_dedupe(campaign.id, "report", "report:generic:completed")
````

## File: backend/tests/test_job_provenance_integration.py
````python
def _campaign(*, findings=None)
⋮----
def _assert_bound(job, campaign, expected_kind)
⋮----
provenance = job["payload"]["_provenance"]
⋮----
def test_sanitized_scan_payload_is_policy_bound()
⋮----
campaign = _campaign()
receipt = policy_receipt(campaign, "example.test", "automated_scan")
⋮----
payload = sanitized_scan_payload(campaign, receipt)
⋮----
def test_orchestrator_scan_jobs_bind_each_engine_kind(tmp_path)
⋮----
queue = JobQueue(str(tmp_path / "queue.sqlite3"))
⋮----
graph = ObservationGraph()
⋮----
jobs = _enqueue_action(
⋮----
by_kind = {job["kind"]: job for job in jobs}
⋮----
def test_orchestrator_recon_and_browser_jobs_are_policy_bound(tmp_path)
⋮----
tasks = [
⋮----
jobs = _enqueue_recon_tasks(campaign, graph, queue, tasks)
⋮----
def test_orchestrator_validation_and_report_jobs_are_policy_bound(tmp_path)
⋮----
finding = Finding(
campaign = _campaign(findings=[finding])
⋮----
validation_jobs = _enqueue_action(
report_jobs = _enqueue_action(
````

## File: backend/tests/test_job_provenance.py
````python
def _campaign(*, allowed_targets=None, rps=2.0)
⋮----
def test_policy_fingerprint_is_deterministic_and_order_stable()
⋮----
first = _campaign(allowed_targets=["example.test", "*.example.test"])
second = _campaign(allowed_targets=["*.example.test", "example.test"])
⋮----
def test_policy_fingerprint_changes_when_governance_changes()
⋮----
base = _campaign(rps=2.0)
changed = _campaign(rps=1.0)
⋮----
def test_attached_provenance_verifies_against_current_campaign()
⋮----
campaign = _campaign()
payload = attach_job_provenance(
job = {
⋮----
verification = verify_job_provenance(job, campaign)
⋮----
def test_stale_policy_fingerprint_fails_closed()
⋮----
campaign = _campaign(rps=2.0)
⋮----
stale_job = {
⋮----
verification = verify_job_provenance(stale_job, campaign)
⋮----
def test_wrong_job_kind_is_rejected()
⋮----
provenance = build_job_provenance(
⋮----
def test_missing_provenance_is_rejected_by_strict_verifier()
⋮----
def test_duplicate_provenance_injection_is_rejected()
⋮----
def test_governed_job_registry_is_explicit_and_closed()
⋮----
def test_job_provenance_status_route_is_registered()
⋮----
def test_job_provenance_status_is_redacted(monkeypatch)
⋮----
class FakeQueue
⋮----
def get(self, job_id)
⋮----
result = main.get_job_provenance_status("job-1")
⋮----
rendered = str(result)
⋮----
def test_capabilities_advertise_policy_bound_job_provenance()
````

## File: backend/tests/test_jobqueue.py
````python
def test_queue_claim_and_complete(tmp_path)
⋮----
q = JobQueue(str(tmp_path / "q.sqlite3"))
created = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
⋮----
claimed = q.claim("worker-a")
⋮----
done = q.finish(created["id"], "worker-a", True)
⋮----
def test_failure_requeues_then_fails(tmp_path)
⋮----
job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=2)
⋮----
requeued = q.finish(job["id"], "worker-a", False, "transient")
⋮----
failed = q.finish(job["id"], "worker-b", False, "still broken")
⋮----
def test_expired_lease_requeues_abandoned_job(tmp_path, monkeypatch)
⋮----
job = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"}, max_attempts=2)
claimed = q.claim("dead-worker")
⋮----
recovered = q.claim("replacement-worker")
⋮----
def test_expired_lease_fails_when_retry_budget_exhausted(tmp_path, monkeypatch)
⋮----
job = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"}, max_attempts=1)
⋮----
failed = q.get(job["id"])
⋮----
def test_invalid_lease_configuration_fails_closed(tmp_path, monkeypatch)
⋮----
def test_rejects_arbitrary_job_kind(tmp_path)
⋮----
def test_stats_expose_counts_without_payloads(tmp_path)
⋮----
first = q.enqueue("campaign-1", "strix_scan", {"secret": "must-not-leak"})
⋮----
stats = q.stats()
⋮----
def test_stats_expose_oldest_running_lease_without_worker_identity(tmp_path)
⋮----
job = q.enqueue("campaign-running", "report", {"platform": "generic"})
claimed = q.claim("worker-secret-name")
⋮----
def test_heartbeat_renews_only_current_owner(tmp_path)
⋮----
job = q.enqueue("campaign-1", "strix_scan", {"target": "https://example.test"})
⋮----
def test_heartbeat_rejects_finished_job(tmp_path)
⋮----
job = q.enqueue("campaign-1", "report", {})
⋮----
def test_stale_worker_cannot_finish_reclaimed_job(tmp_path, monkeypatch)
⋮----
job = q.enqueue("campaign-1", "report", {}, max_attempts=2)
⋮----
reclaimed = q.claim("worker-b")
⋮----
current = q.get(job["id"])
⋮----
completed = q.finish(job["id"], "worker-b", True)
⋮----
def test_stats_remain_healthy_after_expired_lease_recovery(tmp_path, monkeypatch)
⋮----
def test_enqueue_dedupe_key_returns_existing_job(tmp_path)
⋮----
payload = {"campaign_id": "campaign-1", "finding_id": "f1"}
first = q.enqueue("campaign-1", "independent_validation", payload, dedupe_key="validation:f1")
second = q.enqueue("campaign-1", "independent_validation", payload, dedupe_key="validation:f1")
⋮----
def test_enqueue_dedupe_key_rejects_payload_mismatch(tmp_path)
⋮----
def test_enqueue_dedupe_key_is_scoped_by_campaign_and_kind(tmp_path)
⋮----
a = q.enqueue("campaign-1", "report", {}, dedupe_key="same")
b = q.enqueue("campaign-2", "report", {}, dedupe_key="same")
c = q.enqueue("campaign-1", "browser_flow", {}, dedupe_key="same")
⋮----
def test_enqueue_rejects_blank_dedupe_key(tmp_path)
⋮----
def test_enqueue_rejects_oversized_payload(tmp_path, monkeypatch)
⋮----
def test_invalid_job_payload_limit_configuration_fails_closed(tmp_path, monkeypatch)
⋮----
def test_queue_rejects_invalid_campaign_and_worker_identifiers(tmp_path)
⋮----
def test_non_integer_lease_configuration_fails_closed(tmp_path, monkeypatch)
⋮----
def test_queue_rejects_unsafe_dedupe_identifiers(tmp_path)
⋮----
def test_cancel_operations_validate_identifiers_and_reason(tmp_path)
⋮----
job = q.claim("worker-a")
⋮----
def test_job_id_inputs_fail_closed_consistently(tmp_path)
⋮----
def test_queue_telemetry_validates_campaign_ids(tmp_path)
⋮----
def test_queue_database_permissions_are_private_on_posix(tmp_path)
⋮----
db = tmp_path / "q.sqlite3"
⋮----
def test_claim_kind_can_claim_parked_pentagi_job(tmp_path)
⋮----
job = q.enqueue(
⋮----
claimed = q.claim_kind("pentagi-worker", "pentagi_flow")
⋮----
def test_claim_kind_does_not_cross_job_kinds(tmp_path)
⋮----
report = q.enqueue("campaign-1", "report", {"platform": "generic"})
pentagi = q.enqueue(
⋮----
def test_claim_kind_rejects_unknown_kind(tmp_path)
⋮----
def test_failed_pentagi_job_remains_out_of_generic_claim_path(tmp_path)
⋮----
requeued = q.finish(job["id"], "pentagi-worker", False, "transient")
⋮----
reclaimed = q.claim_kind("pentagi-worker-2", "pentagi_flow")
⋮----
def test_get_by_dedupe_returns_exact_job(tmp_path)
⋮----
created = q.enqueue(
⋮----
found = q.get_by_dedupe(
⋮----
def test_claim_allowed_preserves_fifo_across_job_kinds(tmp_path)
⋮----
older = q.enqueue("campaign-1", "report", {"platform": "generic"})
newer = q.enqueue("campaign-1", "independent_validation", {"finding_id": "f1"})
⋮----
claimed = q.claim_allowed(
⋮----
def test_claim_allowed_rejects_empty_and_unknown_kind_sets(tmp_path)
````

## File: backend/tests/test_knowledge_memory.py
````python
def _finding_graph()
⋮----
graph = ObservationGraph()
⋮----
def test_confidence_increases_with_observed_validation_and_evidence()
⋮----
graph = _finding_graph()
⋮----
baseline = build_knowledge_snapshot(graph)
⋮----
validated = build_knowledge_snapshot(graph)
⋮----
evidenced = build_knowledge_snapshot(graph)
⋮----
def test_dry_run_and_error_do_not_masquerade_as_strong_validation()
⋮----
dry_run_graph = _finding_graph()
⋮----
dry_run_confidence = build_knowledge_snapshot(dry_run_graph).finding_confidence[0]
⋮----
error_graph = _finding_graph()
⋮----
error_confidence = build_knowledge_snapshot(error_graph).finding_confidence[0]
⋮----
def test_unknown_validation_outcome_fails_closed()
⋮----
confidence = build_knowledge_snapshot(graph).finding_confidence[0]
⋮----
def test_self_validation_receives_no_confidence_credit()
⋮----
def test_rank_findings_prioritizes_severity()
⋮----
findings = [
⋮----
ranked = rank_findings(findings, graph)
⋮----
def test_rank_findings_uses_evidence_gap_as_tiebreaker()
⋮----
def test_decision_history_reads_only_planner_memory_records()
⋮----
history = decision_history(graph)
⋮----
def test_explainable_ranking_combines_severity_evidence_and_stability()
⋮----
ranked = rank_findings_explainable(
⋮----
def test_explainable_ranking_rewards_evidence_gap_for_equal_severity()
⋮----
ranked = rank_findings_explainable(findings, graph)
⋮----
def test_explainable_ranking_unknown_severity_fails_closed()
⋮----
findings = [SimpleNamespace(id="f1", severity="unexpected")]
⋮----
def test_shared_scoring_tables_are_monotonic_and_fail_closed()
⋮----
severities = ["info", "low", "medium", "high", "critical"]
⋮----
severity_values = [severity_weight(item) for item in severities]
review_values = [review_severity_bonus(item) for item in severities]
⋮----
def test_temporal_need_prioritizes_contradiction_over_stability()
⋮----
def test_classic_and_explainable_rankings_share_severity_order()
⋮----
classic = rank_findings(findings, graph)
explainable = rank_findings_explainable(
````

## File: backend/tests/test_learning_memory.py
````python
def test_learning_memory_aggregates_only_explicit_outcomes()
⋮----
graph = ObservationGraph()
⋮----
memories = build_learning_memory(graph)
⋮----
memory = memories[0]
⋮----
def test_learning_memory_is_bounded_and_deterministic()
⋮----
first = build_learning_memory(graph, limit=2)
second = build_learning_memory(graph, limit=2)
⋮----
def test_learning_memory_route_is_exposed(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_learning_memory(campaign.id)
⋮----
def test_learning_memory_rejects_unbounded_limits()
⋮----
def test_worker_outcome_memory_excludes_payloads_and_errors()
⋮----
event = worker_outcome_event(
⋮----
summary = summarize_worker_outcomes([{**event, "at": "t1"}])
⋮----
def test_worker_outcome_memory_rejects_unknown_kinds_and_unbounded_limits()
````

## File: backend/tests/test_metrics.py
````python
class Queue
⋮----
def stats(self)
⋮----
class Storage
⋮----
def list_campaigns(self)
⋮----
def test_operational_metrics_are_aggregate_only()
⋮----
result = build_operational_metrics(Queue(), Storage())
⋮----
rendered = str(result)
⋮----
def test_metrics_route_is_exposed_under_authenticated_api()
````

## File: backend/tests/test_nuclei_preflight.py
````python
_SCANNER_ENV = (
⋮----
def _clear(monkeypatch)
⋮----
def _active_nuclei(monkeypatch)
⋮----
def test_scanner_capability_blocks_active_nuclei_without_pinned_version(monkeypatch)
⋮----
result = scanner_runtime_capability()
⋮----
def test_preflight_rejects_incomplete_active_nuclei_configuration(monkeypatch)
⋮----
result = build_deployment_preflight({"ok": True})
⋮----
def test_preflight_accepts_complete_active_nuclei_configuration_without_leaking_version(monkeypatch)
⋮----
def test_preflight_rejects_invalid_nuclei_boolean_fail_closed(monkeypatch)
````

## File: backend/tests/test_nuclei_queue_lifecycle.py
````python
def _campaign()
⋮----
def test_scan_engines_default_preserves_strix(monkeypatch)
⋮----
def test_scan_engines_support_explicit_nuclei_and_fail_closed(monkeypatch)
⋮----
def test_sqlite_queue_accepts_nuclei_scan(tmp_path)
⋮----
queue = JobQueue(str(tmp_path / "queue.sqlite3"))
job = queue.enqueue(
⋮----
def test_nuclei_worker_dry_run_preserves_safe_default(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = _campaign()
⋮----
root = tmp_path / "nuclei-runs"
⋮----
result = run_nuclei_job(
⋮----
def test_nuclei_worker_ingests_scoped_findings_and_queues_validation(tmp_path, monkeypatch)
⋮----
def fake_execute(plan)
⋮----
run_dir = Path(plan.output_dir)
⋮----
item = {
⋮----
counts = queue.campaign_job_counts(campaign.id)
````

## File: backend/tests/test_nuclei_worker_plan.py
````python
def _campaign(*, rps: float = 2.0)
⋮----
def _configure_run_root(monkeypatch, tmp_path)
⋮----
root = tmp_path / "nuclei-runs"
⋮----
def _admit_scanner_sandbox(monkeypatch)
⋮----
def test_nuclei_plan_is_dry_run_by_default(monkeypatch, tmp_path)
⋮----
root = _configure_run_root(monkeypatch, tmp_path)
⋮----
plan = build_nuclei_plan(_campaign(), str(root / "job-1"))
⋮----
def test_nuclei_plan_requires_both_activation_gates(monkeypatch, tmp_path)
⋮----
plan = build_nuclei_plan(_campaign(), str(root / "job-2"))
⋮----
def test_nuclei_plan_is_http_only_bounded_and_non_destructive(monkeypatch, tmp_path)
⋮----
command = plan.command
⋮----
def test_nuclei_plan_preserves_sub_one_rps_limits(monkeypatch, tmp_path)
⋮----
plan = build_nuclei_plan(_campaign(rps=0.25), str(root / "job-1"))
⋮----
def test_nuclei_plan_fails_closed_outside_scope(monkeypatch, tmp_path)
⋮----
campaign = _campaign()
⋮----
def test_nuclei_execution_uses_isolated_home(monkeypatch, tmp_path)
⋮----
captured = {"calls": []}
⋮----
class Result
⋮----
returncode = 0
stdout = ""
stderr = ""
⋮----
def fake_run(command, **kwargs)
⋮----
result = Result()
⋮----
result = execute(plan)
⋮----
def test_nuclei_active_execution_requires_allowlisted_runtime(monkeypatch, tmp_path)
⋮----
plan = build_nuclei_plan(_campaign(), str(root / "job-attest"))
⋮----
def test_nuclei_active_execution_rejects_version_mismatch(monkeypatch, tmp_path)
⋮----
stdout = "Nuclei Engine Version: v3.98.0"
⋮----
plan = build_nuclei_plan(_campaign(), str(root / "job-mismatch"))
````

## File: backend/tests/test_observation_graph.py
````python
def campaign(*, automated_scanning=True, findings=())
⋮----
def finding(finding_id="f1", status="validation_required")
⋮----
def test_graph_rejects_unknown_parent()
⋮----
graph = ObservationGraph()
⋮----
def test_graph_restores_without_relying_on_row_order()
⋮----
graph = ObservationGraph.from_records(
⋮----
def test_graph_restore_rejects_missing_or_cyclic_parents()
⋮----
def test_planner_starts_with_inventory()
⋮----
actions = AdaptivePlanner().plan(campaign(), ObservationGraph())
⋮----
def test_planner_progresses_through_bounded_phases()
⋮----
active_campaign = campaign(findings=(finding(status="validation_required"),))
⋮----
def test_planner_waits_for_explicit_resolution_after_observed_validation()
⋮----
action = AdaptivePlanner().plan(campaign(findings=(finding(),)), graph)[0]
⋮----
def test_planner_does_not_generate_report_when_all_findings_are_rejected()
⋮----
action = AdaptivePlanner().plan(campaign(findings=(finding(status="rejected"),)), graph)[0]
⋮----
def test_planner_fails_closed_when_graph_findings_lack_campaign_state()
⋮----
action = AdaptivePlanner().plan(campaign(), graph)[0]
⋮----
def test_planner_fails_closed_when_campaign_findings_lack_graph_state()
⋮----
action = AdaptivePlanner().plan(campaign(findings=(finding("campaign-f1"),)), graph)[0]
⋮----
def test_planner_fails_closed_when_graph_and_campaign_finding_ids_differ_before_validation()
⋮----
def test_planner_fails_closed_when_campaign_contains_untracked_finding_before_report()
⋮----
action = AdaptivePlanner().plan(
⋮----
def test_planner_stops_after_completed_scan_without_findings()
⋮----
def test_planner_counts_validations_by_finding_relationship()
⋮----
def test_planner_does_not_report_after_dry_run_or_error_validation()
⋮----
def test_planner_requires_validation_source_independence()
⋮----
def test_planner_stops_when_automation_is_disabled()
⋮----
action = AdaptivePlanner().plan(campaign(automated_scanning=False), graph)[0]
````

## File: backend/tests/test_observation_writer_provenance.py
````python
def test_record_artifact_seals_storage_provenance_against_metadata_override(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
campaign = Campaign(
⋮----
artifact = store.put_artifact(
observation_id = record_artifact(
⋮----
observation = next(
````

## File: backend/tests/test_observer_deadline_heartbeat.py
````python
def test_deadline_must_be_below_lease_ttl(monkeypatch)
⋮----
def test_scheduler_reports_deadline_exceeded(monkeypatch, tmp_path)
⋮----
lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
⋮----
values = iter([0.0, 6.0])
⋮----
result = run_scheduled_observation(
⋮----
def test_heartbeat_preserves_current_generation(tmp_path)
⋮----
path = str(tmp_path / "lease.sqlite3")
lease = ObserverLease(path)
generation = lease.acquire("node-a", ttl_seconds=10)
⋮----
result = with_lease_heartbeat(
````

## File: backend/tests/test_observer_fencing_integration.py
````python
def critical_metrics()
⋮----
def telemetry()
⋮----
def test_scheduler_passes_owner_and_generation(tmp_path)
⋮----
path = str(tmp_path / "shared.sqlite3")
lease = ObserverLease(path)
seen = {}
⋮----
def observe(owner, generation)
⋮----
result = run_scheduled_observation(lease, "node-a", observe)
⋮----
def test_stale_leader_end_to_end_commit_is_rejected(tmp_path)
⋮----
store = IncidentStore(path)
now = datetime.now(timezone.utc)
⋮----
generation_a = lease.acquire("node-a", ttl_seconds=10, now=now)
generation_b = lease.acquire("node-b", ttl_seconds=10, now=now + timedelta(seconds=11))
⋮----
def test_current_leader_end_to_end_commit_succeeds(tmp_path)
⋮----
generation = lease.acquire("node-b", ttl_seconds=90)
⋮----
result = observe_incidents(
````

## File: backend/tests/test_observer_fencing.py
````python
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def test_generation_increases_after_failover(tmp_path)
⋮----
lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
first = lease.acquire("one", ttl_seconds=10, now=NOW)
second = lease.acquire("two", ttl_seconds=10, now=NOW + timedelta(seconds=11))
⋮----
def test_stale_generation_cannot_heartbeat(tmp_path)
⋮----
def test_current_generation_can_heartbeat(tmp_path)
⋮----
generation = lease.acquire("one", ttl_seconds=10, now=NOW)
⋮----
def test_stale_generation_cannot_release_new_leader(tmp_path)
````

## File: backend/tests/test_observer_health_http.py
````python
TOKEN = "t" * 32
⋮----
def test_observer_health_route_uses_shared_runtime(monkeypatch)
⋮----
runtime = observer_runtime()
before = runtime.snapshot()["deadline_exceeded_count"]
⋮----
response = TestClient(main.app).get(
⋮----
payload = response.json()
````

## File: backend/tests/test_observer_health_metrics.py
````python
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def test_observer_health_metrics_exposes_redacted_ages_and_counters()
⋮----
health = ObserverHealth(
result = observer_health_metrics(health.snapshot(), now=NOW)
⋮----
def test_health_object_tracks_new_counters()
⋮----
health = ObserverHealth()
⋮----
result = health.snapshot()
````

## File: backend/tests/test_observer_resilience.py
````python
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def test_success_resets_failure_streak()
⋮----
health = ObserverHealth(consecutive_failures=2)
⋮----
def test_circuit_opens_after_failure_threshold()
⋮----
health = ObserverHealth()
⋮----
def test_generation_changes_are_counted()
⋮----
def test_snapshot_is_redacted()
⋮----
result = ObserverHealth().snapshot()
````

## File: backend/tests/test_observer_runtime.py
````python
def test_runtime_returns_same_process_singleton()
⋮----
def test_runtime_snapshot_is_detached()
⋮----
runtime = ObserverRuntime()
⋮----
first = runtime.snapshot()
````

## File: backend/tests/test_observer_scheduler.py
````python
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def test_only_one_owner_holds_active_lease(tmp_path)
⋮----
lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
⋮----
def test_expired_lease_can_be_taken_over(tmp_path)
⋮----
def test_scheduler_runs_only_for_leader(tmp_path)
⋮----
called = []
result = run_scheduled_observation(lease, "me", lambda owner, generation: called.append((owner, generation)) or {"ok": True})
⋮----
def test_scheduler_releases_lease_after_pass(tmp_path)
⋮----
result = run_scheduled_observation(lease, "me", lambda owner, generation: {"ok": True})
⋮----
def test_invalid_scheduler_config_fails_closed(monkeypatch)
````

## File: backend/tests/test_observer_slo.py
````python
def test_observer_slo_healthy_by_default()
⋮----
def test_failure_streak_degrades_then_becomes_critical()
⋮----
def test_stale_success_is_critical()
⋮----
result = build_observer_slo({"last_success_age_seconds": 301})
⋮----
def test_circuit_open_is_critical()
⋮----
def test_deadline_or_leadership_loss_degrades()
````

## File: backend/tests/test_openapi_integrity.py
````python
def test_openapi_operation_ids_are_unique()
⋮----
schema = app.openapi()
⋮----
operation_ids = []
⋮----
operation_id = operation.get("operationId")
⋮----
duplicate_warnings = [
⋮----
def test_core_control_routes_are_present_once_in_openapi()
⋮----
expected = {
⋮----
def test_runtime_routes_do_not_duplicate_method_and_path()
⋮----
seen = set()
duplicates = []
⋮----
path = getattr(route, "path", None)
methods = getattr(route, "methods", None)
⋮----
key = (method.upper(), path)
⋮----
def test_mutating_routes_are_confined_to_authenticated_api_namespace()
⋮----
mutating = {"post", "put", "patch", "delete"}
⋮----
exposed = []
⋮----
def test_capability_manifest_is_authenticated_and_conservative()
⋮----
capabilities = system_capabilities()
````

## File: backend/tests/test_operational_alerts.py
````python
def test_operational_alerts_are_aggregate_only(monkeypatch)
⋮----
result = build_operational_alerts(
⋮----
def test_operational_alerts_ok_below_thresholds(monkeypatch)
⋮----
def test_operational_alert_thresholds_fail_closed(monkeypatch)
⋮----
def test_alerts_route_is_exposed_under_authenticated_api()
````

## File: backend/tests/test_operational_slo.py
````python
def base_metrics()
⋮----
def test_slo_healthy_by_default(monkeypatch)
⋮----
result = build_operational_slo(base_metrics())
⋮----
def test_slo_degraded_on_warning_queue_age(monkeypatch)
⋮----
metrics = base_metrics()
⋮----
result = build_operational_slo(metrics)
⋮----
def test_slo_critical_on_queue_age(monkeypatch)
⋮----
def test_slo_critical_when_watchdog_errors(monkeypatch)
⋮----
def test_slo_rejects_inverted_thresholds(monkeypatch)
````

## File: backend/tests/test_orchestrator_validation_alignment.py
````python
def _campaign()
⋮----
def _graph(validation_value: str, validation_source: str) -> ObservationGraph
⋮----
graph = ObservationGraph()
⋮----
def test_dry_run_validation_does_not_remove_pending_finding()
⋮----
pending = _pending_findings(_campaign(), _graph("dry_run", "independent-validator"))
⋮----
def test_self_validation_does_not_remove_pending_finding()
⋮----
pending = _pending_findings(_campaign(), _graph("observed", "scanner"))
⋮----
def test_independent_observed_validation_removes_pending_finding()
⋮----
pending = _pending_findings(_campaign(), _graph("observed", "independent-validator"))
````

## File: backend/tests/test_orchestrator.py
````python
def make_campaign(*, automated_scanning=True, findings=None)
⋮----
def test_advance_bootstraps_asset_and_queues_bounded_recon(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = make_campaign()
⋮----
first = advance_campaign(campaign, queue, store)
second = advance_campaign(campaign, queue, store)
⋮----
jobs = [queue.get(job_id) for job_id in first["job_ids"]]
⋮----
kinds = {item["kind"] for item in store.list_observations(campaign.id)}
⋮----
def test_advance_stops_when_automation_disabled(tmp_path)
⋮----
campaign = make_campaign(automated_scanning=False)
⋮----
result = advance_campaign(campaign, queue, store)
⋮----
def test_advance_stops_when_runtime_budget_is_exhausted(tmp_path)
⋮----
result = advance_campaign(
⋮----
def test_advance_queues_only_unvalidated_findings_then_waits_for_resolution_and_reports(tmp_path)
⋮----
findings = [
campaign = make_campaign(findings=findings)
⋮----
asset = Observation("a1", "asset", "example.test", "scanner")
⋮----
queued = queue.get(result["job_ids"][0])
⋮----
confidence = {item["finding_id"]: item["score"] for item in result["memory"]["finding_confidence"]}
⋮----
waiting = advance_campaign(campaign, queue, store)
⋮----
report = advance_campaign(campaign, queue, store)
⋮----
def test_validation_jobs_are_ordered_by_adaptive_priority(tmp_path)
⋮----
queued = [queue.get(job_id) for job_id in result["job_ids"]]
⋮----
def test_validation_priority_prefers_less_supported_hypothesis_on_tie(tmp_path)
⋮----
hypotheses = {item["finding_id"]: item for item in result["hypotheses"]}
⋮----
def test_orchestrator_exposes_integrated_intelligence_context(tmp_path)
⋮----
intelligence = result["intelligence"]
⋮----
def test_orchestrator_gate_blocks_progress_after_failed_job(tmp_path)
⋮----
failed = queue.enqueue(
claimed = queue.claim("fixture-worker")
⋮----
def test_orchestrator_learning_memory_reaches_adaptive_cycle(tmp_path)
⋮----
memory = {
⋮----
def test_orchestrator_blocks_scan_below_surface_enrichment_threshold(tmp_path)
⋮----
asset = Observation("a1", "asset", "example.test", "recon")
endpoint = Observation(
⋮----
jobs = [queue.get(job_id) for job_id in result["job_ids"]]
⋮----
def test_orchestrator_allows_scan_after_surface_enrichment_threshold(tmp_path)
⋮----
def test_orchestrator_rejects_invalid_surface_enrichment_threshold(tmp_path, monkeypatch)
⋮----
def test_orchestrator_halts_after_repeated_requeues_without_success(tmp_path)
⋮----
def test_orchestrator_exposes_advisory_only_coverage_guidance(tmp_path)
⋮----
guidance = result["intelligence"]["coverage_guidance"]
coverage = result["intelligence"]["coverage"]
⋮----
def test_orchestrator_scanner_memory_can_only_reduce_configured_engines(tmp_path, monkeypatch)
⋮----
adaptation = result["intelligence"]["scanner_adaptation"]
⋮----
def test_orchestrator_caps_multi_engine_scan_fanout_to_remaining_budget(tmp_path, monkeypatch)
⋮----
coordination = result["intelligence"]["pipeline_coordination"]
⋮----
def test_validation_scheduler_selects_one_representative_per_cluster(tmp_path)
⋮----
queued_ids = [job["payload"]["finding_id"] for job in queued]
⋮----
def test_validation_scheduler_re_evaluates_cluster_after_representative_validation(tmp_path)
⋮----
first_jobs = [queue.get(job_id) for job_id in first["job_ids"]]
⋮----
second_jobs = [queue.get(job_id) for job_id in second["job_ids"]]
⋮----
def test_validation_scheduler_stops_cluster_fanout_after_strong_representative_evidence(tmp_path)
⋮----
def test_validation_scheduler_does_not_early_stop_on_observed_validation_without_quality_evidence(tmp_path)
⋮----
def _seed_planner_decisions(store, campaign_id, actions)
⋮----
previous_hash = None
⋮----
decision_hash = f"fixture-hash-{index}"
⋮----
previous_hash = decision_hash
⋮----
def test_critical_planner_oscillation_opens_circuit_breaker_before_new_work(tmp_path)
⋮----
graph = ObservationGraph.from_records(store.list_observations(campaign.id))
breaker = circuit_breaker_state(graph)
⋮----
def test_action_after_stop_opens_circuit_breaker_before_new_work(tmp_path)
⋮----
def test_single_planner_reversal_does_not_trip_breaker(tmp_path)
````

## File: backend/tests/test_outbox_chaos.py
````python
def _campaign() -> Campaign
⋮----
def _configure(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "xbow.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
def test_restart_after_start_intent_resumes_with_single_job(tmp_path, monkeypatch)
⋮----
store = Storage(db, artifacts)
campaign = _campaign()
⋮----
interrupted = Campaign.model_validate(document)
request_id = "chaos-start-after-intent"
receipt = main.policy_receipt(interrupted, "example.test", "automated_scan")
⋮----
# Process restart: construct fresh storage/queue instances and retry the API.
restarted_queue = JobQueue(db)
⋮----
result = main.start_campaign(campaign.id)
⋮----
persisted = Storage(db, artifacts).get_campaign(campaign.id)
⋮----
def test_restart_after_enqueue_reuses_same_start_job(tmp_path, monkeypatch)
⋮----
request_id = "chaos-start-after-enqueue"
⋮----
payload = main.sanitized_scan_payload(interrupted, receipt)
before_restart = JobQueue(db)
existing = before_restart.enqueue(
⋮----
# Simulate losing all process memory after enqueue but before audit reconciliation.
after_restart = JobQueue(db)
recovered = after_restart.get_by_dedupe(
⋮----
started = [
⋮----
def test_restart_after_manual_report_enqueue_is_repaired_locally(tmp_path, monkeypatch)
⋮----
request_id = "chaos-report-after-enqueue"
⋮----
queue_before = JobQueue(db)
existing = queue_before.enqueue(
⋮----
# Restart before report_queued audit event is saved.
queue_after = JobQueue(db)
⋮----
result = main.reconcile_campaign_outbox_local(campaign.id)
⋮----
events = [
⋮----
def test_restart_with_missing_job_never_recreates_work(tmp_path, monkeypatch)
⋮----
# Restart with no corresponding queue row at all.
⋮----
def test_queue_restart_preserves_dedupe_identity_and_terminal_status(tmp_path)
⋮----
db = str(tmp_path / "queue.sqlite3")
first = JobQueue(db)
job = first.enqueue(
claimed = first.claim("worker-before-restart")
⋮----
failed = first.finish(
⋮----
restarted = JobQueue(db)
recovered = restarted.get_by_dedupe(
````

## File: backend/tests/test_overview_reasoning.py
````python
def _campaign()
⋮----
def test_overview_surfaces_hypothesis_and_evidence_chain_state(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = _campaign()
store = Storage(db, artifacts)
⋮----
result = campaign_overview(campaign.id)
⋮----
def test_overview_chain_becomes_complete_after_independent_evidence(tmp_path, monkeypatch)
⋮----
def test_overview_counts_duplicate_candidate_groups(tmp_path, monkeypatch)
````

## File: backend/tests/test_pentagi_admission.py
````python
def _campaign(*, rps: float = 1.0)
⋮----
def _plan(campaign)
⋮----
def _enable_runtime(monkeypatch)
⋮----
def test_admission_is_fail_closed_by_default(monkeypatch)
⋮----
campaign = _campaign()
⋮----
decision = evaluate_pentagi_admission(campaign, _plan(campaign))
⋮----
def test_current_adapter_cannot_be_enabled_into_execution(monkeypatch)
⋮----
def test_admission_rejects_campaign_above_local_cap(monkeypatch)
⋮----
campaign = _campaign(rps=3.0)
future_plan = replace(
⋮----
decision = evaluate_pentagi_admission(campaign, future_plan)
⋮----
def test_future_enforceable_transport_still_requires_every_gate(monkeypatch)
⋮----
campaign = _campaign(rps=1.5)
⋮----
def test_invalid_boolean_configuration_fails_closed(monkeypatch, name, value)
⋮----
@pytest.mark.parametrize("value", ["not-a-number", "0", "20.1"])
def test_invalid_admission_cap_fails_closed(monkeypatch, value)
⋮----
def test_plan_target_mismatch_is_rejected(monkeypatch)
⋮----
plan = replace(_plan(campaign), target="https://other.example.test/")
⋮----
def test_policy_fingerprint_is_stable_and_policy_sensitive(monkeypatch)
⋮----
plan = _plan(campaign)
⋮----
first = evaluate_pentagi_admission(campaign, plan)
second = evaluate_pentagi_admission(campaign, plan)
⋮----
changed = evaluate_pentagi_admission(campaign, plan)
````

## File: backend/tests/test_pentagi_auth.py
````python
def _vault_key() -> str
⋮----
def test_pentagi_auth_reads_legacy_env_when_vault_disabled(monkeypatch)
⋮----
auth = load_pentagi_auth()
⋮----
def test_pentagi_auth_reads_vault_and_refuses_legacy_fallback(monkeypatch, tmp_path)
⋮----
vault_path = tmp_path / "vault.json"
⋮----
def test_pentagi_auth_missing_token_fails_closed(monkeypatch)
⋮----
def test_pentagi_auth_rejects_unsafe_token_values(monkeypatch, token)
⋮----
def test_pentagi_auth_rejects_oversized_token(monkeypatch)
````

## File: backend/tests/test_pentagi_control_api.py
````python
def _campaign()
⋮----
def _configure(monkeypatch)
⋮----
def test_pentagi_preview_exposes_metadata_not_request_payload(monkeypatch)
⋮----
campaign = _campaign()
⋮----
result = main.preview_pentagi_campaign(campaign.id)
⋮----
def test_pentagi_dispatch_is_fail_closed_without_enforcing_transport(tmp_path, monkeypatch)
⋮----
jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
⋮----
preview = pentagi_control.prepare_pentagi_control_preview(campaign)
executable_plan = replace(
executable_decision = pentagi_control.evaluate_pentagi_admission(
future_preview = pentagi_control.PentagiControlPreview(
⋮----
def test_pentagi_queue_audit_reconciliation_retries_on_fresh_snapshot(monkeypatch)
⋮----
snapshots = [
saves = []
⋮----
def load(_campaign_id)
⋮----
def save(value, expected_version=None)
⋮----
result = main._reconcile_pentagi_queued_event(
⋮----
queued_events = [
⋮----
saved = []
⋮----
result = main.dispatch_pentagi_campaign(campaign.id)
⋮----
safe_job = result["job"]
⋮----
persisted = jobs.get(safe_job["id"])
⋮----
pentagi_events = [
⋮----
repeated = main.dispatch_pentagi_campaign(campaign.id)
⋮----
def test_pentagi_dispatch_fails_closed_when_transport_disabled(tmp_path, monkeypatch)
⋮----
class _ArtifactStore
⋮----
def list_artifacts(self, campaign_id)
⋮----
def test_pentagi_status_summary_filters_local_artifacts(tmp_path, monkeypatch)
⋮----
result = main.pentagi_campaign_status(campaign.id)
⋮----
def test_pentagi_dispatch_rejects_closed_lifecycle(tmp_path, monkeypatch)
````

## File: backend/tests/test_pentagi_control.py
````python
def _campaign()
⋮----
def _configure(monkeypatch)
⋮----
def test_control_preview_reports_operational_gates(monkeypatch)
⋮----
preview = prepare_pentagi_control_preview(_campaign())
⋮----
def test_control_ready_remains_blocked_without_enforcing_transport(monkeypatch)
⋮----
def test_control_ready_keeps_global_dry_run_fail_closed(monkeypatch)
````

## File: backend/tests/test_pentagi_dispatch.py
````python
def _campaign()
⋮----
def _future_plan(campaign)
⋮----
def _enable_runtime(monkeypatch)
⋮----
def test_dispatch_is_deduplicated_atomically_in_sqlite(tmp_path, monkeypatch)
⋮----
queue = JobQueue(str(tmp_path / "queue.sqlite3"))
campaign = _campaign()
plan = _future_plan(campaign)
⋮----
first = enqueue_pentagi_flow(queue, campaign, plan)
second = enqueue_pentagi_flow(queue, campaign, plan)
⋮----
def test_dispatch_payload_is_bound_to_permit(tmp_path, monkeypatch)
⋮----
job = enqueue_pentagi_flow(queue, campaign, plan)
⋮----
def test_dispatch_rejects_current_non_executing_plan(tmp_path, monkeypatch)
⋮----
plan = build_pentagi_flow_plan(
⋮----
def test_policy_change_creates_new_identity_not_silent_reuse(tmp_path, monkeypatch)
⋮----
first_plan = _future_plan(campaign)
first = enqueue_pentagi_flow(queue, campaign, first_plan)
⋮----
second_plan = _future_plan(campaign)
second = enqueue_pentagi_flow(queue, campaign, second_plan)
⋮----
def test_pentagi_jobs_are_parked_for_generic_workers(tmp_path, monkeypatch)
⋮----
job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
⋮----
parked = queue.get(job["id"])
⋮----
def test_parked_pentagi_job_does_not_block_other_work(tmp_path, monkeypatch)
⋮----
parked = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
active = queue.enqueue("other-campaign", "report", {"platform": "generic"})
⋮----
claimed = queue.claim("generic-worker")
⋮----
def test_pentagi_dispatch_disables_automatic_remote_retry(tmp_path, monkeypatch)
⋮----
claimed = queue.claim_kind("pentagi-worker", "pentagi_flow")
⋮----
failed = queue.finish(
````

## File: backend/tests/test_pentagi_execution_guard.py
````python
def _campaign()
⋮----
def _future_plan(campaign)
⋮----
def _enable_runtime(monkeypatch)
⋮----
def test_guard_denies_current_non_executing_adapter(monkeypatch)
⋮----
campaign = _campaign()
plan = build_pentagi_flow_plan(
⋮----
def test_future_enforceable_plan_gets_stable_idempotency_key(monkeypatch)
⋮----
plan = _future_plan(campaign)
⋮----
first = issue_pentagi_execution_permit(campaign, plan)
second = issue_pentagi_execution_permit(campaign, plan)
⋮----
def test_policy_change_invalidates_existing_permit(monkeypatch)
⋮----
permit = issue_pentagi_execution_permit(campaign, plan)
⋮----
def test_plan_payload_change_invalidates_existing_permit(monkeypatch)
⋮----
changed_payload = dict(plan.payload)
changed_variables = dict(changed_payload["variables"])
⋮----
changed_plan = replace(plan, payload=changed_payload)
⋮----
def test_runtime_gate_change_invalidates_existing_permit(monkeypatch)
````

## File: backend/tests/test_pentagi_flow_status.py
````python
class _Socket
⋮----
def settimeout(self, value)
⋮----
class _Raw
⋮----
def __init__(self, sock)
⋮----
class _FP
⋮----
class _Response
⋮----
def __init__(self, payload: bytes, content_type: str = "application/json")
⋮----
def getcode(self)
⋮----
def read(self, amount)
⋮----
chunk = self._payload[self._offset:self._offset + amount]
⋮----
class _Opener
⋮----
def __init__(self, response)
⋮----
def open(self, request, timeout)
⋮----
def _auth(monkeypatch)
⋮----
def test_fetch_flow_status_is_read_only_and_validated(monkeypatch)
⋮----
opener = _Opener(
⋮----
result = fetch_pentagi_flow_status(
⋮----
@pytest.mark.parametrize("status", ["created", "running", "waiting", "finished", "failed"])
def test_fetch_flow_status_accepts_documented_states(monkeypatch, status)
⋮----
opener = _Opener(_Response(
⋮----
def test_fetch_flow_status_fails_closed_on_invalid_response(monkeypatch, payload)
⋮----
opener = _Opener(_Response(payload))
⋮----
def test_fetch_flow_status_rejects_unsafe_base_endpoint(monkeypatch)
````

## File: backend/tests/test_pentagi_status_poller.py
````python
class _Clock
⋮----
def __init__(self)
⋮----
def monotonic(self)
⋮----
def sleep(self, seconds)
⋮----
def _snapshot(status)
⋮----
def test_poller_stops_on_finished(monkeypatch)
⋮----
statuses = iter(["created", "running", "finished"])
⋮----
clock = _Clock()
⋮----
result = poll_pentagi_flow_until_terminal(
⋮----
def test_poller_stops_on_failed(monkeypatch)
⋮----
def test_poller_times_out_without_infinite_loop(monkeypatch)
⋮----
def test_poller_rejects_invalid_interval(monkeypatch)
⋮----
def test_poller_continues_through_waiting(monkeypatch)
⋮----
statuses = iter(["waiting", "finished"])
⋮----
def test_poller_caps_refresh_by_remaining_budget(monkeypatch)
⋮----
observed = []
⋮----
def refresh(*args, **kwargs)
````

## File: backend/tests/test_pentagi_status_tracker.py
````python
class _Store
⋮----
def __init__(self, receipt_kind="pentagi_receipt")
⋮----
def read_artifact(self, campaign_id, artifact_id)
⋮----
def put_artifact(self, campaign_id, kind, content, **kwargs)
⋮----
record = {
⋮----
def test_refresh_persists_idempotent_status_snapshot(monkeypatch)
⋮----
store = _Store()
⋮----
result = refresh_pentagi_flow_status(store, "campaign-1", "receipt-1")
⋮----
write = store.writes[0]
⋮----
decoded = json.loads(write["content"].decode())
⋮----
def test_refresh_rejects_non_receipt_artifact(monkeypatch)
⋮----
store = _Store(receipt_kind="report")
````

## File: backend/tests/test_pentagi_status_worker_service.py
````python
def _enable(monkeypatch)
⋮----
def test_status_worker_is_disabled_by_default(monkeypatch)
⋮----
def test_status_jobs_are_invisible_to_generic_workers(tmp_path)
⋮----
queue = JobQueue(str(tmp_path / "q.sqlite3"))
job = queue.enqueue(
⋮----
claimed = queue.claim_kind("status-worker", "pentagi_status")
⋮----
def test_status_worker_completes_terminal_tracking_job(tmp_path, monkeypatch)
⋮----
def test_status_worker_requeues_bounded_timeout_job(tmp_path, monkeypatch)
⋮----
requeued = queue.get(job["id"])
````

## File: backend/tests/test_pentagi_worker_service.py
````python
def _campaign()
⋮----
def _future_plan(campaign)
⋮----
def _enable_admission(monkeypatch)
⋮----
def _enable_worker(monkeypatch)
⋮----
class _Store
⋮----
def __init__(self, campaign)
⋮----
def get_campaign_record(self, campaign_id)
⋮----
def put_artifact(self, campaign_id, kind, content, **kwargs)
⋮----
record = {
⋮----
def test_transport_gate_is_explicit(monkeypatch)
⋮----
def test_worker_runtime_gate_blocks_before_claim(monkeypatch)
⋮----
def test_preflight_revalidates_exact_queued_permit(tmp_path, monkeypatch)
⋮----
queue = JobQueue(str(tmp_path / "queue.sqlite3"))
campaign = _campaign()
queued = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
claimed = queue.claim_kind("pentagi-worker", "pentagi_flow")
⋮----
result = preflight_pentagi_job(claimed, campaign)
⋮----
def test_preflight_rejects_policy_drift(tmp_path, monkeypatch)
⋮----
def test_preflight_rejects_queue_identity_tampering(tmp_path, monkeypatch)
⋮----
def test_process_one_submits_once_and_completes(tmp_path, monkeypatch)
⋮----
job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
calls = []
⋮----
def submit(plan, permit)
⋮----
store = _Store(campaign)
⋮----
receipt = store.artifacts[0]
⋮----
decoded = __import__("json").loads(receipt["content"].decode("utf-8"))
⋮----
completed = queue.get(job["id"])
⋮----
def test_process_one_transport_failure_is_terminal_without_retry(tmp_path, monkeypatch)
⋮----
def fail(plan, permit)
⋮----
failed = queue.get(job["id"])
⋮----
def test_process_one_revalidates_after_claim_before_transport(tmp_path, monkeypatch)
⋮----
class _DriftingStore(_Store)
⋮----
called = False
⋮----
called = True
⋮----
def test_process_one_maintains_lease_during_transport(tmp_path, monkeypatch)
⋮----
heartbeats = []
original_heartbeat = queue.heartbeat
⋮----
def heartbeat(job_id, worker_id)
⋮----
def test_process_one_contains_admission_policy_error(tmp_path, monkeypatch)
````

## File: backend/tests/test_pipeline_swarm.py
````python
def _usage(**overrides)
⋮----
values = {
⋮----
def test_pipeline_swarm_uses_registered_specialized_agents()
⋮----
scan = coordinate_pipeline_action("scan", 2, _usage())
validate = coordinate_pipeline_action("validate", 4, _usage())
report = coordinate_pipeline_action("report", 1, _usage())
⋮----
def test_pipeline_swarm_shares_inflight_capacity_across_stages()
⋮----
usage = _usage(remaining_inflight_jobs=1)
⋮----
scan = coordinate_pipeline_action("scan", 2, usage)
validate = coordinate_pipeline_action("validate", 10, usage)
report = coordinate_pipeline_action("report", 1, usage)
⋮----
def test_pipeline_swarm_respects_stage_specific_budgets()
⋮----
limits = PlannerBudget(
usage = _usage(
⋮----
def test_pipeline_swarm_rejects_unknown_action_and_negative_request()
````

## File: backend/tests/test_plan_evidence_quality.py
````python
def test_campaign_plan_uses_configured_budget_and_exposes_evidence_quality(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_plan(campaign.id)
````

## File: backend/tests/test_planner_advisory.py
````python
def _campaign(findings)
⋮----
def test_advisory_context_selects_highest_ranked_finding()
⋮----
graph = ObservationGraph()
⋮----
campaign = _campaign([
⋮----
context = build_advisory_planner_context(campaign, graph)
⋮----
def test_advisory_context_uses_temporal_stability_in_focus_selection()
⋮----
context = build_advisory_planner_context(
⋮----
def test_advisory_context_handles_no_findings()
⋮----
context = build_advisory_planner_context(_campaign([]), ObservationGraph())
⋮----
def test_advisory_context_returns_bounded_top_n_focus()
⋮----
findings = []
⋮----
finding_id = f"f{index}"
⋮----
context = build_advisory_planner_context(_campaign(findings), graph, top_n=2)
⋮----
def test_advisory_context_rejects_unbounded_top_n()
⋮----
def test_advisory_focus_fingerprint_is_deterministic()
⋮----
advisory = {
⋮----
first = advisory_focus_fingerprint(advisory)
second = advisory_focus_fingerprint(dict(reversed(list(advisory.items()))))
⋮----
def test_advisory_delta_detects_top_change_as_significant()
⋮----
previous = {
current = {
⋮----
delta = diff_advisory_focus_snapshots(previous, current)
⋮----
def test_advisory_delta_tracks_entries_exits_and_rank_changes()
⋮----
def test_advisory_delta_is_empty_for_equivalent_focus()
⋮----
snapshot = {
⋮----
delta = diff_advisory_focus_snapshots(snapshot, snapshot)
⋮----
def test_advisory_journal_emits_top_change_and_priority_shift()
⋮----
snapshots = [
⋮----
events = build_advisory_decision_journal(snapshots)
⋮----
def test_advisory_journal_emits_focus_stabilized_after_three_equal_snapshots()
⋮----
def test_advisory_journal_limit_is_bounded()
````

## File: backend/tests/test_planner_budget.py
````python
def test_budget_usage_reads_durable_campaign_jobs(tmp_path)
⋮----
queue = JobQueue(str(tmp_path / "db.sqlite3"))
graph = ObservationGraph()
⋮----
usage = budget_usage(graph, queue, "c1")
⋮----
def test_validate_action_stops_when_validation_budget_is_exhausted(tmp_path)
⋮----
limits = PlannerBudget(max_validations=2, max_validation_batch=2)
⋮----
def test_scan_limit_does_not_block_unrelated_report_action(tmp_path)
⋮----
limits = PlannerBudget(max_scans=1)
⋮----
def test_total_action_budget_fails_closed(tmp_path)
⋮----
limits = PlannerBudget(max_actions=1)
⋮----
def test_validation_batch_is_bounded_by_batch_and_remaining_budget(tmp_path)
⋮----
limits = PlannerBudget(max_validations=12, max_validation_batch=10)
⋮----
usage = budget_usage(graph, queue, "c1", limits)
⋮----
def test_inflight_budget_stops_new_network_work(tmp_path)
⋮----
limits = PlannerBudget(max_inflight_jobs=2)
⋮----
def test_validation_batch_respects_inflight_capacity(tmp_path)
⋮----
limits = PlannerBudget(max_validations=20, max_validation_batch=10, max_inflight_jobs=6)
⋮----
def test_repeated_failed_jobs_stop_new_network_work(tmp_path)
⋮----
limits = PlannerBudget(max_failed_jobs=2)
⋮----
queued = queue.enqueue(
claimed = queue.claim("worker-1")
⋮----
def test_stop_action_is_never_blocked_by_job_budgets(tmp_path)
⋮----
limits = PlannerBudget(max_inflight_jobs=1)
⋮----
requested = PlannedAction("stop", "example.test", "policy stop", 100)
⋮----
def test_local_inventory_is_not_blocked_by_failed_job_budget(tmp_path)
⋮----
limits = PlannerBudget(max_failed_jobs=1)
⋮----
requested = PlannedAction("inventory", "example.test", "seed target", 100)
⋮----
def test_validation_batch_is_zero_when_no_inflight_capacity_remains(tmp_path)
⋮----
def test_budget_rejects_non_positive_limits()
⋮----
def test_budget_rejects_validation_batch_larger_than_total_limit()
⋮----
def test_scan_budget_counts_strix_and_nuclei_jobs(tmp_path)
⋮----
usage = budget_usage(graph, queue, "c1", PlannerBudget(max_scans=3))
⋮----
def test_scan_batch_limit_respects_scan_and_inflight_capacity(tmp_path)
⋮----
limits = PlannerBudget(max_scans=3, max_inflight_jobs=3)
⋮----
def test_scan_batch_limit_rejects_negative_request(tmp_path)
````

## File: backend/tests/test_planner_limits.py
````python
def _campaign()
⋮----
def test_planner_limits_use_safe_defaults(monkeypatch)
⋮----
limits = planner_limits()
⋮----
def test_planner_limits_reject_invalid_configuration(monkeypatch, name, value)
⋮----
def test_planner_stops_when_endpoint_bound_is_exceeded(monkeypatch)
⋮----
graph = ObservationGraph()
⋮----
action = AdaptivePlanner().plan(_campaign(), graph)[0]
⋮----
def test_planner_stops_when_finding_bound_is_exceeded(monkeypatch)
⋮----
def test_planner_fails_closed_on_invalid_limit_configuration(monkeypatch)
⋮----
action = AdaptivePlanner().plan(_campaign(), ObservationGraph())[0]
````

## File: backend/tests/test_policy_integrity.py
````python
def _campaign()
⋮----
def test_policy_receipt_has_stable_hash_without_hmac(monkeypatch)
⋮----
receipt = policy_receipt(_campaign(), "example.test", "automated_scan")
verified = verify_policy_receipt(receipt)
⋮----
def test_policy_receipt_detects_tampering(monkeypatch)
⋮----
def test_policy_receipt_hmac_signature_detects_resealed_tampering(monkeypatch)
⋮----
forged = dict(receipt)
⋮----
forged = seal_policy_receipt(forged)
⋮----
verified = verify_policy_receipt(forged)
⋮----
def test_hmac_receipt_fails_closed_without_verification_key(monkeypatch)
````

## File: backend/tests/test_policy_invariants.py
````python
def _campaign(**rule_overrides)
⋮----
rules = ProgramRules(
⋮----
def test_deny_rules_override_allow_rules()
⋮----
campaign = _campaign()
rules = campaign.target.rules
⋮----
def test_sensitive_actions_fail_closed_by_default()
⋮----
receipt = policy_receipt(campaign, "example.test", action)
⋮----
def test_out_of_scope_target_blocks_automated_scan()
⋮----
receipt = policy_receipt(campaign, "outside.test", "automated_scan")
⋮----
def test_worker_payload_never_enables_prohibited_actions()
⋮----
campaign = _campaign(
receipt = policy_receipt(campaign, "example.test", "automated_scan")
payload = sanitized_scan_payload(campaign, receipt)
````

## File: backend/tests/test_postgres_integration.py
````python
POSTGRES_URL = os.getenv("XBOW_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="XBOW_TEST_POSTGRES_URL is not configured")
⋮----
def _store(tmp_path)
⋮----
def test_postgres_campaign_roundtrip(tmp_path)
⋮----
store = _store(tmp_path)
campaign_id = f"ci-{uuid4()}"
document = {
⋮----
def test_postgres_campaign_version_conflict_fails_closed(tmp_path)
⋮----
updated = {**document, "state": "running", "updated_at": "y"}
````

## File: backend/tests/test_postgres_storage.py
````python
def test_postgres_sql_compat_translates_placeholders()
⋮----
def test_postgres_sql_compat_translates_begin_immediate()
⋮----
def test_postgres_storage_requires_database_url(monkeypatch)
⋮----
def test_postgres_storage_rejects_non_postgres_url(monkeypatch)
⋮----
def test_postgres_storage_rejects_url_without_host(monkeypatch)
````

## File: backend/tests/test_queue_age_metrics.py
````python
class Queue
⋮----
def __init__(self, oldest, running=None)
⋮----
def stats(self)
⋮----
class Storage
⋮----
def list_campaigns(self)
⋮----
def test_metrics_expose_queue_age_without_payloads()
⋮----
oldest = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
metrics = build_operational_metrics(Queue(oldest), Storage())
⋮----
def test_invalid_queue_timestamp_does_not_break_metrics()
⋮----
metrics = build_operational_metrics(Queue("not-a-date"), Storage())
⋮----
def test_alerts_detect_stalled_queue(monkeypatch)
⋮----
result = build_operational_alerts(
stalled = [item for item in result["alerts"] if item["code"] == "queue_stalled"]
⋮----
def test_queue_age_threshold_fails_closed_on_invalid_config(monkeypatch)
⋮----
def test_overflowing_queue_timestamp_does_not_break_metrics()
⋮----
metrics = build_operational_metrics(
⋮----
class OutboxStorage
⋮----
def __init__(self, requested_at)
⋮----
def test_metrics_expose_outbox_age_and_counts_without_identities()
⋮----
requested_at = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
metrics = build_operational_metrics(Queue(None), OutboxStorage(requested_at))
⋮----
rendered = str(metrics)
⋮----
def test_alerts_detect_stalled_outbox(monkeypatch)
⋮----
stalled = [item for item in result["alerts"] if item["code"] == "outbox_stalled"]
⋮----
def test_alerts_detect_outbox_backlog(monkeypatch)
⋮----
backlog = [item for item in result["alerts"] if item["code"] == "outbox_backlog"]
⋮----
def test_outbox_alert_thresholds_fail_closed(monkeypatch)
⋮----
def test_metrics_expose_running_lease_age()
⋮----
running = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
metrics = build_operational_metrics(Queue(None, running), Storage())
⋮----
def test_invalid_running_lease_timestamp_does_not_break_metrics()
⋮----
metrics = build_operational_metrics(Queue(None, "not-a-date"), Storage())
⋮----
def test_alerts_detect_stale_running_lease(monkeypatch)
⋮----
stale = [
⋮----
def test_running_lease_alert_threshold_fails_closed(monkeypatch)
````

## File: backend/tests/test_queue_backend.py
````python
def test_queue_backend_defaults_to_sqlite(monkeypatch, tmp_path)
⋮----
backend = create_queue()
⋮----
def test_queue_backend_accepts_sqlite_alias(monkeypatch, tmp_path)
⋮----
def test_queue_backend_accepts_redis(monkeypatch)
⋮----
def test_queue_backend_builds_redis_adapter(monkeypatch)
⋮----
def test_queue_backend_redis_requires_explicit_url(monkeypatch)
⋮----
def test_queue_backend_rejects_unknown_backend(monkeypatch)
````

## File: backend/tests/test_queue_health.py
````python
def test_queue_health_reports_integrity_without_payloads(tmp_path)
⋮----
q = JobQueue(str(tmp_path / "q.sqlite3"))
⋮----
health = q.health()
⋮----
def test_queue_health_fails_closed_on_corrupt_database(tmp_path)
⋮----
path = tmp_path / "q.sqlite3"
q = JobQueue(str(path))
````

## File: backend/tests/test_readiness.py
````python
class HealthyQueue
⋮----
def health(self)
⋮----
class UnhealthyQueue
⋮----
class ExplodingQueue
⋮----
def __init__(self)
⋮----
class FakeStorage
⋮----
def __init__(self, root: Path, *, healthy: bool = True)
⋮----
def test_readiness_requires_database_and_artifact_store(tmp_path, monkeypatch)
⋮----
result = readiness.readiness()
⋮----
def test_readiness_fails_closed_when_database_is_unhealthy(tmp_path, monkeypatch)
⋮----
def test_readiness_sanitizes_queue_probe_exceptions(tmp_path, monkeypatch)
⋮----
def test_readiness_sanitizes_storage_probe_exceptions(monkeypatch)
⋮----
def explode_storage()
⋮----
def test_readiness_fails_when_metadata_storage_is_unhealthy(tmp_path, monkeypatch)
⋮----
def test_artifact_store_probe_fails_for_non_directory(tmp_path)
⋮----
target = tmp_path / "artifact-file"
⋮----
result = readiness._artifact_store_ready(target)
⋮----
def test_main_returns_normally_when_ready(monkeypatch)
⋮----
def test_main_exits_nonzero_when_not_ready(monkeypatch)
````

## File: backend/tests/test_recon_swarm.py
````python
def test_capabilities_are_bounded_read_only_and_get_head_only()
⋮----
capabilities = recon_capabilities()
⋮----
def test_recon_plan_bootstraps_crawl_and_technology_context()
⋮----
graph = ObservationGraph()
⋮----
tasks = build_recon_plan(
⋮----
def test_recon_plan_adds_form_and_browser_mapping_after_endpoints_exist()
⋮----
def test_recon_plan_fails_closed_out_of_scope_and_invalid_limits()
⋮----
def test_recon_plan_route_is_exposed_and_scope_aware(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_recon_plan(campaign.id)
⋮----
def test_recon_plan_refuses_unobserved_host_when_asset_inventory_exists()
⋮----
def test_recon_plan_accepts_matching_bare_asset_host()
````

## File: backend/tests/test_recon_worker.py
````python
class _Response
⋮----
def __init__(self, body: bytes, headers: dict[str, str], status: int = 200)
⋮----
message = Message()
⋮----
def read(self, _limit: int)
⋮----
def __enter__(self)
⋮----
def __exit__(self, exc_type, exc, tb)
⋮----
class _Opener
⋮----
def __init__(self, response)
⋮----
def open(self, _request, timeout)
⋮----
def _campaign()
⋮----
def test_recon_worker_is_dry_run_by_default(monkeypatch)
⋮----
result = execute_recon_task(
⋮----
def test_recon_worker_extracts_only_same_origin_read_only_surface(monkeypatch)
⋮----
html = b"""
response = _Response(html, {"Content-Type": "text/html"})
⋮----
def test_recon_worker_detects_bounded_technology_headers(monkeypatch)
⋮----
response = _Response(
⋮----
def test_recon_worker_rejects_out_of_scope_target(monkeypatch)
⋮----
def test_recon_worker_enriches_same_origin_resources_without_extra_requests(monkeypatch)
⋮----
opener = _Opener(response)
calls = {"count": 0}
⋮----
def _open(_request, timeout)
⋮----
def test_recon_surface_parser_bounds_discovered_links_and_form_inputs(monkeypatch)
⋮----
links = "".join(f'<a href="/p/{index}">x</a>' for index in range(700))
inputs = "".join(f'<input name="field-{index}">' for index in range(150))
html = f"<html>{links}<form action='/search' method='get'>{inputs}</form></html>".encode()
⋮----
class _RoutingOpener
⋮----
def __init__(self, routes)
⋮----
def open(self, request, timeout)
⋮----
url = request.full_url
⋮----
def test_recon_worker_crawls_multiple_pages_with_explicit_budget(monkeypatch)
⋮----
opener = _RoutingOpener(
⋮----
def test_recon_worker_respects_local_request_cap(monkeypatch)
⋮----
def test_recon_worker_rejects_invalid_request_budget(monkeypatch)
⋮----
def test_recon_worker_rejects_invalid_local_depth(monkeypatch)
⋮----
def test_recon_worker_reports_consumed_budget_and_skip_telemetry(monkeypatch)
⋮----
root = _Response(
one = _Response(
two = _Response(
⋮----
def test_recon_worker_stops_cleanly_when_wall_clock_budget_expires(monkeypatch)
⋮----
ticks = iter((0.0, 0.1, 0.2, 0.3, 6.0, 6.0))
⋮----
def test_recon_worker_rejects_invalid_wall_clock_budget(monkeypatch)
⋮----
def test_recon_worker_marks_request_budget_saturation_as_incomplete(monkeypatch)
⋮----
opener = _RoutingOpener({"https://example.test/": root})
⋮----
def test_recon_worker_reports_incomplete_frontier_when_budget_prevents_followup(monkeypatch)
````

## File: backend/tests/test_red_team_coverage.py
````python
def test_red_team_coverage_reports_gaps_without_executing_actions()
⋮----
graph = ObservationGraph()
⋮----
result = build_red_team_coverage(graph)
⋮----
def test_endpoint_review_credit_requires_recorded_review_evidence()
⋮----
before = build_red_team_coverage(graph)
⋮----
after = build_red_team_coverage(graph)
⋮----
def test_red_team_coverage_improves_after_independent_evidence()
⋮----
def test_red_team_coverage_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_red_team_coverage(campaign.id)
````

## File: backend/tests/test_red_team_decision.py
````python
def test_decision_engine_prioritizes_scope_integrity()
⋮----
graph = ObservationGraph()
⋮----
decisions = build_red_team_decisions(
⋮----
def test_decision_engine_prioritizes_validation_and_evidence()
⋮----
finding = Finding(
⋮----
decisions = build_red_team_decisions([finding], graph)
⋮----
kinds = [item.kind for item in decisions]
⋮----
def test_decision_engine_becomes_idle_when_no_work_exists()
⋮----
decisions = build_red_team_decisions([], ObservationGraph())
⋮----
def test_decision_route_is_exposed_and_scope_aware(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_red_team_decisions(campaign.id)
⋮----
def test_decision_limit_fails_closed()
⋮----
def _strong_finding_graph()
⋮----
def test_readiness_suppresses_redundant_validation_when_report_ready()
⋮----
snapshots = [
⋮----
def test_contradictory_readiness_requires_human_review()
⋮----
def _cluster_findings()
⋮----
first = Finding(
second = Finding(
⋮----
def _mixed_cluster_graph()
⋮----
def test_mixed_cluster_holds_ready_member_back_from_report_review()
⋮----
report = next(
validate = next(item for item in decisions if item.kind == "validate_findings")
⋮----
def test_blocked_cluster_escalates_all_cluster_members_for_human_review()
⋮----
graph = _mixed_cluster_graph()
⋮----
review = decisions[0]
````

## File: backend/tests/test_redis_chaos.py
````python
@pytest.fixture
def redis_queue(monkeypatch)
⋮----
url = os.getenv("XBOW_REDIS_URL")
⋮----
prefix = f"xbow:test:chaos:{uuid4().hex}"
⋮----
queue = RedisJobQueue(url)
⋮----
keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
⋮----
def test_redis_restart_preserves_dedupe_identity(redis_queue)
⋮----
first = redis_queue
created = first.enqueue(
⋮----
restarted = RedisJobQueue(first.url)
recovered = restarted.get_by_dedupe(
⋮----
def test_redis_restart_preserves_terminal_status(redis_queue)
⋮----
claimed = first.claim("worker-before-restart")
⋮----
failed = first.finish(
⋮----
def test_redis_restart_recovers_expired_lease(redis_queue, monkeypatch)
⋮----
claimed = first.claim("dead-worker")
⋮----
old_score = time.time() - 3600
⋮----
recovered = restarted.get(created["id"])
⋮----
replacement = restarted.claim("replacement-worker")
⋮----
def test_redis_restart_keeps_pentagi_out_of_generic_workers(redis_queue)
⋮----
claimed = restarted.claim_kind("pentagi-worker", "pentagi_flow")
⋮----
def test_redis_dedupe_survives_new_client_instances(redis_queue)
⋮----
payload = {
⋮----
second = RedisJobQueue(first.url)
third = RedisJobQueue(first.url)
⋮----
same_second = second.enqueue(
same_third = third.enqueue(
````

## File: backend/tests/test_redis_integration.py
````python
@pytest.fixture
def redis_queue(monkeypatch)
⋮----
url = "redis://localhost:6379/15"
prefix = f"xbow:test:{uuid4().hex}"
⋮----
queue = RedisJobQueue()
⋮----
keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
⋮----
def test_redis_queue_roundtrip(redis_queue)
⋮----
created = redis_queue.enqueue(
⋮----
claimed = redis_queue.claim("worker-a")
⋮----
completed = redis_queue.finish(created["id"], "worker-a", True)
⋮----
def test_redis_queue_dedupe_and_payload_mismatch_fail_closed(redis_queue)
⋮----
payload = {"finding_id": "f1"}
first = redis_queue.enqueue(
second = redis_queue.enqueue(
⋮----
def test_redis_queue_enforces_lease_ownership(redis_queue)
⋮----
job = redis_queue.enqueue("campaign-1", "report", {}, max_attempts=2)
⋮----
current = redis_queue.get(job["id"])
⋮----
def test_redis_queue_retry_budget(redis_queue)
⋮----
first = redis_queue.claim("worker-a")
⋮----
requeued = redis_queue.finish(job["id"], "worker-a", False, "transient")
⋮----
second = redis_queue.claim("worker-b")
⋮----
failed = redis_queue.finish(job["id"], "worker-b", False, "persistent")
````

## File: backend/tests/test_redis_jobqueue_integration.py
````python
@pytest.fixture
def redis_queue(monkeypatch)
⋮----
url = os.getenv("XBOW_REDIS_URL")
⋮----
prefix = f"xbow:test:{uuid4().hex}"
⋮----
queue = RedisJobQueue(url)
⋮----
keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
⋮----
def test_redis_dedupe_survives_adapter_restart(redis_queue)
⋮----
payload = {
first = redis_queue.enqueue(
⋮----
restarted = RedisJobQueue(redis_queue.url)
recovered = restarted.get_by_dedupe(
duplicate = restarted.enqueue(
⋮----
def test_redis_expired_lease_recovery_is_restart_safe(redis_queue, monkeypatch)
⋮----
job = redis_queue.enqueue(
claimed = redis_queue.claim("worker-before-restart")
⋮----
recovered = restarted.get(job["id"])
⋮----
reclaimed = restarted.claim("worker-after-restart")
⋮----
claimed = redis_queue.claim_kind("pentagi-worker-before", "pentagi_flow")
⋮----
reclaimed = restarted.claim_kind("pentagi-worker-after", "pentagi_flow")
⋮----
def test_redis_stats_expose_running_lease_without_worker_identity(redis_queue)
⋮----
claimed = redis_queue.claim("redis-worker-secret-name")
⋮----
stats = redis_queue.stats()
⋮----
def test_redis_heartbeat_renews_only_current_owner(redis_queue)
⋮----
claimed = redis_queue.claim("heartbeat-owner")
⋮----
key = redis_queue._job_key(job["id"])
⋮----
unchanged = redis_queue.get(job["id"])
⋮----
renewed = redis_queue.get(job["id"])
⋮----
def test_redis_stale_worker_cannot_finish_reclaimed_job(redis_queue, monkeypatch)
⋮----
first = redis_queue.claim("worker-before-reclaim")
⋮----
second = redis_queue.claim("worker-after-reclaim")
⋮----
current = redis_queue.get(job["id"])
⋮----
completed = redis_queue.finish(
````

## File: backend/tests/test_redis_jobqueue.py
````python
class DummyRedis
⋮----
def ping(self)
⋮----
def test_redis_queue_rejects_missing_url(monkeypatch)
⋮----
def test_redis_queue_rejects_non_redis_url(monkeypatch)
⋮----
def test_redis_queue_rejects_unsafe_prefix(monkeypatch)
⋮----
def test_redis_queue_health_does_not_expose_configuration(monkeypatch)
⋮----
queue = RedisJobQueue()
⋮----
def test_pentagi_jobs_never_use_generic_redis_queue()
⋮----
class DedupeRedis(DummyRedis)
⋮----
def __init__(self, dedupe_hash, dedupe_key, job_id, job_row)
⋮----
def hget(self, key, field)
⋮----
def hgetall(self, key)
⋮----
def test_redis_get_by_dedupe_uses_index_without_scanning(monkeypatch)
⋮----
probe = RedisJobQueue()
dedupe_hash = probe._dedupe_key("campaign-1", "report")
fake = DedupeRedis(
⋮----
found = queue.get_by_dedupe(
⋮----
class AllowedKindRedis(DummyRedis)
⋮----
def __init__(self)
⋮----
def zrange(self, key, start, end, withscores=False)
⋮----
item = self.scores.get(key)
⋮----
def test_redis_claim_allowed_selects_oldest_kind(monkeypatch)
⋮----
fake = AllowedKindRedis()
⋮----
claimed_kinds = []
⋮----
def fake_claim_kind(worker_id, kind)
⋮----
claimed = queue.claim_allowed(
````

## File: backend/tests/test_report_approval.py
````python
def _campaign() -> Campaign
⋮----
campaign = Campaign(
⋮----
def _artifact() -> dict
⋮----
def _store(tmp_path, campaign: Campaign) -> Storage
⋮----
store = Storage(str(tmp_path / "xbow.sqlite3"), str(tmp_path / "artifacts"))
⋮----
def test_exact_report_and_campaign_state_can_be_approved()
⋮----
campaign = _campaign()
artifact = _artifact()
⋮----
status = approval_status(campaign, artifact)
⋮----
def test_campaign_change_invalidates_existing_approval()
⋮----
def test_report_hash_change_invalidates_existing_approval()
⋮----
artifact = {**artifact, "sha256": "b" * 64}
⋮----
def test_revocation_disables_approval()
⋮----
def test_non_report_artifact_cannot_be_approved()
⋮----
artifact = {**_artifact(), "kind": "http_evidence"}
⋮----
def test_storage_backed_approval_verifies_report_bytes(tmp_path)
⋮----
store = _store(tmp_path, campaign)
artifact = store.put_artifact(
⋮----
event = approval_event_from_storage(
⋮----
status = approval_status_from_storage(campaign, store, artifact["id"])
⋮----
def test_tampered_report_bytes_cannot_be_approved_or_reported_as_approved(tmp_path)
⋮----
metadata = store.get_artifact(campaign.id, artifact["id"])
````

## File: backend/tests/test_report_readiness.py
````python
def _finding(finding_id: str, status: str = "validation_required")
⋮----
def test_report_readiness_blocks_unvalidated_finding()
⋮----
graph = ObservationGraph()
⋮----
item = build_report_readiness([_finding("f1")], graph)[0]
⋮----
def test_report_readiness_requires_complete_independent_evidence()
⋮----
item = build_report_readiness([_finding("f1", "confirmed")], graph)[0]
⋮----
def test_observed_but_unevidenced_validation_remains_blocked()
⋮----
def test_report_readiness_duplicate_requires_review()
⋮----
findings = [_finding("f1", "confirmed"), _finding("f2", "confirmed")]
⋮----
items = build_report_readiness(findings, graph)
⋮----
def test_report_readiness_route_is_exposed()
⋮----
def test_report_readiness_distinguishes_human_review_from_submission_completeness()
⋮----
finding = _finding("f1", "confirmed")
⋮----
item = build_report_readiness([finding], graph)[0]
⋮----
def test_report_readiness_rejects_invalid_cwe_shape_for_submission()
⋮----
def test_review_queue_and_report_readiness_routes_are_registered()
⋮----
paths = app.openapi()["paths"]
````

## File: backend/tests/test_report.py
````python
def _campaign() -> Campaign
⋮----
target = TargetInput(
campaign = Campaign(target=target)
⋮----
def test_hackerone_report_contains_submission_sections()
⋮----
report = render_markdown(_campaign(), platform="hackerone")
⋮----
def test_report_excludes_unconfirmed_findings()
⋮----
campaign = _campaign()
⋮----
report = render_markdown(campaign, platform="bugcrowd")
⋮----
def test_report_marks_high_quality_confirmed_finding_ready_for_review()
⋮----
finding_id = str(campaign.findings[0].id)
⋮----
report = render_markdown(
⋮----
def test_report_holds_confirmed_finding_when_evidence_quality_is_not_high()
````

## File: backend/tests/test_review_queue.py
````python
def test_review_queue_prioritizes_validation_gap_over_surface_review()
⋮----
graph = ObservationGraph()
⋮----
tasks = build_review_queue(graph)
⋮----
def test_review_queue_filters_out_of_scope_work()
⋮----
tasks = build_review_queue(
⋮----
def test_review_queue_is_bounded_and_deterministic()
⋮----
first = build_review_queue(graph, limit=3)
second = build_review_queue(graph, limit=3)
⋮----
def test_review_queue_route_is_exposed_and_advisory(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
result = campaign_review_queue(campaign.id)
⋮----
def test_review_queue_rejects_unbounded_limits()
⋮----
def test_review_queue_boosts_contradictory_hypothesis_validation()
⋮----
baseline = build_review_queue(graph)
boosted = build_review_queue(
⋮----
def test_review_queue_evolving_hypothesis_gets_smaller_bonus()
⋮----
evolving = build_review_queue(
contradictory = build_review_queue(
⋮----
def test_review_queue_exposes_score_components_for_validation_tasks()
⋮----
task = build_review_queue(
⋮----
components = task.to_dict()["score_components"]
⋮----
def test_surface_review_tasks_expose_empty_score_components()
⋮----
task = next(item for item in build_review_queue(graph) if item.kind != "validate_finding")
⋮----
def test_review_queue_severity_component_increases_validation_priority()
⋮----
info = build_review_queue(graph, severities={"f1": "info"})[0]
critical = build_review_queue(graph, severities={"f1": "critical"})[0]
⋮----
def test_review_queue_unknown_severity_fails_closed_to_zero_bonus()
⋮----
task = build_review_queue(graph, severities={"f1": "unexpected"})[0]
````

## File: backend/tests/test_rolling_telemetry.py
````python
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
⋮----
def event(seconds_ago, status="completed", duration_ms=100)
⋮----
def test_rolling_windows_are_time_bounded()
⋮----
result = build_rolling_telemetry(
⋮----
def test_failure_rate_is_computed_per_window()
⋮----
def test_latency_percentiles_use_bounded_durations()
⋮----
durations = result["windows"]["300"]["duration_ms"]
⋮----
def test_future_and_malformed_events_are_ignored()
⋮----
future = event(-10)
malformed = {"type": "worker_outcome", "status": "failed", "at": "bad"}
result = build_rolling_telemetry([future, malformed, event(1)], now=NOW)
⋮----
def test_output_is_redacted()
⋮----
result = build_rolling_telemetry([event(1)], now=NOW)
````

## File: backend/tests/test_runtime_budget_config.py
````python
PLANNER_ENV_NAMES = (
⋮----
def _clear_planner_env(monkeypatch)
⋮----
def test_planner_budget_from_env_uses_safe_defaults(monkeypatch)
⋮----
budget = planner_budget_from_env()
⋮----
def test_planner_budget_from_env_accepts_explicit_limits(monkeypatch)
⋮----
def test_planner_budget_from_env_rejects_invalid_values(monkeypatch, name, value)
⋮----
def test_planner_budget_from_env_rejects_batch_above_total(monkeypatch)
⋮----
def test_campaign_runtime_limit_from_env_uses_default(monkeypatch)
⋮----
limit = campaign_runtime_limit_from_env()
⋮----
def test_campaign_runtime_limit_from_env_accepts_explicit_value(monkeypatch)
⋮----
@pytest.mark.parametrize("value", ["bad", "59", "604801"])
def test_campaign_runtime_limit_from_env_rejects_invalid_values(monkeypatch, value)
⋮----
def test_orchestrator_uses_runtime_limit_from_environment(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = Campaign(
⋮----
result = advance_campaign(campaign, queue, store)
````

## File: backend/tests/test_runtime_capabilities.py
````python
_PENTAGI_FLAGS = (
⋮----
def _clear(monkeypatch)
⋮----
def test_pentagi_capability_defaults_fail_closed(monkeypatch)
⋮----
result = pentagi_runtime_capability()
⋮----
def test_all_operator_gates_still_do_not_claim_pentagi_execution(monkeypatch)
⋮----
def test_status_tracking_requires_integration_and_status_worker(monkeypatch)
⋮----
disabled = pentagi_runtime_capability()
⋮----
enabled = pentagi_runtime_capability()
⋮----
def test_invalid_boolean_configuration_fails_closed(monkeypatch)
⋮----
safe = safe_pentagi_runtime_capability()
⋮----
def test_capabilities_api_exposes_runtime_pentagi_state_without_secrets(monkeypatch)
⋮----
result = main.system_capabilities()
⋮----
execution = result["execution"]
⋮----
def test_capabilities_api_reports_configuration_error_without_raising(monkeypatch)
⋮----
detail = result["execution"]["pentagi_detail"]
⋮----
def test_scanner_runtime_capability_defaults_fail_closed(monkeypatch)
⋮----
result = scanner_runtime_capability()
⋮----
def test_scanner_runtime_capability_reports_ready_only_with_dedicated_profile(monkeypatch)
⋮----
def test_capabilities_api_exposes_scanner_worker_admission(monkeypatch)
⋮----
scanner = result["execution"]["scanner_worker_detail"]
⋮----
def test_scanner_runtime_capability_rejects_unsupported_engine(monkeypatch)
````

## File: backend/tests/test_scan_payload_idempotency.py
````python
def _campaign() -> Campaign
⋮----
def test_scan_payload_ignores_receipt_timestamp()
⋮----
campaign = _campaign()
first = policy_receipt(campaign, "example.test", "automated_scan")
second = {**first, "timestamp": "2099-01-01T00:00:00+00:00"}
⋮----
first_payload = sanitized_scan_payload(campaign, first)
second_payload = sanitized_scan_payload(campaign, second)
⋮----
def test_scan_payload_preserves_policy_decision_fields()
⋮----
receipt = policy_receipt(campaign, "example.test", "automated_scan")
⋮----
payload = sanitized_scan_payload(campaign, receipt)
````

## File: backend/tests/test_scanner_adaptation.py
````python
def _memory(engine, *, successes=0, failures=0, confidence=0.0, success_rate=0.0)
⋮----
def test_adaptation_never_expands_configured_engines()
⋮----
result = adapt_scanner_engines(
⋮----
def test_adaptation_suppresses_repeatedly_failing_engine_when_alternative_exists()
⋮----
def test_adaptation_never_suppresses_last_configured_engine()
⋮----
def test_adaptation_ranks_successful_memory_first()
⋮----
def test_adaptation_rejects_unknown_or_duplicate_configuration()
````

## File: backend/tests/test_scanner_ingestion.py
````python
def _campaign()
⋮----
def test_generic_scanner_ingestion_persists_chain_and_queues_validation(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = _campaign()
⋮----
run = tmp_path / "run"
⋮----
artifact = run / "vulnerabilities.json"
⋮----
result = ingest_scanner_run("strix", run, campaign, queue, store)
⋮----
graph = load_observation_graph(store, campaign.id)
⋮----
def test_generic_scanner_ingestion_is_idempotent(tmp_path)
⋮----
first = ingest_scanner_run("strix", run, campaign, queue, store)
second = ingest_scanner_run("strix", run, campaign, queue, store)
⋮----
def test_generic_scanner_ingestion_handles_missing_artifact(tmp_path)
⋮----
result = ingest_scanner_run("strix", tmp_path / "missing", campaign, queue, store)
⋮----
def test_generic_scanner_ingestion_supports_nuclei_adapter(tmp_path)
⋮----
artifact = run / "nuclei-results.jsonl"
⋮----
result = ingest_scanner_run("nuclei", run, campaign, queue, store)
````

## File: backend/tests/test_scanner_normalization.py
````python
def _campaign()
⋮----
def test_strix_and_nuclei_normalize_to_same_canonical_shape()
⋮----
campaign = _campaign()
strix = normalize_strix_item(
nuclei = normalize_nuclei_item(
⋮----
def test_normalized_ids_are_engine_scoped_and_stable()
⋮----
item = normalize_strix_item(
⋮----
first = normalized_finding_id(item)
second = normalized_finding_id(item)
⋮----
def test_normalizers_fail_closed_outside_scope()
⋮----
def test_nuclei_jsonl_parser_normalizes_deduplicates_and_filters_scope(tmp_path)
⋮----
path = tmp_path / "nuclei.jsonl"
item = {
outside = {
⋮----
findings = parse_nuclei_jsonl(path, _campaign())
⋮----
finding = findings[0]
⋮----
def test_nuclei_jsonl_parser_rejects_invalid_line(tmp_path)
⋮----
def test_nuclei_jsonl_parser_rejects_oversized_file(tmp_path, monkeypatch)
⋮----
def test_scanner_registry_exposes_supported_engines()
⋮----
adapters = scanner_adapters()
⋮----
def test_scanner_registry_rejects_unknown_engine()
⋮----
def test_scanner_registry_dispatches_strix_parser(tmp_path)
⋮----
path = tmp_path / "vulnerabilities.json"
⋮----
findings = parse_scanner_artifact("strix", path, _campaign())
⋮----
def test_scanner_registry_dispatches_nuclei_parser(tmp_path)
⋮----
findings = parse_scanner_artifact("nuclei", path, _campaign())
⋮----
def test_scanner_registry_discovers_artifacts_by_adapter_glob(tmp_path)
⋮----
run = tmp_path / "run"
nested = run / "nested"
⋮----
strix = nested / "vulnerabilities.json"
nuclei = nested / "nuclei-results.jsonl"
⋮----
def test_scanner_registry_rejects_symlinked_artifacts(tmp_path)
⋮----
outside = tmp_path / "outside.json"
⋮----
def test_scanner_registry_selects_latest_artifact(tmp_path)
⋮----
first = run / "a.jsonl"
second = run / "b.jsonl"
⋮----
artifacts = discover_scanner_artifacts("nuclei", run)
⋮----
def test_scanner_registry_missing_run_directory_is_empty(tmp_path)
⋮----
missing = tmp_path / "missing"
````

## File: backend/tests/test_scanner_observation_chain.py
````python
def _campaign()
⋮----
def test_scanner_finding_persists_canonical_asset_endpoint_finding_evidence_chain(tmp_path)
⋮----
campaign = _campaign()
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
⋮----
finding = Finding(
⋮----
finding_observation_id = _record_finding_observation(store, campaign, finding)
records = store.list_observations(campaign.id)
by_id = {item["id"]: item for item in records}
⋮----
finding_record = by_id[finding_observation_id]
endpoint_id = finding_record["parent_ids"][0]
endpoint_record = by_id[endpoint_id]
asset_id = endpoint_record["parent_ids"][0]
asset_record = by_id[asset_id]
⋮----
evidence = [
⋮----
def test_scanner_finding_without_endpoint_links_directly_to_asset(tmp_path)
⋮----
parent = by_id[by_id[finding_observation_id]["parent_ids"][0]]
````

## File: backend/tests/test_scanner_sandbox.py
````python
_NAMES = (
⋮----
def _clear(monkeypatch)
⋮----
def _attest_runtime(monkeypatch, *, rootfs=True, nnp=True, caps=True)
⋮----
def test_scanner_sandbox_defaults_fail_closed(monkeypatch)
⋮----
result = scanner_sandbox_admission("nuclei")
⋮----
def test_restricted_scanner_worker_can_admit_allowlisted_engine(monkeypatch)
⋮----
result = require_scanner_sandbox("nuclei")
⋮----
def test_engine_must_be_explicitly_allowlisted(monkeypatch)
⋮----
def test_invalid_sandbox_boolean_fails_closed(monkeypatch)
⋮----
safe = safe_scanner_sandbox_admission("nuclei")
⋮----
def test_scanner_worker_kill_switch_blocks_execution_admission(monkeypatch)
````

## File: backend/tests/test_scanner_worker.py
````python
def _campaign()
⋮----
def test_scanner_worker_dry_run_stays_ready_and_records_event(tmp_path, monkeypatch)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = _campaign()
⋮----
result = run_strix_job(
⋮----
observations = store.list_observations(campaign.id)
````

## File: backend/tests/test_scope.py
````python
def test_exact_host_allowed()
⋮----
def test_wildcard_subdomain_allowed()
⋮----
def test_unlisted_host_denied()
⋮----
def test_deny_overrides_allow()
⋮----
def test_target_input_rejects_url_userinfo()
⋮----
rules = ProgramRules(
⋮----
def test_target_input_rejects_query_and_fragment(url)
````

## File: backend/tests/test_secret_vault.py
````python
def _master_key()
⋮----
def _configure(monkeypatch, tmp_path)
⋮----
def test_vault_encrypts_secret_at_rest(monkeypatch, tmp_path)
⋮----
path = tmp_path / "secrets.vault.json"
raw = path.read_text(encoding="utf-8")
⋮----
document = json.loads(raw)
⋮----
def test_vault_detects_ciphertext_tampering(monkeypatch, tmp_path)
⋮----
document = json.loads(path.read_text(encoding="utf-8"))
ciphertext = document["secrets"]["audit_hmac_key"]["ciphertext"]
⋮----
def test_vault_rejects_wrong_master_key(monkeypatch, tmp_path)
⋮----
def test_vault_master_key_file_is_supported(monkeypatch, tmp_path)
⋮----
key_file = tmp_path / "master.key"
⋮----
def test_vault_rejects_conflicting_master_key_sources(monkeypatch, tmp_path)
⋮----
def test_resolve_secret_preserves_env_compatibility_when_vault_disabled(monkeypatch)
⋮----
def test_resolve_secret_uses_vault_and_refuses_env_fallback(monkeypatch, tmp_path)
⋮----
document = json.loads((tmp_path / "secrets.vault.json").read_text(encoding="utf-8"))
⋮----
def test_vault_rejects_broad_master_key_permissions(monkeypatch, tmp_path)
⋮----
def test_vault_rejects_broad_existing_vault_permissions(monkeypatch, tmp_path)
⋮----
def _new_master_key()
⋮----
def test_vault_rekey_rotates_all_secrets_atomically(monkeypatch, tmp_path)
⋮----
old_document = (tmp_path / "secrets.vault.json").read_text(encoding="utf-8")
⋮----
result = rekey_vault()
⋮----
new_document = (tmp_path / "secrets.vault.json").read_text(encoding="utf-8")
⋮----
def test_vault_rekey_rolls_back_if_any_entry_is_corrupt(monkeypatch, tmp_path)
⋮----
before = path.read_bytes()
⋮----
def test_vault_rekey_rejects_same_key(monkeypatch, tmp_path)
⋮----
def test_vault_rekey_supports_private_new_key_file(monkeypatch, tmp_path)
⋮----
key_file = tmp_path / "new-master.key"
````

## File: backend/tests/test_storage_backend.py
````python
def test_storage_backend_defaults_to_sqlite(monkeypatch, tmp_path)
⋮----
backend = create_storage()
⋮----
def test_storage_backend_accepts_sqlite_alias(monkeypatch, tmp_path)
⋮----
def test_storage_backend_normalizes_postgres_alias(monkeypatch)
⋮----
def test_storage_backend_requires_postgres_url(monkeypatch)
⋮----
def test_storage_backend_rejects_unknown_backend(monkeypatch)
````

## File: backend/tests/test_storage.py
````python
def test_campaign_roundtrip_and_artifact_hash(tmp_path)
⋮----
db = tmp_path / "xbow.sqlite3"
artifacts = tmp_path / "artifacts"
store = Storage(str(db), str(artifacts))
campaign = {
⋮----
artifact = store.put_artifact("c1", "http_evidence", b"evidence", media_type="text/plain")
⋮----
listed = store.list_artifacts("c1")
⋮----
def test_campaign_versions_reject_stale_snapshot(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
campaign = {"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"}
⋮----
first = store.get_campaign_record("c1")
second = store.get_campaign_record("c1")
⋮----
current = store.get_campaign_record("c1")
⋮----
def test_campaign_create_rejects_impossible_expected_version(tmp_path)
⋮----
def test_observation_graph_roundtrip_and_parent_integrity(tmp_path)
⋮----
asset = store.put_observation(
endpoint = store.put_observation(
⋮----
rows = store.list_observations("c1")
⋮----
def test_observation_rejects_unknown_parent_and_conflicting_identity(tmp_path)
⋮----
first = {"id": "a1", "kind": "asset", "value": "example.com", "source": "scope"}
⋮----
def test_artifact_kind_fails_closed(tmp_path)
⋮----
def test_artifact_read_detects_tampering(tmp_path)
⋮----
root = tmp_path / "artifacts"
store = Storage(str(tmp_path / "db.sqlite3"), str(root))
⋮----
artifact = store.put_artifact("c1", "validation", b"trusted")
metadata = store.get_artifact("c1", artifact["id"])
⋮----
def test_artifact_lookup_is_campaign_scoped(tmp_path)
⋮----
artifact = store.put_artifact("c1", "validation", b"evidence", finding_id="f1")
⋮----
def test_idempotency_key_returns_existing_artifact(tmp_path)
⋮----
first = store.put_artifact("c1", "validation", b"same", idempotency_key="job-1:validation")
second = store.put_artifact("c1", "validation", b"same", idempotency_key="job-1:validation")
⋮----
def test_idempotency_key_rejects_different_content(tmp_path)
⋮----
def test_artifact_write_rejects_path_traversal_campaign_id(tmp_path)
⋮----
campaign_id = "../escape"
⋮----
def test_artifact_write_rejects_symlinked_campaign_directory(tmp_path)
⋮----
outside = tmp_path / "outside"
⋮----
campaign_dir = root / "c1"
⋮----
def test_invalid_artifact_size_configuration_fails_closed(tmp_path, monkeypatch)
⋮----
def test_artifact_size_configuration_rejects_unsafe_bounds(tmp_path, monkeypatch)
⋮----
def test_artifact_media_type_rejects_header_controls(tmp_path)
⋮----
def test_artifact_file_permissions_are_private(tmp_path)
⋮----
artifact = store.put_artifact("c1", "validation", b"private")
⋮----
mode = stat.S_IMODE((root / metadata["relative_path"]).stat().st_mode)
⋮----
def test_artifact_file_is_removed_when_metadata_insert_fails(tmp_path, monkeypatch)
⋮----
original_connect = store.connect
calls = 0
⋮----
@contextmanager
    def flaky_connect()
⋮----
def test_artifact_idempotency_key_rejects_unsafe_values(tmp_path)
⋮----
invalid = (
⋮----
def test_storage_rejects_invalid_identifiers(tmp_path)
⋮----
def test_has_artifact_validates_filters(tmp_path)
⋮----
@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_storage_permissions_are_private_on_posix(tmp_path)
⋮----
db = tmp_path / "db.sqlite3"
⋮----
store = Storage(str(db), str(root))
⋮----
def test_observation_persistence_is_bounded(tmp_path, monkeypatch)
⋮----
def test_observation_parent_count_is_bounded(tmp_path)
⋮----
parents = tuple(f"p:{index}" for index in range(65))
⋮----
def test_invalid_observation_size_limit_fails_closed(tmp_path, monkeypatch)
⋮----
def test_campaign_document_persistence_is_bounded(tmp_path, monkeypatch)
⋮----
document = {
⋮----
def test_invalid_campaign_document_limit_fails_closed(tmp_path, monkeypatch)
⋮----
document = {"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"}
⋮----
def test_idempotency_key_rejects_metadata_mismatch(tmp_path)
⋮----
def test_observation_rejects_non_serializable_metadata(tmp_path)
⋮----
def test_hypothesis_snapshot_persistence_is_idempotent(tmp_path)
⋮----
snapshot = [{"id": "hypothesis:f1", "finding_id": "f1", "confidence": 0.35}]
⋮----
first = store.put_hypothesis_snapshot("c1", "abc123", snapshot)
second = store.put_hypothesis_snapshot("c1", "abc123", snapshot)
⋮----
def test_hypothesis_snapshot_rejects_fingerprint_collision(tmp_path)
⋮----
def test_hypothesis_snapshot_history_is_campaign_scoped(tmp_path)
⋮----
def test_advisory_focus_snapshot_persistence_is_idempotent(tmp_path)
⋮----
advisory = {"focus_finding_id": "f1", "focus": [{"rank": 1, "finding_id": "f1"}]}
⋮----
first = store.put_advisory_focus_snapshot("c1", "fp1", advisory)
second = store.put_advisory_focus_snapshot("c1", "fp1", advisory)
⋮----
def test_advisory_focus_snapshot_rejects_fingerprint_collision(tmp_path)
⋮----
def test_advisory_focus_history_is_campaign_scoped(tmp_path)
⋮----
def test_storage_health_reports_sqlite_ready(tmp_path)
⋮----
result = store.health()
````

## File: backend/tests/test_submission_api.py
````python
def _setup(tmp_path, monkeypatch, *, report_ready=True)
⋮----
db = str(tmp_path / "db.sqlite3")
artifacts = str(tmp_path / "artifacts")
⋮----
campaign = Campaign(
store = Storage(db, artifacts)
⋮----
artifact = store.put_artifact(campaign.id, "report", b"report", media_type="text/markdown")
⋮----
def test_submission_routes_are_mounted()
⋮----
paths = set(app.openapi()["paths"])
expected = {
⋮----
def test_campaign_submission_overview_counts_states(tmp_path, monkeypatch)
⋮----
before = submission_api.list_submission_states(campaign.id)
⋮----
after = submission_api.list_submission_states(campaign.id)
⋮----
def test_submission_api_requires_approval(tmp_path, monkeypatch)
⋮----
def test_approve_then_mark_submitted_is_idempotent(tmp_path, monkeypatch)
⋮----
approved = submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
submitted = submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")
repeated = submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")
⋮----
def test_conflicting_submission_metadata_is_rejected(tmp_path, monkeypatch)
⋮----
def test_revocation_reblocks_submission_state(tmp_path, monkeypatch)
⋮----
status = submission_api.get_submission_state(campaign.id, artifact["id"])
⋮----
def test_reapproval_requires_new_manual_submission(tmp_path, monkeypatch)
⋮----
reapproved = submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
⋮----
resubmitted = submission_api.mark_report_submitted(
⋮----
def test_non_report_artifact_is_rejected(tmp_path, monkeypatch)
⋮----
store = Storage()
evidence = store.put_artifact(campaign.id, "http_evidence", b"evidence")
⋮----
def test_tampered_report_is_rejected(tmp_path, monkeypatch)
⋮----
metadata = store.get_artifact(campaign.id, artifact["id"])
⋮----
def test_report_approval_rejects_confirmed_finding_without_ready_evidence(tmp_path, monkeypatch)
⋮----
def test_submission_mutations_preserve_campaign_audit_chain(tmp_path, monkeypatch)
⋮----
persisted = Storage().get_campaign(campaign.id)
verification = verify_campaign_event_chain(persisted["events"])
````

## File: backend/tests/test_submission_state.py
````python
def _campaign() -> Campaign
⋮----
campaign = Campaign(
⋮----
def _artifact() -> dict
⋮----
def test_report_starts_as_draft()
⋮----
status = submission_status(_campaign(), _artifact())
⋮----
def test_current_human_approval_unlocks_submission()
⋮----
campaign = _campaign()
artifact = _artifact()
⋮----
status = assert_submission_allowed(campaign, artifact)
⋮----
def test_submission_is_recorded_only_after_approval()
⋮----
status = submission_status(campaign, artifact)
⋮----
def test_revocation_without_submission_requires_review()
⋮----
def test_revocation_reblocks_previously_submitted_report()
⋮----
def test_reapproval_does_not_resurrect_old_submission()
⋮----
def test_new_submission_after_reapproval_counts_for_current_cycle()
⋮----
def test_campaign_change_makes_approval_stale_and_reblocks_submission()
⋮----
def test_unapproved_submission_attempt_is_rejected()
⋮----
def test_submission_event_requires_complete_metadata()
⋮----
invalid = (
````

## File: backend/tests/test_swarm_coordinator.py
````python
def _tasks()
⋮----
graph = ObservationGraph()
⋮----
def test_swarm_coordinator_preserves_capability_boundaries()
⋮----
result = coordinate_recon_swarm(_tasks())
⋮----
def test_swarm_coordinator_shares_request_budget_across_agents()
⋮----
tasks = _tasks()
result = coordinate_recon_swarm(
⋮----
def test_swarm_coordinator_limits_agent_fanout()
⋮----
def test_swarm_coordinator_fails_closed_on_agent_mismatch()
⋮----
bad = ReconTask(
⋮----
def test_swarm_coordinator_rejects_capability_escalation()
⋮----
def test_swarm_budget_validation_is_fail_closed()
⋮----
def test_swarm_coordinator_uses_central_agent_registry(monkeypatch)
⋮----
original = swarm_coordinator.agent_by_name
⋮----
def fake_agent_by_name(name)
⋮----
profile = original(name)
````

## File: backend/tests/test_totp_auth.py
````python
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
⋮----
def _request(method="POST", headers=None)
⋮----
raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
⋮----
def _clear(monkeypatch)
⋮----
def test_totp_matches_rfc6238_sha1_vector(monkeypatch)
⋮----
secret = configured_totp_secret()
⋮----
def test_totp_disabled_preserves_mutating_api_compatibility(monkeypatch)
⋮----
def test_totp_enabled_requires_code_for_mutation(monkeypatch)
⋮----
def test_totp_enabled_does_not_require_code_for_get(monkeypatch)
⋮----
def test_totp_rejects_invalid_code(monkeypatch)
⋮----
def test_totp_accepts_adjacent_time_step(monkeypatch)
⋮----
code = _totp(secret, 2)
⋮----
def test_totp_vault_secret_is_supported(monkeypatch, tmp_path)
⋮----
def test_totp_vault_mode_refuses_env_fallback(monkeypatch, tmp_path)
⋮----
def test_control_middleware_requires_token_and_totp_for_mutation(monkeypatch)
⋮----
token = "control-token-" + "x" * 32
⋮----
code = _totp(secret, 1)
⋮----
async def call_next(_request)
⋮----
result = asyncio.run(
⋮----
def test_invalid_totp_configuration_fails_closed(monkeypatch)
⋮----
def test_totp_code_is_single_use_in_memory_backend(monkeypatch)
⋮----
def test_totp_replay_state_expires_after_window(monkeypatch)
⋮----
first = _totp(configured_totp_secret(), 1)
later = _totp(configured_totp_secret(), 5)
⋮----
def test_totp_replay_backend_invalid_fails_closed(monkeypatch)
⋮----
code = _totp(configured_totp_secret(), 1)
````

## File: backend/tests/test_validation_state.py
````python
def _graph(validation_value="observed", validation_source="validator")
⋮----
graph = ObservationGraph()
⋮----
def test_observed_independent_validation_is_recognized()
⋮----
graph = _graph()
⋮----
def test_self_validation_does_not_count_as_independent()
⋮----
graph = _graph(validation_source="scanner")
⋮----
def test_non_observed_attempt_counts_only_as_attempt()
⋮----
graph = _graph(validation_value="dry_run")
state = analyze_validation_state(graph)
⋮----
def test_unattempted_finding_is_exposed_explicitly()
⋮----
def test_empty_graph_is_not_treated_as_fully_validated()
⋮----
state = analyze_validation_state(ObservationGraph())
⋮----
def test_mixed_validation_states_remain_finding_specific()
⋮----
def test_multiple_attempts_can_upgrade_to_observed_independent_state()
⋮----
def test_non_finding_validation_parent_is_ignored()
⋮----
def test_observed_validation_without_child_evidence_is_not_evidence_backed()
⋮----
def test_evidence_child_of_independent_observed_validation_is_evidence_backed()
⋮----
def test_evidence_attached_directly_to_finding_does_not_count()
⋮----
def test_evidence_on_self_validation_does_not_count_as_independent()
````

## File: backend/tests/test_validator.py
````python
def campaign() -> Campaign
⋮----
def finding(**kwargs) -> Finding
⋮----
data = {
⋮----
class _Response
⋮----
def __init__(self, body: bytes, *, status: int = 200, content_type: str = "text/plain")
⋮----
def __enter__(self)
⋮----
def __exit__(self, exc_type, exc, tb)
⋮----
def read(self, _limit: int) -> bytes
⋮----
class _EchoingOpener
⋮----
def __init__(self, *, baseline_body: bytes = b"baseline")
⋮----
def open(self, request, timeout=None)
⋮----
url = request.full_url
⋮----
values = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
⋮----
def test_probe_resolves_relative_endpoint_inside_scope()
⋮----
def test_probe_rejects_out_of_scope_endpoint()
⋮----
def test_probe_rejects_denied_host_even_if_related()
⋮----
def test_http_validation_is_dry_run_by_default(monkeypatch)
⋮----
result = safe_http_probe(campaign(), finding())
⋮----
payload = json.loads(result.json_bytes())
⋮----
def test_invalid_http_validation_flag_fails_closed(monkeypatch)
⋮----
def test_invalid_http_validator_limits_fail_closed(monkeypatch, name, value, message)
⋮----
def test_explicit_false_http_validation_flag_remains_dry_run(monkeypatch)
⋮----
def test_validation_evidence_redacts_query_values(monkeypatch)
⋮----
result = safe_http_probe(
⋮----
def test_validation_preview_is_text_only_and_bounded(monkeypatch)
⋮----
def test_invalid_validation_preview_limit_fails_closed(monkeypatch)
⋮----
def test_differential_validation_uses_inert_marker_on_existing_query_parameter(monkeypatch)
⋮----
opener = _EchoingOpener()
⋮----
sleeps: list[float] = []
⋮----
serialized = json.dumps(payload, sort_keys=True)
⋮----
def test_active_validation_redacts_query_values_reflected_in_body_preview(monkeypatch)
⋮----
opener = _EchoingOpener(baseline_body=b"echoed private-value and 42")
⋮----
def test_differential_validation_does_not_invent_query_parameters(monkeypatch)
⋮----
result = safe_http_probe(campaign(), finding(endpoint="/account"))
⋮----
def test_invalid_differential_validation_gate_fails_closed_before_network(monkeypatch)
````

## File: backend/tests/test_watchdog_observability.py
````python
class Queue
⋮----
def health(self)
⋮----
def stats(self)
⋮----
class Store
⋮----
artifact_root = None
⋮----
def list_campaigns(self)
⋮----
def test_metrics_include_watchdog(monkeypatch)
⋮----
result = build_operational_metrics(Queue(), Store())
⋮----
def test_invalid_watchdog_config_is_redacted_error(monkeypatch)
⋮----
def test_readiness_fails_on_critical_watchdog(monkeypatch, tmp_path)
⋮----
queue = Queue()
store = Store()
⋮----
def stale_stats()
⋮----
result = queue.stats()
⋮----
result = readiness_module.readiness()
````

## File: backend/tests/test_worker_concurrency.py
````python
def make_campaign() -> Campaign
⋮----
def test_worker_save_rejects_stale_campaign_snapshot(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
campaign = make_campaign()
⋮----
def test_worker_poll_interval_is_bounded(monkeypatch)
⋮----
def test_validation_worker_rejects_resolved_finding_before_probe(tmp_path)
⋮----
job = {
⋮----
def test_validation_worker_rejects_completed_campaign_before_probe(tmp_path)
⋮----
def test_stale_validation_job_is_cancelled_without_retry(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
⋮----
job = queue.enqueue(
⋮----
final = queue.get(job["id"])
⋮----
def test_completed_campaign_validation_job_is_cancelled_without_retry(tmp_path)
⋮----
def test_completed_campaign_browser_job_is_cancelled_without_retry(tmp_path)
````

## File: backend/tests/test_worker_job_provenance.py
````python
def _runtime(tmp_path)
⋮----
db = str(tmp_path / "db.sqlite3")
store = Storage(db, str(tmp_path / "artifacts"))
queue = JobQueue(db)
campaign = Campaign(
⋮----
def _stub_execution(monkeypatch)
⋮----
def test_worker_rejects_governed_job_when_policy_fingerprint_is_stale(tmp_path, monkeypatch)
⋮----
payload = attach_job_provenance(
job = queue.enqueue(
⋮----
current = Campaign.model_validate(raw)
⋮----
final = queue.get(job["id"])
⋮----
def test_worker_rejects_unprovenanced_governed_job_by_default(tmp_path, monkeypatch)
⋮----
def test_worker_legacy_flag_allows_unprovenanced_governed_job(tmp_path, monkeypatch)
````

## File: backend/tests/test_worker_observations.py
````python
def test_worker_observation_lineage_roundtrips(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
⋮----
campaign = SimpleNamespace(id="c1")
finding = Finding(
⋮----
finding_observation_id = _record_finding_observation(store, campaign, finding)
artifact = store.put_artifact(
validation_id = _record_artifact_observation(
evidence_id = _record_artifact_observation(
⋮----
graph = load_observation_graph(store, "c1")
⋮----
endpoint_id = graph.by_kind("endpoint")[0].id
asset_id = graph.by_kind("asset")[0].id
````

## File: backend/tests/test_worker_outcome_memory.py
````python
def _campaign()
⋮----
def test_record_worker_outcome_is_idempotent_and_payload_free(tmp_path)
⋮----
store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
campaign = _campaign()
⋮----
job = {
⋮----
saved = store.get_campaign(campaign.id)
outcomes = [event for event in saved["events"] if event.get("type") == "worker_outcome"]
⋮----
def test_worker_outcome_audit_detects_tampering(tmp_path)
⋮----
result = verify_worker_audit_chain(saved["events"])
⋮----
def test_worker_outcome_audit_links_multiple_events(tmp_path)
⋮----
def test_worker_outcome_extends_existing_campaign_audit_chain(tmp_path)
⋮----
def test_worker_event_helper_seals_and_deduplicates_campaign_event()
⋮----
event = {
````

## File: backend/tests/test_worker_parser.py
````python
def campaign()
⋮----
def test_parser_normalizes_and_filters_scope(tmp_path)
⋮----
path = tmp_path / "vulnerabilities.json"
⋮----
findings = parse_strix_vulnerabilities(path, campaign())
⋮----
def test_parser_uses_stable_ids_and_deduplicates_same_result(tmp_path)
⋮----
item = {
⋮----
first = parse_strix_vulnerabilities(path, campaign())
second = parse_strix_vulnerabilities(path, campaign())
⋮----
def test_locator_rejects_symlink_escape(tmp_path)
⋮----
run = tmp_path / "run"
⋮----
outside = tmp_path / "outside.json"
⋮----
def test_parser_rejects_oversized_json(tmp_path, monkeypatch)
⋮----
def test_invalid_strix_size_limit_fails_closed(tmp_path, monkeypatch)
⋮----
def test_active_scan_rejects_campaign_rate_above_autonomous_cap(monkeypatch)
⋮----
def test_dry_run_does_not_require_active_rate_admission(monkeypatch)
⋮----
plan = build_strix_plan(campaign())
⋮----
def test_invalid_active_rate_cap_fails_closed(monkeypatch)
⋮----
def test_strix_plan_exposes_rate_admission_telemetry(monkeypatch)
⋮----
def test_dry_run_rate_telemetry_does_not_claim_active_cap(monkeypatch)
⋮----
def test_invalid_worker_boolean_fails_closed(monkeypatch, name, value)
⋮----
def test_worker_boolean_parser_accepts_explicit_common_values(monkeypatch)
⋮----
def test_strix_output_dir_must_stay_under_run_root(tmp_path, monkeypatch)
⋮----
root = tmp_path / "runs"
⋮----
def test_strix_output_dir_rejects_symlink(tmp_path, monkeypatch)
⋮----
outside = tmp_path / "outside"
⋮----
link = root / "job"
⋮----
def test_strix_output_dir_accepts_child_of_run_root(tmp_path, monkeypatch)
⋮----
plan = build_strix_plan(campaign(), str(root / "job-1"))
⋮----
def test_non_integer_worker_limits_fail_closed(monkeypatch, tmp_path, name, value, message)
````

## File: backend/tests/test_worker_roles.py
````python
class FakeQueue
⋮----
def __init__(self)
⋮----
def claim(self, worker_id)
⋮----
def claim_allowed(self, worker_id, kinds)
⋮----
def test_general_worker_keeps_scanner_preview_jobs_in_safe_mode(monkeypatch)
⋮----
queue = FakeQueue()
⋮----
def test_general_worker_excludes_scanner_jobs_for_active_execution(monkeypatch)
⋮----
def test_scanner_worker_claims_only_scanner_jobs(monkeypatch)
````

## File: backend/tests/test_worker_secrets.py
````python
def _clear(monkeypatch)
⋮----
def _configure_vault(monkeypatch, tmp_path)
⋮----
def test_worker_env_preserves_legacy_provider_secrets_when_vault_disabled(monkeypatch)
⋮----
env = _worker_env()
⋮----
def test_worker_env_loads_scanner_secrets_from_vault(monkeypatch, tmp_path)
⋮----
def test_worker_env_keeps_unused_vault_secrets_optional(monkeypatch, tmp_path)
⋮----
def test_worker_env_refuses_legacy_secret_fallback_when_vault_enabled(monkeypatch, tmp_path)
⋮----
def test_worker_env_does_not_inherit_unrelated_secrets(monkeypatch)
````

## File: backend/tests/test_worker_state.py
````python
def _campaign(findings)
⋮----
def _finding(status)
⋮----
def test_post_scan_state_stays_validating_for_known_unresolved_finding()
⋮----
campaign = _campaign([_finding("validation_required")])
⋮----
def test_post_scan_state_completes_only_when_all_findings_are_resolved()
⋮----
campaign = _campaign([_finding("confirmed"), _finding("rejected")])
⋮----
def test_post_scan_state_completes_when_scan_has_no_findings()
````

## File: backend/tests/test_worker_watchdog.py
````python
_ENV = (
⋮----
def _clear(monkeypatch)
⋮----
def test_watchdog_ok_for_healthy_aggregate_metrics(monkeypatch)
⋮----
result = build_worker_watchdog({
⋮----
def test_watchdog_detects_stalled_queue(monkeypatch)
⋮----
def test_watchdog_detects_stale_running_lease(monkeypatch)
⋮----
def test_watchdog_enforces_failed_job_budget(monkeypatch)
⋮----
def test_watchdog_invalid_threshold_fails_closed(monkeypatch)
````

## File: frontend/app.js
````javascript
const $=id
const lines=id
const clamp=(v,min,max)
const fmtSeconds=value=>{
  const seconds=Math.max(0,Number(value)||0);
⋮----
async function api(path,opts=
⋮----
function setStatus(message,type='muted')
⋮----
function budgetRow(label,used,limit)
⋮----
function renderControl(data)
⋮----
function readinessClass(value)
⋮----
function visibleFindings(data)
⋮----
function renderClusters(data)
⋮----
function renderReviewAndSubmission(reviewQueue, reportReadiness)
⋮----
function renderDecisionTimeline(data)
⋮----
function renderFindingIntelligence(data)
⋮----
async function refreshDashboard()
⋮----
async function activateCampaign(value)
⋮----
$('load').onclick=async()=>
⋮----
$('refresh').onclick=async()=>
⋮----
$('create').onclick=async()=>
⋮----
$('start').onclick=async()=>
⋮----
$('resetBreaker').onclick=async()=>
````

## File: frontend/hackerone.js
````javascript
const el=id
const splitLines=value
⋮----
function setLauncherStatus(message,type='muted')
⋮----
function parseScopeDocument()
⋮----
function reviewedAtIso()
⋮----
function buildPolicy()
⋮----
function buildPayload()
⋮----
function conservativeBlockers(policy)
⋮----
function payloadFingerprint(payload)
⋮----
function invalidatePreview()
⋮----
function renderScopeList(targetId,values,emptyLabel)
⋮----
function renderPreview(preview,payload,blockers)
⋮----
async function preview()
⋮----
async function launch()
⋮----
async function importScopeFile()
````

## File: frontend/sw.js
````javascript

````

## File: .repo-standards.yml
````yaml
source: dbrckk/repo-standards
ref: v7
version: 7
adopted: true
workflow_mode: unified-single-commit
repo_brain: dbrckk/repo-brain@v2
ai_context:
  index: .ai/index.md
  project_state: .ai/project-state.md
  change_impact: .ai/change-impact.md
  architecture: .ai/architecture.json
  dependency_map: .ai/dependency-map.json
  commands: .ai/commands.json
  ci_status: .ai/ci-status.md
  security_signals: .ai/security-signals.json
  repo_health: .ai/repo-health.md
  brain_summary: .ai/brain/summary.md
  brain_lookup: .ai/brain/lookup.json
  brain_symbols: .ai/brain/symbols.json
  brain_graph: .ai/brain/code-graph.json
  repo_map: .ai/repo-map.md
  segmented_maps: .ai/maps/
workflow:
  file: .github/workflows/ai-repo-map.yml
  reusable_unified: .github/workflows/reusable-unified.yml
````

## File: AGENTS.md
````markdown
# Repository agent instructions

This repository adopts shared standards from `dbrckk/repo-standards` at the release recorded in `.repo-standards.yml`.

Before substantial work:
1. Read the central `AGENTS.md` and relevant standards at the configured ref.
2. Read `.ai/project-state.md`.
3. Read `.ai/change-impact.md`.
4. Read `.ai/architecture.json`.
5. Read `.ai/brain/summary.md`.
6. Search `.ai/brain/lookup.json` for named symbols before broad source exploration.
7. Use `.ai/brain/code-graph.json` and `.ai/brain/imports.json` for cross-module context.
8. Read `.ai/dependency-map.json` when dependency context matters.
9. Read `.ai/commands.json`, `.ai/ci-status.md`, and security signals when relevant.
10. Read `.ai/repo-health.md`.
11. Use `.ai/index.md` and segmented maps only if symbol-level context is insufficient.
12. Read `.ai/repo-map.md` only as a final broad-context fallback.
13. Fetch only task-relevant source files or line ranges.

Repository-specific rules:
- Preserve existing architecture and public interfaces unless the task requires a change.
- Prefer the smallest coherent change.
- Verify Repo Brain symbol hits against authoritative source before editing.
- Run relevant tests, lint, build, or validation commands before declaring completion.
- Treat security signals and static graph edges as heuristics, not proof.
- Never reproduce suspected secret values.
- Update manual project-state sections when status, blockers, or next priority materially changes.
````

## File: docker-compose.distributed.yml
````yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${XBOW_POSTGRES_DB:-xbow}
      POSTGRES_USER: ${XBOW_POSTGRES_USER:-xbow}
      POSTGRES_PASSWORD: ${XBOW_POSTGRES_PASSWORD:?set XBOW_POSTGRES_PASSWORD}
    volumes:
      - xbow-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${XBOW_POSTGRES_USER:-xbow} -d ${XBOW_POSTGRES_DB:-xbow}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    security_opt:
      - no-new-privileges:true
    networks: [control]

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    environment:
      REDIS_PASSWORD: ${XBOW_REDIS_PASSWORD:?set XBOW_REDIS_PASSWORD}
    command:
      - sh
      - -c
      - exec redis-server --appendonly yes --requirepass "$$REDIS_PASSWORD"
    volumes:
      - xbow-redis:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$$REDIS_PASSWORD\" ping | grep -q PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s
    security_opt:
      - no-new-privileges:true
    networks: [control]

  backend:
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      XBOW_STORAGE_BACKEND: postgresql
      XBOW_DATABASE_URL: ${XBOW_DATABASE_URL:?set XBOW_DATABASE_URL}
      XBOW_QUEUE_BACKEND: redis
      XBOW_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}
      XBOW_API_RATE_LIMIT_BACKEND: redis
      XBOW_API_RATE_LIMIT_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}
      XBOW_TOTP_REPLAY_BACKEND: redis
      XBOW_TOTP_REPLAY_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}

  worker:
    depends_on:
      backend:
        condition: service_healthy
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      XBOW_STORAGE_BACKEND: postgresql
      XBOW_DATABASE_URL: ${XBOW_DATABASE_URL:?set XBOW_DATABASE_URL}
      XBOW_QUEUE_BACKEND: redis
      XBOW_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}


  scanner-worker:
    depends_on:
      backend:
        condition: service_healthy
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      XBOW_STORAGE_BACKEND: postgresql
      XBOW_DATABASE_URL: ${XBOW_DATABASE_URL:?set XBOW_DATABASE_URL}
      XBOW_QUEUE_BACKEND: redis
      XBOW_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}



  pentagi-worker:
    depends_on:
      backend:
        condition: service_healthy
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      XBOW_STORAGE_BACKEND: postgresql
      XBOW_DATABASE_URL: ${XBOW_DATABASE_URL:?set XBOW_DATABASE_URL}
      XBOW_QUEUE_BACKEND: redis
      XBOW_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}

  pentagi-status-worker:
    depends_on:
      backend:
        condition: service_healthy
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      XBOW_STORAGE_BACKEND: postgresql
      XBOW_DATABASE_URL: ${XBOW_DATABASE_URL:?set XBOW_DATABASE_URL}
      XBOW_QUEUE_BACKEND: redis
      XBOW_REDIS_URL: ${XBOW_REDIS_URL:?set XBOW_REDIS_URL}

volumes:
  xbow-postgres:
  xbow-redis:
````

## File: docker-compose.tls.yml
````yaml
services:
  tls-proxy:
    image: caddy:2.11.4-alpine
    restart: unless-stopped
    environment:
      XBOW_PUBLIC_HOST: ${XBOW_PUBLIC_HOST:?set XBOW_PUBLIC_HOST}
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - xbow-caddy-data:/data
      - xbow-caddy-config:/config
    read_only: true
    tmpfs:
      - /tmp:size=32m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    pids_limit: 128
    mem_limit: 256m
    cpus: 0.5
    depends_on:
      frontend:
        condition: service_started
    networks:
      control:
        ipv4_address: 172.30.0.11

  frontend:
    ports: !override []
    networks:
      control:
        ipv4_address: 172.30.0.10

  backend:
    environment:
      XBOW_TRUSTED_PROXY_CIDRS: 172.30.0.10/32,172.30.0.11/32

volumes:
  xbow-caddy-data:
  xbow-caddy-config:

networks:
  control:
    ipam:
      config:
        - subnet: 172.30.0.0/24
````

## File: docker-compose.yml
````yaml
services:
  backend:
    build: ./backend
    restart: unless-stopped
    init: true
    stop_grace_period: 20s
    environment:
      DRY_RUN: ${DRY_RUN:-true}
      XBOW_API_TOKEN: ${XBOW_API_TOKEN:-}
      XBOW_DB_PATH: /data/xbow.sqlite3
      XBOW_ARTIFACT_ROOT: /data/artifacts
      XBOW_MAX_JOB_PAYLOAD_BYTES: ${XBOW_MAX_JOB_PAYLOAD_BYTES:-65536}
      XBOW_MAX_OBSERVATION_BYTES: ${XBOW_MAX_OBSERVATION_BYTES:-65536}
      XBOW_MAX_CAMPAIGN_DOCUMENT_BYTES: ${XBOW_MAX_CAMPAIGN_DOCUMENT_BYTES:-2097152}
      XBOW_ALERT_QUEUE_AGE_SECONDS: ${XBOW_ALERT_QUEUE_AGE_SECONDS:-300}
      XBOW_ALERT_PENDING_OUTBOX: ${XBOW_ALERT_PENDING_OUTBOX:-20}
      XBOW_ALERT_OUTBOX_AGE_SECONDS: ${XBOW_ALERT_OUTBOX_AGE_SECONDS:-300}
      XBOW_ALERT_WEBHOOK_URL: ${XBOW_ALERT_WEBHOOK_URL:-}
      XBOW_ALERT_WEBHOOK_TIMEOUT_SECONDS: ${XBOW_ALERT_WEBHOOK_TIMEOUT_SECONDS:-5}
      XBOW_ALERT_WEBHOOK_HMAC_KEY: ${XBOW_ALERT_WEBHOOK_HMAC_KEY:-}
      XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}
      XBOW_SCAN_ENGINES: ${XBOW_SCAN_ENGINES:-nuclei}
      XBOW_ENABLE_SCANNER_WORKER: ${XBOW_ENABLE_SCANNER_WORKER:-false}
      XBOW_ENABLE_NUCLEI: ${XBOW_ENABLE_NUCLEI:-false}
      XBOW_SCANNER_SANDBOX_PROFILE: ${XBOW_SCANNER_SANDBOX_PROFILE:-restricted-v1}
      XBOW_SCANNER_ALLOWED_ENGINES: ${XBOW_SCANNER_ALLOWED_ENGINES:-nuclei}
      XBOW_NUCLEI_ALLOWED_VERSION: ${XBOW_NUCLEI_ALLOWED_VERSION:-}
      XBOW_ENABLE_PENTAGI: ${XBOW_ENABLE_PENTAGI:-false}
      XBOW_ENABLE_PENTAGI_WORKER: ${XBOW_ENABLE_PENTAGI_WORKER:-false}
      XBOW_ENABLE_PENTAGI_TRANSPORT: ${XBOW_ENABLE_PENTAGI_TRANSPORT:-false}
      XBOW_ENABLE_PENTAGI_STATUS_WORKER: ${XBOW_ENABLE_PENTAGI_STATUS_WORKER:-false}
      XBOW_PENTAGI_BASE_URL: ${XBOW_PENTAGI_BASE_URL:-}
      XBOW_PENTAGI_MODEL_PROVIDER: ${XBOW_PENTAGI_MODEL_PROVIDER:-}
      XBOW_PENTAGI_MAX_ADMISSION_RPS: ${XBOW_PENTAGI_MAX_ADMISSION_RPS:-2.0}
    volumes:
      - xbow-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=64m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 512m
    cpus: 1.0
    healthcheck:
      test: ["CMD", "python", "-m", "app.readiness"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks: [control]

  worker:
    build: ./backend
    command: ["python", "-m", "app.worker_service"]
    restart: unless-stopped
    init: true
    stop_grace_period: 30s
    depends_on:
      backend:
        condition: service_healthy
    environment:
      DRY_RUN: ${DRY_RUN:-true}
      XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}
      XBOW_ENABLE_HTTP_VALIDATION: ${XBOW_ENABLE_HTTP_VALIDATION:-false}
      XBOW_ENABLE_DIFFERENTIAL_VALIDATION: ${XBOW_ENABLE_DIFFERENTIAL_VALIDATION:-false}
      XBOW_ENABLE_BROWSER_AUTOMATION: ${XBOW_ENABLE_BROWSER_AUTOMATION:-false}
      XBOW_VALIDATION_PREVIEW_CHARS: ${XBOW_VALIDATION_PREVIEW_CHARS:-4096}
      WORKER_TIMEOUT_SECONDS: ${WORKER_TIMEOUT_SECONDS:-7200}
      XBOW_JOB_LEASE_SECONDS: ${XBOW_JOB_LEASE_SECONDS:-21600}
      XBOW_MAX_STRIX_JSON_BYTES: ${XBOW_MAX_STRIX_JSON_BYTES:-5242880}
      XBOW_MAX_AUTONOMOUS_RPS: ${XBOW_MAX_AUTONOMOUS_RPS:-2.0}
      XBOW_MAX_JOB_PAYLOAD_BYTES: ${XBOW_MAX_JOB_PAYLOAD_BYTES:-65536}
      XBOW_DB_PATH: /data/xbow.sqlite3
      XBOW_ARTIFACT_ROOT: /data/artifacts
      XBOW_STRIX_RUN_ROOT: /data/strix_runs
      XBOW_WORKER_POLL_SECONDS: ${XBOW_WORKER_POLL_SECONDS:-1}
      XBOW_WORKER_ROLE: general
      XBOW_SCAN_ENGINES: ${XBOW_SCAN_ENGINES:-nuclei}
      XBOW_PLANNER_MAX_OBSERVATIONS: ${XBOW_PLANNER_MAX_OBSERVATIONS:-5000}
      XBOW_PLANNER_MAX_ENDPOINTS: ${XBOW_PLANNER_MAX_ENDPOINTS:-1500}
      XBOW_PLANNER_MAX_FINDINGS: ${XBOW_PLANNER_MAX_FINDINGS:-250}
      XBOW_PLANNER_MAX_ACTIONS: ${XBOW_PLANNER_MAX_ACTIONS:-50}
      XBOW_PLANNER_MAX_SCANS: ${XBOW_PLANNER_MAX_SCANS:-3}
      XBOW_PLANNER_MAX_VALIDATIONS: ${XBOW_PLANNER_MAX_VALIDATIONS:-25}
      XBOW_PLANNER_MAX_VALIDATION_BATCH: ${XBOW_PLANNER_MAX_VALIDATION_BATCH:-10}
      XBOW_PLANNER_MAX_REPORTS: ${XBOW_PLANNER_MAX_REPORTS:-5}
      XBOW_PLANNER_MAX_INFLIGHT_JOBS: ${XBOW_PLANNER_MAX_INFLIGHT_JOBS:-12}
      XBOW_PLANNER_MAX_FAILED_JOBS: ${XBOW_PLANNER_MAX_FAILED_JOBS:-5}
      XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS: ${XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS:-21600}
      STRIX_LLM: ${STRIX_LLM:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      LLM_API_BASE: ${LLM_API_BASE:-}
    volumes:
      - xbow-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=128m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 256
    mem_limit: 2g
    cpus: 2.0
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
    healthcheck:
      test: ["CMD", "python", "-m", "app.readiness"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks: [control]


  scanner-worker:
    profiles: ["scanner"]
    build: ./backend
    command: ["python", "-m", "app.worker_service"]
    restart: unless-stopped
    init: true
    stop_grace_period: 30s
    depends_on:
      backend:
        condition: service_healthy
    environment:
      XBOW_WORKER_ROLE: scanner
      XBOW_SCAN_ENGINES: ${XBOW_SCAN_ENGINES:-nuclei}
      XBOW_ENABLE_SCANNER_WORKER: "true"
      DRY_RUN: ${DRY_RUN:-true}
      XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}
      XBOW_ENABLE_NUCLEI: ${XBOW_ENABLE_NUCLEI:-false}
      XBOW_SCANNER_SANDBOX_PROFILE: restricted-v1
      XBOW_SANDBOX_READ_ONLY_ROOTFS: "true"
      XBOW_SANDBOX_NO_NEW_PRIVILEGES: "true"
      XBOW_SANDBOX_CAP_DROP_ALL: "true"
      XBOW_SCANNER_ALLOWED_ENGINES: ${XBOW_SCANNER_ALLOWED_ENGINES:-nuclei}
      XBOW_NUCLEI_ALLOWED_VERSION: ${XBOW_NUCLEI_ALLOWED_VERSION:-}
      XBOW_MAX_AUTONOMOUS_RPS: ${XBOW_MAX_AUTONOMOUS_RPS:-2.0}
      WORKER_TIMEOUT_SECONDS: ${WORKER_TIMEOUT_SECONDS:-7200}
      XBOW_JOB_LEASE_SECONDS: ${XBOW_JOB_LEASE_SECONDS:-21600}
      XBOW_DB_PATH: /data/xbow.sqlite3
      XBOW_ARTIFACT_ROOT: /data/artifacts
      XBOW_STRIX_RUN_ROOT: /data/strix_runs
      XBOW_NUCLEI_RUN_ROOT: /data/nuclei_runs
      STRIX_LLM: ${STRIX_LLM:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      LLM_API_BASE: ${LLM_API_BASE:-}
    volumes:
      - xbow-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=128m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 2g
    cpus: 2.0
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
    networks: [control]



  pentagi-worker:
    profiles: ["pentagi"]
    build: ./backend
    command: ["python", "-m", "app.pentagi_worker_service"]
    restart: unless-stopped
    init: true
    stop_grace_period: 30s
    depends_on:
      backend:
        condition: service_healthy
    environment:
      DRY_RUN: ${DRY_RUN:-true}
      XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}
      XBOW_ENABLE_PENTAGI: ${XBOW_ENABLE_PENTAGI:-false}
      XBOW_ENABLE_PENTAGI_WORKER: ${XBOW_ENABLE_PENTAGI_WORKER:-false}
      XBOW_ENABLE_PENTAGI_TRANSPORT: ${XBOW_ENABLE_PENTAGI_TRANSPORT:-false}
      XBOW_PENTAGI_API_TOKEN: ${XBOW_PENTAGI_API_TOKEN:-}
      XBOW_PENTAGI_TIMEOUT_SECONDS: ${XBOW_PENTAGI_TIMEOUT_SECONDS:-10}
      XBOW_PENTAGI_MAX_RESPONSE_BYTES: ${XBOW_PENTAGI_MAX_RESPONSE_BYTES:-1048576}
      XBOW_PENTAGI_MAX_ADMISSION_RPS: ${XBOW_PENTAGI_MAX_ADMISSION_RPS:-2.0}
      XBOW_JOB_LEASE_SECONDS: ${XBOW_JOB_LEASE_SECONDS:-21600}
      XBOW_DB_PATH: /data/xbow.sqlite3
      XBOW_ARTIFACT_ROOT: /data/artifacts
      XBOW_VAULT_ENABLED: ${XBOW_VAULT_ENABLED:-false}
      XBOW_VAULT_PATH: /data/secrets.vault.json
      XBOW_VAULT_MASTER_KEY: ${XBOW_VAULT_MASTER_KEY:-}
      XBOW_VAULT_MASTER_KEY_FILE: ${XBOW_VAULT_MASTER_KEY_FILE:-}
    volumes:
      - xbow-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=32m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 512m
    cpus: 0.5
    networks: [control]

  pentagi-status-worker:
    profiles: ["pentagi-status"]
    build: ./backend
    command: ["python", "-m", "app.pentagi_status_worker_service"]
    restart: unless-stopped
    init: true
    stop_grace_period: 30s
    depends_on:
      backend:
        condition: service_healthy
    environment:
      XBOW_ENABLE_PENTAGI: ${XBOW_ENABLE_PENTAGI:-false}
      XBOW_ENABLE_PENTAGI_STATUS_WORKER: ${XBOW_ENABLE_PENTAGI_STATUS_WORKER:-false}
      XBOW_PENTAGI_API_TOKEN: ${XBOW_PENTAGI_API_TOKEN:-}
      XBOW_PENTAGI_TIMEOUT_SECONDS: ${XBOW_PENTAGI_TIMEOUT_SECONDS:-10}
      XBOW_PENTAGI_MAX_RESPONSE_BYTES: ${XBOW_PENTAGI_MAX_RESPONSE_BYTES:-1048576}
      XBOW_PENTAGI_STATUS_POLL_SECONDS: ${XBOW_PENTAGI_STATUS_POLL_SECONDS:-10}
      XBOW_PENTAGI_STATUS_MAX_SECONDS: ${XBOW_PENTAGI_STATUS_MAX_SECONDS:-3600}
      XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS: ${XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS:-1}
      XBOW_JOB_LEASE_SECONDS: ${XBOW_JOB_LEASE_SECONDS:-21600}
      XBOW_DB_PATH: /data/xbow.sqlite3
      XBOW_ARTIFACT_ROOT: /data/artifacts
      XBOW_VAULT_ENABLED: ${XBOW_VAULT_ENABLED:-false}
      XBOW_VAULT_PATH: /data/secrets.vault.json
      XBOW_VAULT_MASTER_KEY: ${XBOW_VAULT_MASTER_KEY:-}
      XBOW_VAULT_MASTER_KEY_FILE: ${XBOW_VAULT_MASTER_KEY_FILE:-}
    volumes:
      - xbow-data:/data
    read_only: true
    tmpfs:
      - /tmp:size=32m,noexec,nosuid,nodev
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 384m
    cpus: 0.5
    networks: [control]

  frontend:
    build: ./frontend
    restart: unless-stopped
    init: true
    stop_grace_period: 15s
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "${XBOW_PORT:-8080}:80"
    read_only: true
    tmpfs:
      - /var/cache/nginx:size=32m
      - /var/run:size=8m
      - /tmp:size=16m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 128
    mem_limit: 256m
    cpus: 0.5
    networks: [control]

volumes:
  xbow-data:

networks:
  control:
    driver: bridge
````

## File: pyproject.toml
````toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"backend/app/main.py" = ["F401"]
````

## File: README.md
````markdown
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
````
