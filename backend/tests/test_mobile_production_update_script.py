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


def test_enable_script_keeps_rollback_active_through_final_launch_verification():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    arm = script.index("=== ARM PERSISTENT HACKERONE NUCLEI PROFILE ===")
    probe = script.index("=== HACKERONE API PROBE ===")
    verdict = script.index("=== FINAL BUG BOUNTY LAUNCH VERDICT ===")
    clear_trap = script.index("trap - ERR", arm)
    assert arm < probe < verdict < clear_trap


def test_enable_script_refreshes_safe_production_before_readiness_and_queue_checks():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    refresh = script.index("=== SAFE PRODUCTION REFRESH ===")
    readiness = script.index("=== BACKEND READINESS ===")
    queue_check = script.index("=== QUEUE MUST BE IDLE BEFORE ARMING ===")
    arm = script.index("=== ARM PERSISTENT HACKERONE NUCLEI PROFILE ===")
    assert refresh < readiness < queue_check < arm
    assert 'bash "$INSTALL_DIR/scripts/mobile-production-update.sh"' in script


def test_enable_script_documents_stale_checkout_and_stopped_stack_recovery():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    assert "containers are stopped" in script
    assert "checkout is stale" in script
    assert "repository .env remains fail-safe" in script


def test_enable_script_reexecs_from_refreshed_checkout_exactly_once():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    assert 'XBOW_ACTIVATION_REFRESHED:-0' in script
    assert "=== RESTART ACTIVATION FROM UPDATED CHECKOUT ===" in script
    assert 'exec env XBOW_ACTIVATION_REFRESHED=1 bash "$INSTALL_DIR/scripts/mobile-enable-hackerone-nuclei.sh"' in script


def test_enable_script_reconciles_hackerone_batches_before_queue_idle_gate():
    script = (ROOT / "scripts/mobile-enable-hackerone-nuclei.sh").read_text(encoding="utf-8")

    reconcile = script.index("=== RECONCILE HACKERONE BATCH STATE ===")
    queue_check = script.index("=== QUEUE MUST BE IDLE BEFORE ARMING ===")
    assert reconcile < queue_check
    assert "reconcile_hackerone_batches(queue(), storage(), limit=200)" in script
    assert "RECONCILED_BATCHES=" in script


def test_mobile_status_public_https_probe_uses_get_not_head():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert 'curl -fsS -D - -o /dev/null "https://$PUBLIC_HOST/health"' in script
    assert 'curl -fsSI "https://$PUBLIC_HOST/health"' not in script
    assert 'echo "PUBLIC_HTTPS_OK=true"' in script


def test_mobile_status_verifies_exact_deployed_v83_contract():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "=== DEPLOYED REVISION ===" in script
    assert 'LOCAL_SHA="$(git rev-parse HEAD)"' in script
    assert "git ls-remote origin refs/heads/main" in script
    assert "CHECKOUT_CURRENT=true" in script
    assert "EXPECTED_DASHBOARD_ASSET=" in script
    assert "grep -o 'simple.js?v=[0-9][0-9]*' frontend/index.html" in script
    assert "PUBLIC_DASHBOARD_ASSET=" in script
    assert '[ "$DASHBOARD_ASSET" = "$EXPECTED_DASHBOARD_ASSET" ]' in script
    assert "DASHBOARD_VERSION_OK=true" in script
    assert "=== V83 ROUTE CONTRACT ===" in script
    assert '"/api/hackerone/simple-review-package"' in script
    assert '"/api/imports/hackerone/rules-preview"' in script
    assert '"/api/imports/hackerone/batches/launch-reviewed"' in script
    assert '"/api/hackerone/journal"' in script
    assert '"/api/labs/htb/campaigns"' in script
    assert '"/api/labs/htb/campaigns/{campaign_id}/outcome"' in script
    assert '"/api/labs/htb/campaigns/{campaign_id}/learning"' in script
    assert '"/api/labs/htb/learning"' in script
    assert "V83_ROUTE_CONTRACT_OK=true" in script
    assert "=== PRODUCTION CONTRACT VERDICT ===" in script
    assert "PRODUCTION_CONTRACT_OK=true" in script
    assert "PRODUCTION_CONTRACT_OK=false" in script


def test_mobile_status_production_contract_requires_all_live_prerequisites():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    verdict = script.split("=== PRODUCTION CONTRACT VERDICT ===", 1)[1]
    assert '[ "$RUNTIME_READY" = "true" ]' in verdict
    assert '[ "$PUBLIC_HTTPS_OK" = "true" ]' in verdict
    assert '[ "$HACKERONE_API_READY" = "true" ]' in verdict
    assert '[ "$DASHBOARD_VERSION_OK" = "true" ]' in verdict
    assert '[ "$V83_ROUTE_CONTRACT_OK" = "true" ]' in verdict
    assert '[ "$CHECKOUT_CURRENT" = "true" ]' in verdict
    assert "BLOCKER=checkout_stale" in verdict
    assert "BLOCKER=dashboard_version" in verdict
    assert "BLOCKER=route_contract" in verdict


def test_mobile_status_route_contract_tolerates_non_route_entries():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert 'getattr(route, "path", None)' in script
    assert 'if (path := getattr(route, "path", None))' in script
    assert "paths = {" in script


def test_mobile_status_uses_live_origin_main_and_fails_closed():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "git ls-remote origin refs/heads/main" in script
    assert "REMOTE_MAIN_REACHABLE=true" in script
    assert "REMOTE_MAIN_REACHABLE=false" in script
    verdict = script.split("=== PRODUCTION CONTRACT VERDICT ===", 1)[1]
    assert '[ "$REMOTE_MAIN_REACHABLE" = "true" ]' in verdict
    assert "BLOCKER=origin_main_unreachable" in verdict
    assert "exit 1" in verdict


def test_mobile_status_live_verifies_one_or_two_accessible_bounties():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "=== ACCESSIBLE BOUNTY PRECHECK ===" in script
    assert "from app.hackerone_api import hackerone_simple_review_package" in script
    assert "result = hackerone_simple_review_package()" in script
    assert "1 <= len(handles) <= 2" in script
    assert 'result.get("live_verified") is True' in script
    assert "ACCESSIBLE_BOUNTY_PRECHECK_OK=true" in script
    assert "ACCESSIBLE_BOUNTY_COUNT=" in script
    assert "ACCESSIBLE_BOUNTY_HANDLES=" in script
    verdict = script.split("=== PRODUCTION CONTRACT VERDICT ===", 1)[1]
    assert '[ "$ACCESSIBLE_BOUNTY_PRECHECK_OK" = "true" ]' in verdict
    assert "BLOCKER=accessible_bounty_precheck" in verdict


def test_mobile_status_dashboard_version_check_cannot_drift_from_frontend_version():
    script = (ROOT / "scripts/mobile-production-status.sh").read_text(encoding="utf-8")

    assert "EXPECTED_DASHBOARD_ASSET=" in script
    assert "frontend/index.html" in script
    assert 'simple.js?v=82' not in script
