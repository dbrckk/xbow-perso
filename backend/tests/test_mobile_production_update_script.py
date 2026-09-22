from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_live_production_update_waits_for_worker_heartbeats():
    script = (ROOT / "scripts/mobile-production-update.sh").read_text(encoding="utf-8")

    assert "=== WAIT FOR WORKER HEARTBEATS ===" in script
    assert 's["general"]["live"] and s["scanner"]["live"]' in script
    assert "for _ in $(seq 1 30)" in script
    assert "Worker heartbeat validation failed." in script
    assert "=== HACKERONE LIVE GO/NO-GO ===" in script


def test_mobile_status_reports_hackerone_launch_readiness():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "=== WORKER LIVENESS ===" in script
    assert "=== HACKERONE LIVE READINESS ===" in script
    assert '"live_scan_ready": r["live_scan_ready"]' in script
    assert '"failed": [x["id"] for x in r["checks"] if x["required"] and not x["ok"]]' in script
    assert "=== PUBLIC HTTPS ===" in script
