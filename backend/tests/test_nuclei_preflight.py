from app.deployment_preflight import build_deployment_preflight
from app.runtime_capabilities import scanner_runtime_capability


_SCANNER_ENV = (
    "XBOW_ENABLE_ACTIVE_SCANS",
    "XBOW_ENABLE_SCANNER_WORKER",
    "XBOW_ENABLE_NUCLEI",
    "DRY_RUN",
    "XBOW_SCANNER_SANDBOX_PROFILE",
    "XBOW_SCANNER_ALLOWED_ENGINES",
    "XBOW_NUCLEI_ALLOWED_VERSION",
)


def _clear(monkeypatch):
    for name in _SCANNER_ENV:
        monkeypatch.delenv(name, raising=False)


def _active_nuclei(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("DRY_RUN", "false")


def test_scanner_capability_blocks_active_nuclei_without_pinned_version(monkeypatch):
    _active_nuclei(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")

    result = scanner_runtime_capability()

    assert result.get("nuclei_enabled") is True
    assert result.get("nuclei_version_configured") is False
    assert result["dispatch_ready"] is False
    assert "nuclei_version_allowlist_missing" in result["dispatch_block_reasons"]


def test_preflight_rejects_incomplete_active_nuclei_configuration(monkeypatch):
    _active_nuclei(monkeypatch)
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "strix")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert {item["code"] for item in result["issues"]} == {
        "scanner_worker_disabled",
        "scanner_sandbox_profile_required",
        "nuclei_not_allowlisted",
        "nuclei_version_allowlist_missing",
    }
    assert result.get("scanner") == {
        "execution_intent": True,
        "nuclei_enabled": True,
        "worker_enabled": False,
        "sandbox_profile": "unconfigured",
        "nuclei_allowlisted": False,
        "nuclei_version_configured": False,
        "dispatch_ready": False,
    }


def test_preflight_accepts_complete_active_nuclei_configuration_without_leaking_version(monkeypatch):
    _active_nuclei(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_SCANNER_WORKER", "true")
    monkeypatch.setenv("XBOW_SCANNER_SANDBOX_PROFILE", "restricted-v1")
    monkeypatch.setenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_NUCLEI_ALLOWED_VERSION", "v3.4.10-private-marker")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "ok"
    assert result["issues"] == []
    assert result.get("scanner") == {
        "execution_intent": True,
        "nuclei_enabled": True,
        "worker_enabled": True,
        "sandbox_profile": "restricted-v1",
        "nuclei_allowlisted": True,
        "nuclei_version_configured": True,
        "dispatch_ready": True,
    }
    assert "v3.4.10-private-marker" not in str(result)


def test_preflight_rejects_invalid_nuclei_boolean_fail_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "maybe")

    result = build_deployment_preflight({"ok": True})

    assert result["status"] == "error"
    assert {item["code"] for item in result["issues"]} == {
        "scanner_invalid_boolean_configuration"
    }
    assert result.get("scanner", {}).get("dispatch_ready") is False
