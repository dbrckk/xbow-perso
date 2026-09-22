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


def test_mobile_status_prints_explicit_launch_verdict_and_blockers():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "=== BUG BOUNTY LAUNCH VERDICT ===" in script
    assert "BUG_BOUNTY_LAUNCH_READY=true" in script
    assert "BUG_BOUNTY_LAUNCH_READY=false" in script
    assert "VERDICT=READY" in script
    assert "VERDICT=BLOCKED" in script
    assert "BLOCKER=" in script
    assert "=== DASHBOARD ASSET VERSION ===" in script
    assert "PUBLIC_HTTPS_OK=false" in script
    assert "BLOCKER=public_https" in script


def test_enable_script_requires_final_live_launch_verdict():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    assert "=== FINAL BUG BOUNTY LAUNCH VERDICT ===" in script
    assert "BUG_BOUNTY_LAUNCH_READY=false" in script
    assert "BUG_BOUNTY_LAUNCH_READY=true" in script
    assert "raise SystemExit(1)" in script
    assert "NEXT_STEP=Open the dashboard" in script
    assert "DASHBOARD_URL=https://$PUBLIC_HOST/" in script


def test_mobile_status_requires_live_hackerone_api_probe_for_ready_verdict():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "=== HACKERONE API PROBE ===" in script
    assert "HACKERONE_API_READY=false" in script
    assert "HACKERONE_API_READY=true" in script
    assert 'HackerOneClient(credentials).get_json(' in script
    assert 'page[size]' in script
    assert '[ "$HACKERONE_API_READY" = "true" ]' in script
    assert "BLOCKER=hackerone_api" in script


def test_enable_script_probes_hackerone_before_declaring_profile_armed():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    probe = script.index("=== HACKERONE API PROBE ===")
    armed = script.index("PERSISTENT HACKERONE NUCLEI PROFILE ARMED")
    assert probe < armed
    assert "HACKERONE_API_READY=true" in script
    assert "HACKERONE_API_READY=false" in script
    assert 'HackerOneClient(credentials).get_json(' in script


def test_enable_script_reports_actionable_non_idle_queue_blocker():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    assert "QUEUE_IDLE=" in script
    assert "QUEUE_QUEUED=" in script
    assert "QUEUE_RUNNING=" in script
    assert "ACTIVE_BATCH_ID=" in script
    assert "ACTIVE_BATCH_STATE=" in script
    assert "queue_idle = active_jobs == 0 and not active_batches" in script
    assert "if not queue_idle:" in script
    assert "Let the active batch finish or cancel it from the dashboard before arming the scanner." in script
    assert "assert active==0" not in script
