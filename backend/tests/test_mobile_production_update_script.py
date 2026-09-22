from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_live_production_update_waits_for_worker_heartbeats():
    script = (ROOT / "scripts/mobile-production-update.sh").read_text(encoding="utf-8")

    assert "=== WAIT FOR WORKER HEARTBEATS ===" in script
    assert 's["general"]["live"] and s["scanner"]["live"]' in script
    assert "for _ in $(seq 1 30)" in script
    assert "Worker heartbeat validation failed." in script
    assert "=== HACKERONE LIVE GO/NO-GO ===" in script
