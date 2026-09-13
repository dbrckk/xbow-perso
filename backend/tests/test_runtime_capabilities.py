import pytest

from app import main
from app.runtime_capabilities import (
    CapabilityConfigError,
    pentagi_runtime_capability,
    safe_pentagi_runtime_capability,
)


_PENTAGI_FLAGS = (
    "XBOW_ENABLE_PENTAGI",
    "XBOW_ENABLE_ACTIVE_SCANS",
    "XBOW_ENABLE_PENTAGI_WORKER",
    "XBOW_ENABLE_PENTAGI_TRANSPORT",
    "XBOW_ENABLE_PENTAGI_STATUS_WORKER",
    "DRY_RUN",
)


def _clear(monkeypatch):
    for name in _PENTAGI_FLAGS:
        monkeypatch.delenv(name, raising=False)


def test_pentagi_capability_defaults_fail_closed(monkeypatch):
    _clear(monkeypatch)

    result = pentagi_runtime_capability()

    assert result["mode"] == "disabled"
    assert result["dispatch_ready"] is False
    assert result["execution_transport_enforceable"] is False
    assert "pentagi_disabled" in result["dispatch_block_reasons"]
    assert "active_scans_disabled" in result["dispatch_block_reasons"]
    assert "global_dry_run" in result["dispatch_block_reasons"]
    assert "execution_transport_not_enforceable" in result["dispatch_block_reasons"]
    assert result["status_tracking"]["available"] is False
    assert result["contains_secrets"] is False


def test_all_operator_gates_still_do_not_claim_pentagi_execution(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")
    monkeypatch.setenv("DRY_RUN", "false")

    result = pentagi_runtime_capability()

    assert result["mode"] == "preview_only"
    assert result["dispatch_ready"] is False
    assert result["dispatch_block_reasons"] == [
        "execution_transport_not_enforceable"
    ]
    assert result["execution_transport_enforceable"] is False
    assert result["status_tracking"] == {
        "worker_enabled": True,
        "available": True,
    }


def test_status_tracking_requires_integration_and_status_worker(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")

    disabled = pentagi_runtime_capability()
    assert disabled["status_tracking"]["worker_enabled"] is True
    assert disabled["status_tracking"]["available"] is False

    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    enabled = pentagi_runtime_capability()
    assert enabled["status_tracking"]["available"] is True


def test_invalid_boolean_configuration_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "maybe")

    with pytest.raises(CapabilityConfigError, match="XBOW_ENABLE_PENTAGI"):
        pentagi_runtime_capability()

    safe = safe_pentagi_runtime_capability()
    assert safe["mode"] == "configuration_error"
    assert safe["configuration_error"] is True
    assert safe["dispatch_ready"] is False
    assert safe["dispatch_block_reasons"] == ["invalid_boolean_configuration"]
    assert safe["contains_secrets"] is False


def test_capabilities_api_exposes_runtime_pentagi_state_without_secrets(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_API_TOKEN", "must-not-leak")

    result = main.system_capabilities()

    execution = result["execution"]
    assert execution["pentagi"] == "preview_only"
    assert execution["pentagi_status_tracking"] == "available"
    assert execution["default_mode"] == "active"
    assert execution["pentagi_detail"]["dispatch_ready"] is False
    assert result["safety"]["pentagi_remote_execution_enforceable"] is False
    assert "must-not-leak" not in str(result)


def test_capabilities_api_reports_configuration_error_without_raising(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "invalid")

    result = main.system_capabilities()

    assert result["execution"]["pentagi"] == "configuration_error"
    detail = result["execution"]["pentagi_detail"]
    assert detail["dispatch_ready"] is False
    assert detail["configuration_error"] is True
