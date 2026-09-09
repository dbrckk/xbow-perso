import pytest
from pydantic import ValidationError

from app.browser import BrowserFlowInput, BrowserPolicyError, BrowserStep, execute_browser_flow, validate_flow
from app.main import Campaign, ProgramRules, TargetInput


def _campaign() -> Campaign:
    return Campaign(
        target=TargetInput(
            name="Local fixture",
            primary_url="https://app.test.local",
            rules=ProgramRules(
                authorization_reference="fixture-only",
                allowed_targets=["*.test.local"],
                denied_targets=["blocked.test.local"],
            ),
        )
    )


def test_browser_navigation_fails_closed_outside_scope():
    flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://example.com")])
    with pytest.raises(BrowserPolicyError, match="outside declared scope"):
        validate_flow(_campaign(), flow)


def test_browser_denied_target_overrides_wildcard_allow():
    flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://blocked.test.local")])
    with pytest.raises(BrowserPolicyError, match="outside declared scope"):
        validate_flow(_campaign(), flow)


def test_fill_rejects_literal_or_unscoped_secret_reference():
    with pytest.raises(ValidationError):
        BrowserStep(operation="fill", selector="#password")
    with pytest.raises(ValidationError):
        BrowserStep(operation="fill", selector="#password", secret_env="PASSWORD")


def test_browser_is_dry_run_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_BROWSER_AUTOMATION", raising=False)
    flow = BrowserFlowInput(
        steps=[
            BrowserStep(operation="navigate", url="https://app.test.local/login"),
            BrowserStep(operation="screenshot"),
        ]
    )
    result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))
    assert result.status == "dry_run"
    assert result.observations == [{"steps": 2}]
    assert result.screenshots == []
