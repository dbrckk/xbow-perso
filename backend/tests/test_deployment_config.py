from pathlib import Path


def test_compose_declares_backend_and_worker_healthchecks():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("healthcheck:") >= 2
    assert "http://127.0.0.1:8000/health" in compose
    assert "JobQueue().stats()" in compose


def test_compose_keeps_services_hardened():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("read_only: true") >= 3
    assert compose.count("no-new-privileges:true") >= 3
    assert compose.count("cap_drop:") >= 3
    assert "XBOW_ENABLE_ACTIVE_SCANS: ${XBOW_ENABLE_ACTIVE_SCANS:-false}" in compose
    assert "XBOW_ENABLE_HTTP_VALIDATION: ${XBOW_ENABLE_HTTP_VALIDATION:-false}" in compose
    assert "XBOW_ENABLE_BROWSER_AUTOMATION: ${XBOW_ENABLE_BROWSER_AUTOMATION:-false}" in compose
