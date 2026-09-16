import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import PentagiPolicyError, build_pentagi_flow_plan


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=1.5,
            ),
        ),
    )


def test_pentagi_plan_is_non_executing_and_scope_constrained():
    plan = build_pentagi_flow_plan(
        _campaign(),
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )

    assert plan.endpoint == "https://pentagi.example.test/api/v1/graphql"
    assert plan.target == "https://app.example.test/"
    assert plan.model_provider == "openai"
    assert plan.dry_run is True
    assert plan.execution_supported is False

    variables = plan.payload["variables"]
    assert variables["provider"] == "openai"
    flow_input = variables["input"]
    assert "https://app.example.test/" in flow_input
    assert "*.example.test" in flow_input
    assert "admin.example.test" in flow_input
    assert "1.5 requests/second" in flow_input
    assert "denial-of-service" in flow_input
    assert "destructive testing" in flow_input
    assert "social engineering" in flow_input
    assert "credential attacks" in flow_input
    assert "AUTH-1" not in flow_input


def test_pentagi_plan_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("XBOW_PENTAGI_BASE_URL", raising=False)
    monkeypatch.delenv("XBOW_PENTAGI_MODEL_PROVIDER", raising=False)

    with pytest.raises(PentagiPolicyError, match="XBOW_PENTAGI_BASE_URL is required"):
        build_pentagi_flow_plan(_campaign())


def test_pentagi_plan_reads_explicit_environment(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_BASE_URL", "https://pentagi.example.test")
    monkeypatch.setenv("XBOW_PENTAGI_MODEL_PROVIDER", "custom-provider")

    plan = build_pentagi_flow_plan(_campaign())

    assert plan.endpoint == "https://pentagi.example.test/api/v1/graphql"
    assert plan.model_provider == "custom-provider"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://pentagi.example.test",
        "https://user:pass@pentagi.example.test",
        "https://pentagi.example.test/path",
        "https://pentagi.example.test?x=1",
        "https://pentagi.example.test/#fragment",
        "https://[",
        "https://[::1",
        "https://pentagi.example.test:notaport",
        "https://pentagi.example.test:70000",
    ],
)
def test_pentagi_plan_rejects_unsafe_endpoint_forms(base_url):
    with pytest.raises(PentagiPolicyError):
        build_pentagi_flow_plan(
            _campaign(),
            base_url=base_url,
            model_provider="openai",
        )


@pytest.mark.parametrize(
    "provider",
    ["", "has space", "../provider", "x" * 65],
)
def test_pentagi_plan_rejects_invalid_provider(provider):
    with pytest.raises(PentagiPolicyError):
        build_pentagi_flow_plan(
            _campaign(),
            base_url="https://pentagi.example.test",
            model_provider=provider,
        )


def test_pentagi_plan_fails_closed_outside_scope():
    campaign = _campaign()
    campaign.target.rules.allowed_targets = ["other.example.test"]

    with pytest.raises(PentagiPolicyError, match="outside declared scope"):
        build_pentagi_flow_plan(
            campaign,
            base_url="https://pentagi.example.test",
            model_provider="openai",
        )


def test_pentagi_plan_fails_closed_when_automation_is_disabled():
    campaign = _campaign()
    campaign.target.rules.automated_scanning = False

    with pytest.raises(PentagiPolicyError, match="Automated scanning is disabled"):
        build_pentagi_flow_plan(
            campaign,
            base_url="https://pentagi.example.test",
            model_provider="openai",
        )


@pytest.mark.parametrize(
    "flag",
    [
        "destructive_testing",
        "denial_of_service",
        "social_engineering",
        "credential_attacks",
    ],
)
def test_pentagi_plan_refuses_unsafe_campaign_flags(flag):
    campaign = _campaign()
    setattr(campaign.target.rules, flag, True)

    with pytest.raises(PentagiPolicyError, match="Unsafe campaign flags"):
        build_pentagi_flow_plan(
            campaign,
            base_url="https://pentagi.example.test",
            model_provider="openai",
        )


def test_controlled_flag_cannot_claim_graphql_function_enforcement(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_CONTROLLED_FUNCTIONS", "true")
    plan = build_pentagi_flow_plan(
        _campaign(),
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )

    assert plan.dry_run is True
    assert plan.execution_supported is False
    assert "functions" not in plan.payload["variables"]


def test_controlled_pentagi_plan_stays_preview_only_without_contract(monkeypatch):
    monkeypatch.delenv("XBOW_PENTAGI_CONTROLLED_FUNCTIONS", raising=False)
    plan = build_pentagi_flow_plan(
        _campaign(),
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )

    assert plan.dry_run is True
    assert plan.execution_supported is False
