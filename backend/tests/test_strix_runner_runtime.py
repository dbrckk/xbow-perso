from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _compose() -> str:
    return (ROOT / "docker-compose.yml").read_text()


def _service_block(name: str, next_name: str) -> str:
    compose = _compose()
    marker = f"\n  {name}:\n"
    next_marker = f"\n  {next_name}:\n"
    return compose.split(marker, 1)[1].split(next_marker, 1)[0]


def test_strix_runner_dockerfile_pins_release_and_digests():
    dockerfile = (ROOT / "backend" / "Dockerfile.strix-runner").read_text()

    assert "ARG STRIX_VERSION=1.6.2" in dockerfile
    assert (
        "ARG STRIX_UPSTREAM_COMMIT="
        "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
        in dockerfile
    )
    assert (
        "f3f29fa64bee420bf64f8911fb9f38e20270d406f6df44cc2436252c2af0bc81"
        in dockerfile
    )
    assert (
        "4a4cba115bda8b89d7bbfabe960246a480ff43563144959b2e33477955aa6df2"
        in dockerfile
    )
    assert "sha256sum -c -" in dockerfile
    assert 'test "$(/opt/strix/strix --version)" = "strix ${STRIX_VERSION}"' in dockerfile
    assert "docker.sock" not in dockerfile
    assert "apt-get install" not in dockerfile.split("FROM python:3.12-slim", 1)[1]


def test_strix_runner_is_internal_unpublished_and_secret_free():
    runner = _service_block("strix-runner", "pentagi-worker")

    assert 'profiles: ["strix-runner"]' in runner
    assert "dockerfile: Dockerfile.strix-runner" in runner
    assert "networks: [strix-runner-control]" in runner
    assert "networks: [control" not in runner
    assert "strix-external" not in runner
    assert "strix-egress-control" not in runner
    assert "\n    ports:" not in runner
    assert "\n    volumes:" not in runner
    assert "read_only: true" in runner
    assert "no-new-privileges:true" in runner
    assert "cap_drop:" in runner
    assert "- ALL" in runner
    assert "docker.sock" not in runner
    assert "LLM_API_KEY" not in runner
    assert "XBOW_STRIX_BROKER_HMAC_KEY" not in runner
    assert "XBOW_STRIX_EGRESS_HMAC_KEY" not in runner


def test_broker_and_runner_share_only_dedicated_internal_network():
    compose = _compose()
    broker = _service_block("strix-broker", "strix-egress")
    runner = _service_block("strix-runner", "pentagi-worker")
    networks = compose.split("\nnetworks:", 1)[1]

    assert "strix-runner-control" in broker
    assert "networks: [strix-runner-control]" in runner
    assert (
        "strix-runner-control:\n"
        "    driver: bridge\n"
        "    internal: true"
    ) in networks


def test_scanner_worker_cannot_reach_strix_runner_network():
    scanner = _service_block("scanner-worker", "strix-broker")

    assert "strix-runner-control" not in scanner


def test_ci_builds_attestation_runner_profile():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert (
        "docker compose --profile strix-runner build --pull strix-runner"
        in workflow
    )


def test_supply_chain_builds_runner_with_provenance_and_sbom():
    workflow = (
        ROOT / ".github" / "workflows" / "supply-chain.yml"
    ).read_text()

    assert "Build Strix runner without publishing" in workflow
    assert "file: ./backend/Dockerfile.strix-runner" in workflow
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow


def test_ci_smoke_tests_runner_attestation_without_scan_execution():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "Smoke-test pinned Strix runner attestation" in workflow
    assert "docker compose --profile strix-runner up -d strix-runner" in workflow
    assert "docker inspect --format" in workflow
    assert ".State.Health.Status" in workflow
    assert '"healthy"' in workflow
    assert "strix scan" not in workflow


def test_supply_chain_cancels_superseded_branch_runs():
    workflow = (
        ROOT / ".github" / "workflows" / "supply-chain.yml"
    ).read_text()

    assert "concurrency:" in workflow
    assert "supply-chain-${{ github.workflow }}-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
