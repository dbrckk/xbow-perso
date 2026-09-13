import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_restricted_plan import (
    PentagiRestrictedPlanError,
    build_restricted_pentagi_rest_plan,
)


def _campaign():
    return Campaign(
        id="restricted",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _configure(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_BASE_URL", "https://pentagi.example.test")
    monkeypatch.setenv("XBOW_PENTAGI_MODEL_PROVIDER", "openai")
    monkeypatch.setenv(
        "XBOW_PENTAGI_BROKER_URL",
        "https://xbow.example.test/api/internal/pentagi/request",
    )
    monkeypatch.setenv(
        "XBOW_PENTAGI_BROKER_TOKEN",
        "broker-token-with-at-least-sixteen-chars",
    )


def test_restricted_rest_plan_disables_all_native_tools(monkeypatch):
    _configure(monkeypatch)

    plan = build_restricted_pentagi_rest_plan(_campaign())

    assert plan.endpoint == "https://pentagi.example.test/api/v1/flows/"
    assert plan.dry_run is True
    assert plan.execution_supported is False
    assert plan.payload["provider"] == "openai"

    functions = plan.payload["functions"]
    disabled = {item["name"] for item in functions["disabled"]}
    assert {
        "terminal",
        "file",
        "browser",
        "search_in_memory",
        "search_guide",
        "search_answer",
        "search_code",
        "store_guide",
        "store_answer",
        "store_code",
        "google",
        "duckduckgo",
        "tavily",
        "firecrawl",
        "traversaal",
        "perplexity",
        "searxng",
        "sploitus",
        "graphiti_search",
    } == disabled

    external = functions["functions"]
    assert len(external) == 1
    assert external[0]["name"] == "xbow_http_request"
    assert external[0]["schema"]["function"]["parameters"]["properties"]["method"]["enum"] == [
        "GET",
        "HEAD",
    ]


def test_restricted_plan_keeps_broker_secret_internal(monkeypatch):
    _configure(monkeypatch)

    plan = build_restricted_pentagi_rest_plan(_campaign())

    assert plan.payload["functions"]["token"].startswith("broker-token-")
    assert "broker-token" not in plan.target
    assert "broker-token" not in plan.endpoint


@pytest.mark.parametrize(
    ("name", "value", "match"),
    [
        ("XBOW_PENTAGI_BROKER_URL", "", "BROKER_URL is required"),
        ("XBOW_PENTAGI_BROKER_URL", "http://xbow.example.test/broker", "must use HTTPS"),
        ("XBOW_PENTAGI_BROKER_TOKEN", "", "broker token is unavailable"),
        ("XBOW_PENTAGI_BROKER_TOKEN", "short", "broker token is unavailable"),
    ],
)
def test_restricted_plan_requires_safe_broker_configuration(
    monkeypatch,
    name,
    value,
    match,
):
    _configure(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(PentagiRestrictedPlanError, match=match):
        build_restricted_pentagi_rest_plan(_campaign())
