import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_control import (
    PentagiControlError,
    prepare_pentagi_control_preview,
    require_pentagi_control_ready,
)


def _campaign():
    return Campaign(
        id="control",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _configure(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_BASE_URL", "https://pentagi.example.test")
    monkeypatch.setenv("XBOW_PENTAGI_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def test_control_preview_reports_operational_gates(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI_WORKER", raising=False)
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI_TRANSPORT", raising=False)

    preview = prepare_pentagi_control_preview(_campaign())

    assert preview.decision.allowed is False
    assert "plan_is_dry_run" in preview.decision.reasons
    assert "execution_transport_not_enforceable" in preview.decision.reasons
    assert preview.ready is False
    assert preview.operational_reasons == (
        "pentagi_worker_disabled",
        "pentagi_transport_disabled",
    )
    assert preview.plan.dry_run is True
    assert preview.plan.execution_supported is False


def test_control_ready_remains_blocked_without_enforcing_transport(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")

    with pytest.raises(PentagiControlError, match="execution_transport_not_enforceable"):
        require_pentagi_control_ready(_campaign())


def test_control_ready_keeps_global_dry_run_fail_closed(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("DRY_RUN", "true")

    with pytest.raises(PentagiControlError, match="global_dry_run"):
        require_pentagi_control_ready(_campaign())
