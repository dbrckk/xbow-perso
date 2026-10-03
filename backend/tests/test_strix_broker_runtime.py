from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _broker_compose_block() -> str:
    compose = (ROOT / "docker-compose.yml").read_text()
    return compose.split("  strix-broker:", 1)[1].split("\n  pentagi-worker:", 1)[0]


def test_strix_broker_is_internal_and_unpublished():
    compose = (ROOT / "docker-compose.yml").read_text()
    broker = _broker_compose_block()
    networks = compose.split("\nnetworks:", 1)[1]

    assert 'profiles: ["strix-broker"]' in broker
    assert 'networks: [strix-broker]' in broker
    assert "\n    ports:" not in broker
    assert "\n    volumes:" not in broker
    assert "read_only: true" in broker
    assert "no-new-privileges:true" in broker
    assert "cap_drop:" in broker
    assert "- ALL" in broker
    assert "XBOW_STRIX_BROKER_HMAC_KEY:" in broker
    assert "internal: true" in networks


def test_scanner_worker_can_reach_only_broker_internal_boundary_additionally():
    compose = (ROOT / "docker-compose.yml").read_text()
    scanner = compose.split("  scanner-worker:", 1)[1].split(
        "\n  strix-broker:",
        1,
    )[0]

    assert "networks: [control, strix-broker]" in scanner
    assert "/var/run/docker.sock" not in scanner
    assert "docker.sock" not in scanner


def test_ci_builds_strix_broker_profile():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert (
        "docker compose --profile strix-broker build --pull strix-broker"
        in workflow
    )
