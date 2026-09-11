import pytest
from pydantic import ValidationError

from app.browser import (
    BrowserExecutionResult,
    BrowserFlowInput,
    BrowserPolicyError,
    BrowserStep,
    _assert_read_only_browser_method,
    _flow_dedupe_key,
    execute_browser_flow,
    persist_browser_result,
    validate_flow,
)
from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage


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


def test_browser_flow_dedupe_key_is_stable_for_same_campaign_version_and_flow():
    flow = BrowserFlowInput(
        steps=[
            BrowserStep(operation="navigate", url="https://app.test.local/login"),
            BrowserStep(operation="screenshot"),
        ]
    )
    first = _flow_dedupe_key("c1", 4, flow)
    second = _flow_dedupe_key("c1", 4, flow)
    assert first == second
    assert first.startswith("browser:v4:c1:")


def test_browser_flow_dedupe_key_changes_with_version_or_flow():
    first_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/a")])
    second_flow = BrowserFlowInput(steps=[BrowserStep(operation="navigate", url="https://app.test.local/b")])
    assert _flow_dedupe_key("c1", 1, first_flow) != _flow_dedupe_key("c1", 2, first_flow)
    assert _flow_dedupe_key("c1", 1, first_flow) != _flow_dedupe_key("c1", 1, second_flow)


def test_browser_artifacts_are_idempotent_per_job(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    campaign.id = "c1"
    store.save_campaign(campaign.model_dump(mode="json"))
    result = BrowserExecutionResult(
        status="completed",
        observations=[{"step": 1, "operation": "navigate", "url": "https://app.test.local"}],
        screenshots=[("shot.png", b"png-bytes")],
    )

    first = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")
    second = persist_browser_result(store, campaign.id, result, idempotency_prefix="job-1")

    assert [item["id"] for item in second] == [item["id"] for item in first]
    assert len(store.list_artifacts(campaign.id)) == 2


def test_invalid_browser_automation_flag_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "sometimes")
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="must be a boolean"):
        execute_browser_flow(_campaign(), flow.model_dump(mode="json"))


def test_browser_automation_flag_accepts_explicit_false_values(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_BROWSER_AUTOMATION", "OFF")
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    result = execute_browser_flow(_campaign(), flow.model_dump(mode="json"))

    assert result.status == "dry_run"


def test_browser_automation_respects_program_disable():
    campaign = _campaign()
    campaign.target.rules.automated_scanning = False
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="disabled by program rules"):
        validate_flow(campaign, flow)


@pytest.mark.parametrize(
    "flag",
    (
        "destructive_testing",
        "denial_of_service",
        "social_engineering",
        "credential_attacks",
    ),
)
def test_browser_automation_rejects_unsafe_campaign_flags(flag):
    campaign = _campaign()
    setattr(campaign.target.rules, flag, True)
    flow = BrowserFlowInput(
        steps=[BrowserStep(operation="navigate", url="https://app.test.local/login")]
    )

    with pytest.raises(BrowserPolicyError, match="unsafe campaign flags"):
        validate_flow(campaign, flow)


def test_browser_request_methods_are_read_only():
    for method in ("GET", "HEAD", "OPTIONS", " get "):
        _assert_read_only_browser_method(method)

    for method in ("POST", "PUT", "PATCH", "DELETE", "CONNECT"):
        with pytest.raises(BrowserPolicyError, match="read-only"):
            _assert_read_only_browser_method(method)


def test_browser_surface_observations_are_persistable_shape():
    result = BrowserExecutionResult(
        status="completed",
        observations=[
            {
                "step": 1,
                "operation": "surface_links",
                "urls": ["https://app.test.local/a", "https://app.test.local/b"],
            },
            {
                "step": 1,
                "operation": "surface_forms",
                "forms": [
                    {
                        "action": "https://app.test.local/search",
                        "method": "GET",
                        "input_names": ["q"],
                    }
                ],
            },
            {
                "step": 1,
                "operation": "surface_technologies",
                "technologies": ["next", "generator:fixture"],
            },
        ],
        screenshots=[],
    )

    assert result.observations[0]["operation"] == "surface_links"
    assert result.observations[1]["forms"][0]["method"] == "GET"
    assert "next" in result.observations[2]["technologies"]
