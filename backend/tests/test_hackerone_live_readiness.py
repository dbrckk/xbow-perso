from app import hackerone_live_readiness as readiness


_ENV_NAMES = (
    "XBOW_API_TOKEN",
    "XBOW_ENABLE_ACTIVE_SCANS",
    "XBOW_ENABLE_RECON",
    "XBOW_ENABLE_EXTERNAL_RECON",
    "XBOW_ENABLE_BROWSER_AUTOMATION",
    "XBOW_ENABLE_SCANNER_WORKER",
    "XBOW_ENABLE_NUCLEI",
    "XBOW_SCANNER_SANDBOX_PROFILE",
    "XBOW_SCANNER_ALLOWED_ENGINES",
    "XBOW_NUCLEI_ALLOWED_VERSION",
    "DRY_RUN",
    "XBOW_ENABLE_HACKERONE_SUBMISSION",
    "XBOW_ENABLE_HACKERONE_REPORT_SYNC",
)


def _clear(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _credentials_ok(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_hackerone_credentials",
        lambda: object(),
    )
    monkeypatch.setattr(
        readiness,
        "worker_liveness_snapshot",
        lambda: {
            "general": {"role": "general", "live": True, "contains_secrets": False},
            "scanner": {"role": "scanner", "live": True, "contains_secrets": False},
            "contains_secrets": False,
        },
    )


def test_live_readiness_is_blocked_by_safe_defaults(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)

    result = readiness.build_hackerone_live_readiness({"ok": True})

    assert result["status"] == "blocked"
    assert result["program_review_ready"] is True
    assert result["live_scan_ready"] is False
    failed = {
        item["id"]
        for item in result["checks"]
        if item["required"] and not item["ok"]
    }
    assert {
        "recon_dispatch",
        "active_scans",
        "dry_run_disabled",
        "scanner_worker",
        "nuclei_enabled",
        "nuclei_version",
        "scanner_dispatch",
        "api_token",
    }.issubset(failed)
    assert result["read_only"] is True
    assert result["contains_secrets"] is False


def test_live_readiness_requires_hackerone_credentials(monkeypatch):
    _clear(monkeypatch)

    def unavailable():
        raise readiness.HackerOneClientError("hidden")

    monkeypatch.setattr(readiness, "load_hackerone_credentials", unavailable)

    result = readiness.build_hackerone_live_readiness({"ok": True})

    by_id = {item["id"]: item for item in result["checks"]}
    assert by_id["hackerone_credentials"]["ok"] is False
    assert result["program_review_ready"] is False
    assert "hidden" not in str(result)


def test_live_readiness_passes_only_with_explicit_scanner_gates(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "x" * 64)
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_RECON", "true")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "3.11.1")
    monkeypatch.setenv("DRY_RUN", "false")

    result = readiness.build_hackerone_live_readiness({"ok": True})

    assert result["status"] == "ready"
    assert result["program_review_ready"] is True
    assert result["live_scan_ready"] is True
    assert all(
        item["ok"]
        for item in result["checks"]
        if item["required"]
    )
    assert result["submission_enabled"] is False
    assert result["report_sync_enabled"] is False


def test_submission_and_sync_are_optional(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)

    result = readiness.build_hackerone_live_readiness({"ok": True})
    by_id = {item["id"]: item for item in result["checks"]}

    assert by_id["direct_submission"]["required"] is False
    assert by_id["report_sync"]["required"] is False


def test_invalid_optional_boolean_fails_closed(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_SUBMISSION", "maybe")

    result = readiness.build_hackerone_live_readiness({"ok": True})

    assert result["status"] == "blocked"
    assert any(
        item["id"] == "boolean_configuration"
        and item["required"]
        and not item["ok"]
        for item in result["checks"]
    )


def test_live_readiness_exposes_redacted_first_run_operator_guide(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "x" * 64)

    result = readiness.build_hackerone_live_readiness({"ok": True})

    assert result["contains_secrets"] is False
    assert result["read_only"] is True
    assert [step["id"] for step in result["operator_steps"]] == [
        "configure_access",
        "configure_hackerone",
        "select_program",
        "review_program",
        "activate_scanner",
        "launch_confirmed_preview",
    ]
    assert result["operator_steps"][0]["done"] is True
    assert result["operator_steps"][1]["done"] is True
    assert result["activation_template"] == [
        "sudo bash /opt/xbow-perso/scripts/mobile-enable-hackerone-nuclei.sh",
    ]
    assert result["scanner_start_command"] == (
        "sudo bash /opt/xbow-perso/scripts/mobile-enable-hackerone-nuclei.sh"
    )
    assert result["scanner_disable_command"] == (
        "sudo bash /opt/xbow-perso/scripts/mobile-disable-hackerone-nuclei.sh"
    )
    assert result["persistent_scanner_profile_supported"] is True
    assert "token" not in "\n".join(result["activation_template"]).lower()



def test_browser_automation_is_optional_but_reported(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "false")

    result = readiness.build_hackerone_live_readiness({"ok": True})
    by_id = {item["id"]: item for item in result["checks"]}

    assert by_id["browser_automation"]["required"] is False
    assert by_id["browser_automation"]["ok"] is False
    assert "browser_automation_disabled" in result["browser_block_reasons"]


def test_live_readiness_blocks_when_recon_is_disabled(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "x" * 64)
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "3.11.1")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_RECON", "false")

    result = readiness.build_hackerone_live_readiness({"ok": True})

    assert result["live_scan_ready"] is False
    assert "recon_disabled" in result["recon_block_reasons"]

def test_live_readiness_blocks_when_scanner_heartbeat_is_stale(monkeypatch):
    _clear(monkeypatch)
    _credentials_ok(monkeypatch)
    monkeypatch.setattr(
        readiness,
        "worker_liveness_snapshot",
        lambda: {
            "general": {"role": "general", "live": True, "contains_secrets": False},
            "scanner": {
                "role": "scanner",
                "live": False,
                "reason": "heartbeat_stale",
                "age_seconds": 45,
                "max_age_seconds": 30,
                "contains_secrets": False,
            },
            "contains_secrets": False,
        },
    )
    monkeypatch.setenv("XBOW_API_TOKEN", "x" * 64)
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_RECON", "true")
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "3.11.1")
    monkeypatch.setenv("DRY_RUN", "false")

    result = readiness.build_hackerone_live_readiness({"ok": True})
    by_id = {item["id"]: item for item in result["checks"]}

    assert result["live_scan_ready"] is False
    assert by_id["scanner_worker_live"]["ok"] is False
    assert result["worker_liveness"]["scanner"]["reason"] == "heartbeat_stale"
    assert result["contains_secrets"] is False
