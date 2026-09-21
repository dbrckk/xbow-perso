from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_live_hackerone_profile_enables_bounded_recon_only():
    script = _text("mobile-enable-hackerone-nuclei.sh")

    assert "XBOW_ENABLE_RECON=true" in script
    assert "XBOW_ENABLE_EXTERNAL_RECON=false" in script
    assert "XBOW_ENABLE_BROWSER_AUTOMATION=false" in script
    assert 'require_baseline_gate "XBOW_ENABLE_RECON" "false"' in script
    assert 'require_baseline_gate "XBOW_ENABLE_EXTERNAL_RECON" "false"' in script
    assert 'require_baseline_gate "XBOW_ENABLE_BROWSER_AUTOMATION" "false"' in script


def test_production_update_propagates_and_attests_bounded_recon():
    script = _text("mobile-production-update.sh")

    assert 'require_live_value "XBOW_ENABLE_RECON" "true"' in script
    assert 'require_live_value "XBOW_ENABLE_EXTERNAL_RECON" "false"' in script
    assert 'require_live_value "XBOW_ENABLE_BROWSER_AUTOMATION" "false"' in script
    assert "export XBOW_ENABLE_NUCLEI XBOW_ENABLE_RECON XBOW_ENABLE_EXTERNAL_RECON" in script
    assert "recon_runtime_capability" in script
    assert 'assert c["dispatch_ready"] and c["recon_enabled"] and not c["external_recon_enabled"]' in script


def test_safe_production_update_keeps_recon_and_browser_disabled():
    script = _text("mobile-production-update.sh")

    assert "export XBOW_ENABLE_RECON=false" in script
    assert "export XBOW_ENABLE_EXTERNAL_RECON=false" in script
    assert "export XBOW_ENABLE_BROWSER_AUTOMATION=false" in script



def test_all_safe_production_scripts_require_recon_browser_baseline_off():
    for name in (
        "mobile-production-preflight.sh",
        "mobile-production-cutover.sh",
        "mobile-production-rollback.sh",
    ):
        script = _text(name)
        assert 'require_gate "XBOW_ENABLE_RECON" "false"' in script
        assert 'require_gate "XBOW_ENABLE_EXTERNAL_RECON" "false"' in script
        assert 'require_gate "XBOW_ENABLE_BROWSER_AUTOMATION" "false"' in script



def test_live_production_update_requires_backend_go_no_go_readiness():
    script = _text("mobile-production-update.sh")

    assert "=== HACKERONE LIVE GO/NO-GO ===" in script
    assert "build_hackerone_live_readiness" in script
    assert 'assert r["live_scan_ready"]' in script



def test_production_update_normalizes_api_token_source():
    script = _text("mobile-production-update.sh")

    assert "auth-source normalization" in script
    assert "unset XBOW_API_TOKEN XBOW_API_TOKEN_FILE" in script
    assert "export XBOW_API_TOKEN" in script
    assert "XBOW_VAULT_ENABLED" in script



def test_production_update_attests_frontend_diagnostic_proxy():
    script = _text("mobile-production-update.sh")

    assert "=== FRONTEND DIAGNOSTIC PROXY ===" in script
    assert "http://127.0.0.1:8080/live" in script
    assert "http://127.0.0.1:8080/auth-status" in script
    assert "0.6.2" in script
    assert "contains_secrets" in script



def test_production_update_self_heals_stale_baseline_flags():
    script = _text("mobile-production-update.sh")

    assert "normalize_baseline_gate()" in script
    assert 'normalize_baseline_gate "DRY_RUN" "true"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_ACTIVE_SCANS" "false"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_NUCLEI" "false"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_RECON" "false"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_EXTERNAL_RECON" "false"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_BROWSER_AUTOMATION" "false"' in script
    assert 'normalize_baseline_gate "XBOW_ENABLE_HACKERONE_SUBMISSION" "false"' in script
