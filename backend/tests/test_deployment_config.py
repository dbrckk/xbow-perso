from pathlib import Path


def _compose() -> str:
    return (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")


def test_compose_declares_backend_and_worker_healthchecks():
    compose = _compose()
    assert compose.count("healthcheck:") >= 2
    assert compose.count('["CMD", "python", "-m", "app.readiness"]') >= 2
    assert compose.count("condition: service_healthy") >= 2


def test_compose_keeps_services_hardened():
    compose = _compose()
    assert compose.count("read_only: true") >= 3
    assert compose.count("no-new-privileges:true") >= 3
    assert compose.count("cap_drop:") >= 3
    assert compose.count("- ALL") >= 3
    assert compose.count("init: true") >= 3
    assert compose.count("restart: unless-stopped") >= 3
    assert "XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}" in compose
    assert "XBOW_ENABLE_HTTP_VALIDATION: ${XBOW_ENABLE_HTTP_VALIDATION:-false}" in compose
    assert "XBOW_ENABLE_BROWSER_AUTOMATION: ${XBOW_ENABLE_BROWSER_AUTOMATION:-false}" in compose
    assert compose.count("XBOW_MAX_JOB_PAYLOAD_BYTES: ${XBOW_MAX_JOB_PAYLOAD_BYTES:-65536}") == 2
    assert "XBOW_MAX_AUTONOMOUS_RPS: ${XBOW_MAX_AUTONOMOUS_RPS:-2.0}" in compose


def test_compose_keeps_state_private_and_shared_only_where_needed():
    compose = _compose()
    assert "XBOW_DB_PATH: /data/xbow.sqlite3" in compose
    assert "XBOW_ARTIFACT_ROOT: /data/artifacts" in compose
    assert compose.count("- xbow-data:/data") == 2
    assert '"${XBOW_PORT:-8080}:80"' in compose


def test_compose_enforces_resource_and_shutdown_bounds():
    compose = _compose()
    assert "stop_grace_period: 20s" in compose
    assert "stop_grace_period: 30s" in compose
    assert "stop_grace_period: 15s" in compose
    assert "pids_limit: 256" in compose
    assert "pids_limit: 128" in compose
    assert "mem_limit: 512m" in compose
    assert "mem_limit: 2g" in compose
    assert "mem_limit: 256m" in compose
    assert "cpus: 1.0" in compose
    assert "cpus: 2.0" in compose
    assert "cpus: 0.5" in compose
