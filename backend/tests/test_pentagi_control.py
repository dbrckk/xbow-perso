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

    assert preview.decision.allowed is True
    assert preview.ready is False
    assert preview.operational_reasons == (
        "pentagi_worker_disabled",
        "pentagi_transport_disabled",
    )
    assert preview.plan.dry_run is False
    assert preview.plan.execution_supported is True


def test_control_ready_requires_worker_and_transport(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")

    preview = require_pentagi_control_ready(_campaign())

    assert preview.ready is True
    assert preview.decision.reasons == ()


def test_control_ready_keeps_global_dry_run_fail_closed(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    monkeypatch.setenv("DRY_RUN", "true")

    with pytest.raises(PentagiControlError, match="global_dry_run"):
        require_pentagi_control_ready(_campaign())
