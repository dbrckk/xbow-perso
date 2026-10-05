import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _compose() -> str:
    return (ROOT / "docker-compose.yml").read_text()


def _service_block(name: str, next_name: str) -> str:
    compose = _compose()
    marker = f"\n  {name}:\n"
    next_marker = f"\n  {next_name}:\n"
    return compose.split(marker, 1)[1].split(next_marker, 1)[0]


def test_strix_broker_is_internal_and_unpublished():
    compose = _compose()
    broker = _service_block("strix-broker", "strix-egress")
    networks = compose.split("\nnetworks:", 1)[1]

    assert 'profiles: ["strix-broker"]' in broker
    assert "networks: [strix-broker, strix-egress-control]" in broker
    assert "strix-external" not in broker
    assert "\n    ports:" not in broker
    assert "\n    volumes:" not in broker
    assert "read_only: true" in broker
    assert "no-new-privileges:true" in broker
    assert "cap_drop:" in broker
    assert "- ALL" in broker
    assert "XBOW_STRIX_BROKER_HMAC_KEY:" in broker
    assert "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY:" in broker
    assert "XBOW_STRIX_EGRESS_URL: http://strix-egress:8091/v1/fetch" in broker
    assert "strix-broker:" in networks
    assert "strix-egress-control:" in networks
    assert networks.count("internal: true") >= 2


def test_strix_egress_is_only_dual_homed_external_boundary():
    egress = _service_block("strix-egress", "pentagi-worker")

    assert 'profiles: ["strix-broker"]' in egress
    assert "networks: [strix-egress-control, strix-external]" in egress
    assert "networks: [strix-broker" not in egress
    assert "networks: [control" not in egress
    assert "\n    ports:" not in egress
    assert "\n    volumes:" not in egress
    assert "read_only: true" in egress
    assert "no-new-privileges:true" in egress
    assert "cap_drop:" in egress
    assert "- ALL" in egress
    assert "XBOW_STRIX_EGRESS_HMAC_KEY:" in egress
    assert "XBOW_STRIX_EGRESS_ENABLED:" in egress
    assert "/var/run/docker.sock" not in egress
    assert "docker.sock" not in egress


def test_scanner_worker_cannot_reach_egress_network_directly():
    scanner = _service_block("scanner-worker", "strix-broker")

    assert "networks: [control, strix-broker]" in scanner
    assert "strix-egress-control" not in scanner
    assert "strix-external" not in scanner
    assert "/var/run/docker.sock" not in scanner
    assert "docker.sock" not in scanner


def test_network_zones_keep_scanner_to_egress_separated():
    networks = _compose().split("\nnetworks:", 1)[1]

    assert (
        "strix-broker:\n"
        "    driver: bridge\n"
        "    internal: true"
    ) in networks
    assert (
        "strix-egress-control:\n"
        "    driver: bridge\n"
        "    internal: true"
    ) in networks
    assert "strix-external:\n    driver: bridge" in networks


def test_ci_builds_strix_broker_and_egress_profile():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert (
        "docker compose --profile strix-broker build --pull "
        "strix-broker strix-egress"
        in workflow
    )



def test_strix_broker_imports_in_fresh_interpreter():
    backend = ROOT / "backend"
    env = {
        **os.environ,
        "PYTHONPATH": str(backend),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app.strix_broker; "
                "print(app.strix_broker.app.title)"
            ),
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "xbow Strix admission broker" in result.stdout
